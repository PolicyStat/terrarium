#!/usr/bin/env python
'Script to generate a portable virtual environment'

import logging
import os
import tempfile
import sys

from optparse import OptionParser

from boto.exception import S3CreateError
from boto.s3.connection import S3Connection
from boto.s3.bucket import Bucket

logger = logging.getLogger('terrarium')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('[%(name)s]%(levelname)s:%(message)s')
stderr_handler = logging.StreamHandler()
stderr_handler.setFormatter(formatter)
logger.addHandler(stderr_handler)

from virtualenv import (
    make_environment_relocatable, create_bootstrap_script,
    join, call_subprocess, path_locations, Logger, rmtree
)

def _get_bucket(s3_bucket, s3conn):
    '''
    Ensures the given S3 bucket exists by creating a public bucket
    if it doesn't.
    '''
    try:
        s3conn.create_bucket(s3_bucket, policy='public-read')
    except S3CreateError:
        pass
    return Bucket(s3conn, name=s3_bucket)

class EnvironmentBuilder(object):
    def __init__(self, options, parser, args, **kwargs):
        self.options = options
        self.parser = parser
        self.args = args
        self.md5sum = None
        self.current = None
        self.path = None
        if options.requirements:
            self.md5sum = files_hash(options.requirements)
        if options.environment_base:
            self.current = join(options.environment_base, 'current')
            self.path = join(options.environment_base, self.md5sum)
        if options.pack:
            self.path = options.pack

    def exists(self):
        if self.path:
            return os.path.exists(self.path)
        return False

    def update_current_symlink(self):
        if self.current:
            if os.path.exists(self.current):
                os.unlink(self.current)
            os.symlink(self.path, self.current)

    @staticmethod
    def _create_bootstrap(dest):
        handler = open(__file__).read()
        start = handler.rfind('##### BLOCK VIRTUALENV')
        start = handler.find('\n', start)
        end = handler.rfind('##### ENDBLOCK VIRTUALENV')
        extra_text = handler[start + 1:end - 1]
        output = create_bootstrap_script(extra_text)
        with open(dest, 'w') as f:
            f.write(output)

    @staticmethod
    def _wipe_all_precompiled_python_files_in_dir(path):
        return call_subprocess([
            'find', path, '-type', 'f', '-name', '*.py[c|o]', '-delete'
        ])

    @staticmethod
    def _replace_all_in_directory(location, old,
            replace='__VIRTUAL_ENV__', binary=False):
        for name in os.listdir(location):
            full_path = join(location, name)
            data = None
            with open(full_path) as f:
                header = f.read(4)
                if binary or header != '\x7fELF':
                    data = header + f.read()
            if not data:
                continue
            new_data = data.replace(old, replace)
            if new_data == data:
                continue
            with open(full_path, 'w') as f:
                data = f.write(new_data)

    @staticmethod
    def _tar_extract(archive, destination):
        opts = [
            'xf', # No compression
            'xzf', # gzip compression
            'xjf', # bzip2 compression
        ]
        os.mkdir(destination)
        for opt in opts:
            try:
                call_subprocess(['tar', opt, archive, '-C', destination])
            except OSError:
                continue
            break

    def _get_s3_connection(self):
        assert self.options.s3_access_key is not None
        assert self.options.s3_secret_key is not None
        assert self.options.s3_bucket is not None
        s3conn = S3Connection(
            aws_access_key_id=self.options.s3_access_key,
            aws_secret_access_key=self.options.s3_secret_key)
        s3_bucket = _get_bucket(self.options.s3_bucket, s3conn)
        return s3conn, s3_bucket

    def build_fresh(self):
        assert self.path
        logger.info('Building fresh environment at %s', self.path)
        fd, bootstrap = tempfile.mkstemp(prefix='pstat_bootstrap_', suffix='.py')

        # Generate a self-contained bootstrap
        EnvironmentBuilder._create_bootstrap(bootstrap)

        # Run the bootstrap script
        requirements = []
        for r in self.options.requirements:
            requirements.extend(['-r', r])
        call_subprocess(['python', bootstrap] + requirements + [self.path])

        # Cleanup
        os.close(fd)
        os.unlink(bootstrap)

        if self.options.upload_environment:
            archive = self.pack()
            self.upload_to_s3(archive)
            return archive

    def pack(self, tarball=None):
        '''
        Do everything needed to prepare an environment for being
        pushed to S3
        '''
        path = self.path
        if not path:
            path = self.options.pack
        assert path
        compress = self.options.compress

        logger.info('packing environment archive %s', path)
        if not tarball:
            tarball = path + '.tar'

        bin_dir = join(path, 'bin')

        # Don't include python binary in distribution (re-link on extract)
        python_bin = join(bin_dir, 'python')
        if os.path.exists(python_bin):
            os.unlink(python_bin)

        # Wipe precompiled python files
        EnvironmentBuilder._wipe_all_precompiled_python_files_in_dir(path)

        # Replace absolute paths in the bin directory
        EnvironmentBuilder._replace_all_in_directory(bin_dir, path)

        # Create an archive of the environment
        call_subprocess([
            'tar', '--exclude-vcs', '-cf', tarball, '-C', path, '.'
        ])

        # Compress if desired (e.g. gzip, or bzip2)
        if compress:
            call_subprocess([compress, tarball])

        extension = {'gzip': '.gz', 'bzip2': '.bz2'}.get(compress, '')
        return tarball + extension

    def unpack(self, archive=None, destination=None):
        if not archive:
            archive = self.options.unpack
            destination = self.args[0]
        logger.info('unpacking environment archive %s', archive)
        EnvironmentBuilder._tar_extract(archive, destination)
        # Rebuild hard links to system-installed python
        vbin = join(destination, 'bin')
        # Fix up paths
        EnvironmentBuilder._replace_all_in_directory(vbin, '__VIRTUAL_ENV__', destination)
        # Restore python binary
        path_to_python = sys.executable
        call_subprocess(['cp', path_to_python, vbin])
        os.link(join(vbin, 'python'), join(vbin, 'python2.6'))

    def upload_to_s3(self, archive):
        logger.info('uploading environment')
        attempts = 0
        while True:
            _, s3_bucket = self._get_s3_connection()
            key = s3_bucket.new_key(self.md5sum)
            try:
                key.set_contents_from_filename(archive)
                logger.debug('upload finished')
                break
            except Exception:
                attempts = attempts + 1
                logger.warning('There was an error uploading the file')
                if attempts > self.options.max_s3_retries:
                    logger.error('Retries exhasted upload the file')
                    raise

    def _save_requirements_md5sum(self, destination):
        with open(join(destination, 'md5sum'), 'w') as f:
            f.write(self.md5sum)

    def fetch_from_s3(self, destination=None):
        _, s3_bucket = self._get_s3_connection()
        env_s3_key = s3_bucket.get_key(self.md5sum)
        if env_s3_key:
            destination = self.path
            logger.info('Downloading environment tarball from S3')
            fd, archive = tempfile.mkstemp()
            env_s3_key.get_contents_to_filename(archive)
            self.unpack(archive, destination)
            self._save_requirements_md5sum(destination)
            os.close(fd)
            os.unlink(archive)
            return True

def validate_options(parser):

    def has_required_options(options_given, options_required):
        return not any(
            getattr(options_given, param) is None for param in options_required
        )

    options, args = parser.parse_args()

    if options.unpack:
        if len(args) == 0:
            parser.error('--unpack requires destination')

    if (options.build_fresh_environment or
            options.make_s3_env) and not options.requirements:
        requirements = os.environ.get('REQUIREMENTS', None)
        if requirements:
            requirements = requirements.split(',')
            requirements = [r.strip() for r in requirements]
        if requirements:
            options.requirements = requirements
        else:
            parser.error(
                'At least one requirements file must be provided with --requirement'
            )

    if options.build_fresh_environment:
        required_params = [
            'environment_base',
        ]
        if not has_required_options(options, required_params):
            parser.error(
                '--build-fresh requires parameters %s' % ', '.join(
                    required_params
                )
            )

    if options.make_s3_env:
        required_params = [
            's3_bucket',
            's3_access_key',
            's3_secret_key',
            'environment_base',
            'requirements',
        ]
        if not has_required_options(options, required_params):
            parser.error(
                '--make-s3-env requires parameters %s' % ', '.join(
                    required_params
                )
            )
    if options.get_s3_env:
        required_params = [
            's3_bucket',
            'environment_base',
            'requirements',
        ]
        if not has_required_options(options, required_params):
            parser.error(
                '--get-s3-env requires parameters %s' % ', '.join(
                    required_params
                )
            )
    return options, args

def configure_main_option_parser(parser=None):

    def optional_arg(arg_default):
        def func(option, opt_str, value, parser):
            if parser.rargs and not parser.rargs[0].startswith('-'):
                val = parser.rargs[0]
                parser.rargs.pop(0)
            else:
                val = arg_default
            setattr(parser.values, option.dest, val)
        return func

    if parser is None:
        parser = OptionParser('usage: %prog [options]')
    parser.add_option('-r', '--requirement',
        dest='requirements', action='append',
        help='')
    parser.add_option('--create-bootstrap', dest='create_bootstrap',
        action='callback', callback=optional_arg('bootstrap.py'),
        help='Create a bootstrapping script that will build '
            'the environment from scratch without requiring '
            'virtualenv to be installed')
    parser.add_option('--make-s3-env',
        action='store_true', default=False,
        help='Fetch environment from S3 if it exists, otherwise build a '
            'fresh environment, use and push it to S3'
    )
    parser.add_option('-g', '--get-s3-env',
        action='store_true', default=False,
        help='Fetch environment from S3 if it exists'
    )
    parser.add_option('--s3-bucket',
        default=os.environ.get('S3_REQS_BUCKET', None),
        help='S3 bucket to use for making/getting the environment')
    parser.add_option('--s3-access-key',
        default=os.environ.get('S3_REQS_ACCESS_KEY', None),
        help='S3 access key to use for making the environment')
    parser.add_option('--s3-secret-key',
        default=os.environ.get('S3_REQS_SECRET_KEY', None),
        help='S3 secret access key to use for making the environment')
    parser.add_option('-b', '--build-fresh', dest='build_fresh_environment',
        action='store_true', help='Build a fresh environment')
    parser.add_option('--upload', dest='upload_environment',
        action='store_true', help='Upload to S3')
    parser.add_option('-c', '--compress', dest='compress', default='gzip',
        action='callback', callback=optional_arg('gzip'),
        help='Compress the environment')
    parser.add_option('--max-s3-retries', default=1,
        help='Number of times to attempt a S3 action before giving up')
    parser.add_option('-p', '--pack', default=None,
        help='Pack up an environment for relocation')
    parser.add_option('-u', '--unpack', default=None,
        help='Unpack a relocatable environment for use')
    parser.add_option('-e', '--environment-base', default=None,
        help='Specify where environments live')
    return parser

def main(parser=None):
    parser = configure_main_option_parser(parser)
    options, args = validate_options(parser)

    if options.create_bootstrap is not None:
        return EnvironmentBuilder._create_bootstrap(options.create_bootstrap)

    env = EnvironmentBuilder(options, parser, args)
    if options.pack:
        return env.pack()
    if options.unpack:
        return env.unpack()
    if options.get_s3_env:
        if env.exists():
            logger.info('Using existing environment at %s (md5 matches)', env.path)
        else:
            if not env.fetch_from_s3():
                logger.error('Matching environment does not exist on S3.')
                logger.error(
                    'Use --make-s3-env to create and upload environment.'
                )
        return env.update_current_symlink()
    if options.make_s3_env:
        if env.exists():
            logger.info('Using existing environment at %s (md5 matches)', env.path)
        elif not env.fetch_from_s3():
            options.upload_environment = True
            archive = env.build_fresh()
            if archive:
                rmtree(env.path)
                env.unpack(archive, env.path)
        return env.update_current_symlink()
    if options.build_fresh_environment:
        return env.build_fresh()
    return parser.print_help()

# The code within the VIRTUALENV block is included in the generated
# bootstrap script to override default behavior.

##### BLOCK VIRTUALENV
import hashlib

def build_kwargs(options, base):
    home_dir, lib_dir, inc_dir, bin_dir = path_locations(base)
    lib_dir = join(home_dir, 'lib')
    # TODO This is a terrible hack, but it works for now
    usr_lib = '/usr/lib/x86_64-linux-gnu'
    if not os.path.exists(usr_lib):
        usr_lib = '/usr/lib'
    return dict(
        base=base,
        bin=bin_dir,
        lib=lib_dir,
        usr_lib=usr_lib,
        pip=join(bin_dir, 'pip'),
        activate_this=join(bin_dir, 'activate_this.py'),
    )

def set_boto_socket_timeout(*args, **kwargs):
    # Try to set the boto connection timeout to fail quickly in boto>=2.0
    try:
        from boto import config
        if not config.has_section('Boto'):
            config.add_section('Boto')
        config.set('Boto', 'http_socket_timeout', '5')
    except ImportError:
        pass

def create_symlinks(*args, **kwargs):
    logger.info('creating symlinks')
    # In order to link with these libraries, PIL needs these
    # to show up in the lib directory
    LIBS = [
        'libz.so',
        'libjpeg.so.62',
        'libfreetype.so',
    ]
    env_lib = kwargs.get('lib')
    usr_lib = kwargs.get('usr_lib')
    for lib in LIBS:
        if not os.path.exists(join(env_lib, lib)):
            cmd = [
                'ln', '-s', join(usr_lib, lib), join(env_lib, lib)
            ]
            call_subprocess(cmd)

def install_prerequisites(*args, **kwargs):
    create_symlinks(*args, **kwargs)

# Called just before options are parsed
def extend_parser(parser):
    parser.add_option('-r', '--requirement',
        dest='requirements', action='append',
        help='')

def pip_install(options, **kwargs):
    # from pip.commands.install import InstallCommand
    # TODO Interface with InstallCommand or create RequirementSets
    # instead of doing the following?
    pip = kwargs.get('pip')
    command = [pip, 'install']
    for req in options.requirements:
        command.extend(['-r', req])
    call_subprocess(command)

def set_logger_level(level):
    for i in range(len(logger.consumers)):
        consumer = logger.consumers[i]
        if consumer[1] == sys.stdout:
            logger.consumers[i] = (level, sys.stdout)

# Called just after options are parsed
def adjust_options(options, args):
    options.use_distribute = True
    options.system_site_packages = False
    options.prompt = '{pstat_env}'

# Called at the very end of the virtualenv
def after_install(options, base):
    set_logger_level(Logger.INFO)
    logger.info('after install')
    kwargs = build_kwargs(options, base)
    install_prerequisites(**kwargs)
    set_boto_socket_timeout(**kwargs)
    pip_install(options, **kwargs)
    # making a virtualenv relocatable can fail for a variety of reasons of
    # which are all silently discarded unless you increase the logging
    # verbosity
    set_logger_level(Logger.DEBUG)
    activate_this = kwargs.get('activate_this')
    execfile(activate_this, dict(__file__=activate_this))
    make_environment_relocatable(base)

def files_hash(files):
    lines = []
    for file_path in files:
        with open(file_path, 'r') as f:
            lines.extend(f.readlines())
    m = hashlib.md5()
    m.update('\n'.join(sorted(lines)))
    return m.hexdigest()

def files_changed(hashcode, hash_path):
    '''
    Determine if the hash at hash_path matches the given files.
    '''
    if not os.path.exists(hash_path):
        return True
    return hashcode != open(hash_path, 'r').readline().strip()
##### ENDBLOCK VIRTUALENV

if __name__ == '__main__':
    main()
