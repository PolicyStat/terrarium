#!/usr/bin/env python
from __future__ import absolute_import

import argparse
import hashlib
import os
import sys
import tempfile
import shutil
import logging

from logging import getLogger, StreamHandler

import terrarium

try:
    import boto  # noqa
    import boto.s3.connection
    import boto.exception
except ImportError:
    boto = None  # noqa

from virtualenv import (  # noqa
    call_subprocess,
    create_bootstrap_script,
)

logger = getLogger(__name__)

# http://www.astro.keele.ac.uk/oldusers/rno/Computing/File_magic.html
MAGIC_NUM = {
    # magic code, offset
    'ELF': ('.ELF', 0),
    'GZIP': ('\x1f\x8b', 0),
    'BZIP': ('\x42\x5a', 0),
    'TAR': ('ustar', 257),
}


class Namespace(argparse._AttributeHolder):
    def __init__(self):
        super(Namespace, self).__init__()
        self._sensitive_arguments = set()

    def _get_kwargs(self):
        '''
        Exclude arguments which are defined as being sensitive
        '''
        kwargs = super(Namespace, self)._get_kwargs()
        return [
            (name, value) for name, value in kwargs
            if name not in self.sensitive_arguments
        ]

    @property
    def sensitive_arguments(self):
        return self._sensitive_arguments

    def add_sensitive_arguments(self, *args):
        '''
        Define arguments as being "sensitive." That is, when this object is
        converted to text, these attributes are not included.

        `args` is a list of strings that indicate the attribute name.
        '''
        self._sensitive_arguments |= set(args)


argparse.Namespace = Namespace


def rmtree(path):
    try:
        if os.path.islink(path):
            os.unlink(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.unlink(path)
        return True
    except OSError, why:
        logger.warn(
            'Failed to remove %s. '
            'Make sure you have permissions to this path. '
            '%s' % (path, why)
        )
        return False


# Helper method to determine the actual type of the file without relying on the
# file extension
def get_type(path):
    with open(path) as f:
        for file_type, magic in MAGIC_NUM.items():
            f.seek(magic[1])
            if magic[0] == f.read(len(magic[0])):
                    return file_type
    return None


class Terrarium(object):
    def __init__(self, args):
        self.args = args
        self._requirements = None
        self._digest = None

    @property
    def digest(self):
        if self._digest is not None:
            return self._digest
        m = hashlib.new(self.args.digest_type)
        m.update('\n'.join(self.requirements))
        self._digest = m.hexdigest()
        return self._digest

    @property
    def requirements(self):
        if self._requirements is not None:
            return self._requirements
        lines = []
        for arg in self.args.reqs:
            if os.path.exists(arg):
                with open(arg, 'r') as f:
                    for line in f.readlines():
                        line = line.strip()
                        if line and not line.startswith('#'):
                            lines.append(line)
        self._requirements = sorted(lines)
        return self._requirements

    def restore_previously_backed_up_environment(self):
        backup = self.get_backup_location()
        if not self.environment_exists(backup):
            logger.info(
                'Failed to restore backup. It doesn\'t appear to exist at %s',
                backup,
            )
            return 1

        target = self.get_target_location()
        if os.path.isdir(target):
            logger.info('Deleting environment at %s', target)
            rmtree(target)

        logger.info('Renaming %s to %s', backup, target)
        os.rename(backup, target)
        return 0

    def get_target_location(self):
        return os.path.abspath(self.args.target)

    def get_backup_location(self, target=None):
        if target is None:
            target = self.get_target_location()
        return ''.join([target, self.args.backup_suffix])

    def environment_exists(self, env):
        return os.path.exists(os.path.join(
            env,
            'bin',
            'activate',
        ))

    def install(self):
        logger.debug('Running install')

        old_target = self.get_target_location()
        old_target_backup = self.get_backup_location()
        new_target = old_target
        prompt = os.path.basename(new_target)

        # Are we building a new environment, or replacing an existing one?
        old_target_exists = self.environment_exists(old_target)
        if old_target_exists:
            new_target = tempfile.mkdtemp(
                prefix='%s.' % os.path.basename(old_target),
                dir=os.path.dirname(old_target),
            )

        # Can the requested environment be downloaded?
        downloaded = False
        if self.args.download:
            downloaded = self.download(new_target)

        if not downloaded:
            if self.args.require_download:
                logger.error(
                    'Failed to download bundle and download is '
                    'required. Refusing to build a new bundle.'
                )
                return 1

            # Create a self-contained script to create a virtual environment
            # and install all of the requested requirements
            logger.info('Building new environment')
            fd, bootstrap = tempfile.mkstemp(
                prefix='terrarium_bootstrap-',
                suffix='.py',
            )
            self.create_bootstrap(bootstrap)

            # Run the bootstrap script which pip installs everything that has
            # been defined as a requirement
            call_subprocess([
                sys.executable,
                bootstrap,
                '--prompt=(%s)' % prompt,
                new_target
            ])

            # Do we want to copy the bootstrap into the environment for future
            # use?
            if self.args.bootstrap:
                logger.info('Copying bootstrap script to new environment')
                dest = os.path.join(
                    new_target, 'bin', 'terrarium_bootstrap.py')
                shutil.copyfile(bootstrap, dest)
                os.chmod(dest, 0744)
            os.close(fd)
            os.unlink(bootstrap)

            if self.args.upload:
                self.upload(new_target)

        if old_target_exists:
            logger.info('Moving old environment out of the way')
            if os.path.exists(old_target_backup):
                if not rmtree(old_target_backup):
                    old_target_backup = tempfile.mkdtemp(
                        prefix='terrarium_old_backup_target-'
                    )
                    old_target_backup = os.path.join(old_target_backup, prompt)
                    logger.info(
                        'Backing environment up to %s' % old_target_backup)
            try:
                os.rename(old_target, old_target_backup)
            except OSError, why:
                logger.error(
                    'Failed to move environment out of the way. '
                    'Check that you have the correct permissions. '
                    '%s' % why
                )
                return 1

            # Fix paths
            Terrarium.replace_all_in_directory(
                os.path.join(new_target, 'bin'),
                new_target,
                old_target,
            )

        try:
            # move the new environment into the target's place
            os.rename(new_target, old_target)
        except OSError, why:
            logger.error(
                'Failed to move the new environment into the correct path. '
                'Check that you have the correct permissions. '
                '%s' % why
            )
            return 1

        # Do we keep a backup of the old environment around or wipe it?
        if os.path.isdir(old_target_backup) and not self.args.backup:
            logger.info('Deleting old environment')
            rmtree(old_target_backup)
        logger.info('Terrarium is finished')
        return 0

    @staticmethod
    def replace_all_in_directory(
        location,
        old,
        replace='__VIRTUAL_ENV__',
        binary=False,
    ):
        for name in os.listdir(location):
            full_path = os.path.join(location, name)
            data = None
            with open(full_path) as f:
                header = f.read(len(MAGIC_NUM['ELF']))
                # Skip binary files
                if binary or header != MAGIC_NUM['ELF']:
                    data = header + f.read()
            if not data:
                continue
            new_data = data.replace(old, replace)
            if new_data == data:
                continue
            with open(full_path, 'w') as f:
                data = f.write(new_data)

    @staticmethod
    def wipe_all_precompiled_python_files_in_dir(path):
        return call_subprocess([
            'find', path, '-type', 'f', '-name', '*.py[c|o]', '-delete'
        ])

    @staticmethod
    def make_bin_dir_paths_relative(bin_dir, target):
        Terrarium.replace_all_in_directory(bin_dir, target)

    @staticmethod
    def make_bin_dir_paths_absolute(bin_dir, target):
        Terrarium.replace_all_in_directory(
            bin_dir,
            '__VIRTUAL_ENV__',
            target,
        )

    def archive(self, target):
        logger.info('Building terrarium bundle')

        bin_dir = os.path.join(target, 'bin')

        Terrarium.wipe_all_precompiled_python_files_in_dir(target)
        Terrarium.make_bin_dir_paths_relative(bin_dir, target)

        archive = '%s.tar' % target

        # Create an archive of the environment
        call_subprocess([
            'tar',
            '--exclude', '.svn',
            '--exclude', '.git',
            '--exclude', '.bzr',
            '--exclude', '.hg',
            '--exclude', 'bin/python',
            '-cf', archive,
            '-C', target,
            '.'
        ])

        if self.args.compress:
            # Compress the tarball
            call_subprocess(['gzip', archive])
            archive = '%s.gz' % archive

        Terrarium.make_bin_dir_paths_absolute(bin_dir, target)
        return archive

    def extract(self, archive, target):
        logger.info('Extracting terrarium bundle')

        archive_type = get_type(archive)

        if archive_type == 'GZIP':
            tar_op = 'xzf'
        elif archive_type == 'BZIP':
            tar_op = 'xjf'
        elif archive_type == 'TAR':
            tar_op = 'xf'
        else:
            logger.error(
                'Failed to extract archive, unknown or unsupported file type')
            return
        if not os.path.exists(target):
            os.mkdir(target)
        call_subprocess(['tar', tar_op, archive, '-C', target])

        bin_dir = os.path.join(target, 'bin')

        # Restore python binary
        path_to_python = sys.executable
        dest = python_binary = os.path.basename(path_to_python)

        if python_binary.startswith('python') and python_binary != 'python':
            dest = 'python'
        dest = os.path.join(bin_dir, dest)
        if not os.path.exists(dest):
            call_subprocess([
                'cp',
                path_to_python,
                dest,
            ])

        # Fix up paths
        Terrarium.make_bin_dir_paths_absolute(bin_dir, target)

    def _get_s3_bucket(self):
        if not boto:
            return None
        conn = boto.s3.connection.S3Connection(
            aws_access_key_id=self.args.s3_access_key,
            aws_secret_access_key=self.args.s3_secret_key
        )
        try:
            conn.create_bucket(
                self.args.s3_bucket,
                policy='public-read',
            )
        except (boto.exception.S3CreateError, boto.exception.S3ResponseError):
            pass
        return boto.s3.bucket.Bucket(conn, name=self.args.s3_bucket)

    def download(self, target):
        if self.args.storage_dir:
            remote_archive = os.path.join(
                self.args.storage_dir,
                self.make_remote_key(),
            )
            if os.path.exists(remote_archive):
                logger.info(
                    'Copying environment from %s (this may take time) ...'
                    % self.args.storage_dir,
                )
                local_archive = '%s.tar.gz' % target
                shutil.copyfile(
                    remote_archive,
                    local_archive,
                )
                self.extract(local_archive, target)
                os.unlink(local_archive)
                return True
            logger.error('Download archive failed')
        if boto and self.args.s3_bucket:
            bucket = self._get_s3_bucket()
            if bucket:
                remote_key = self.make_remote_key()
                key = bucket.get_key(remote_key)
                if key:
                    logger.info(
                        'Downloading %s/%s from S3 '
                        '(this may take time) ...'
                        % (self.args.s3_bucket, remote_key)
                    )
                    fd, archive = tempfile.mkstemp()
                    key.get_contents_to_filename(archive)
                    self.extract(archive, target)
                    os.close(fd)
                    os.unlink(archive)
                    return True

    def make_remote_key(self):
        import platform
        major, minor, patch = platform.python_version_tuple()
        context = {
            'digest': self.digest,
            'python_vmajor': major,
            'python_vminor': minor,
            'python_vpatch': patch,
            'arch': platform.machine(),
        }
        return self.args.remote_key_format % context

    def upload_to_storage_dir(self, target, storage_dir):
        logger.info('Copying environment to storage directory')
        dest = os.path.join(storage_dir, self.make_remote_key())
        if os.path.exists(dest):
            logger.error(
                'Environment already exists at %s'
                % dest,
            )
        else:
            archive = self.archive(target)
            if not archive:
                logger.error('Archiving failed')
            shutil.copyfile(archive, dest)
            logger.info('Archive copied to storage directory')
            os.unlink(archive)

    def upload_to_s3(self, target):
        logger.info('Uploading environment to S3')
        attempts = 0
        bucket = self._get_s3_bucket()
        if not bucket:
            return False

        key = bucket.new_key(self.make_remote_key())
        archive = self.archive(target)
        if not archive:
            logger.error('Archiving failed')

        try:
            key.set_contents_from_filename(archive)
            logger.debug('upload finished')
            os.unlink(archive)
            return True
        except Exception:
            attempts = attempts + 1
            logger.warning('There was an error uploading the file')
            if attempts > self.args.s3_max_retries:
                logger.error(
                    'Attempted to upload archive to S3, but failed'
                )
                raise
            else:
                logger.info('Retrying S3 upload')

    def upload(self, target):
        if self.args.storage_dir:
            self.upload_to_storage_dir(
                target,
                self.args.storage_dir,
            )
        if boto and self.args.s3_bucket:
            self.upload_to_s3(target)

    def create_bootstrap(self, dest):
        extra_text = (
            TERRARIUM_BOOTSTRAP_EXTRA_TEXT.format(
                requirements=self.requirements,
                virtualenv_log_level=self.args.virtualenv_log_level,
                pip_log_level=self.args.pip_log_level,
            )
        )
        output = create_bootstrap_script(extra_text)
        with open(dest, 'w') as f:
            f.write(output)


TERRARIUM_BOOTSTRAP_EXTRA_TEXT = r'''
def adjust_options(options, args):
    options.use_distribute = True
    options.system_site_packages = False

REQUIREMENTS = {requirements}

def after_install(options, base):
    import os
    import tempfile

    # Debug logging for virtualenv
    logger.consumers = [({virtualenv_log_level}, sys.stdout)]

    home_dir, lib_dir, inc_dir, bin_dir = path_locations(base)

    # Update prefix and executable to point to the virtualenv
    sys.prefix = os.path.abspath(base)
    sys.exec_prefix = sys.prefix
    sys.executable = join(os.path.abspath(bin_dir), 'python')

    # Create a symlink for pythonM.N
    pyv_major, pyv_minor = (sys.version_info[0], sys.version_info[1])
    pyversion_path = join(bin_dir, 'python{{major}}.{{minor}}'.format(
        major=pyv_major,
        minor=pyv_minor,
    ))
    # If virtualenv is run using pythonM.N, that binary will already exist so
    # there's no need to create it
    if not os.path.exists(pyversion_path):
        os.symlink('python', pyversion_path)

    # Activate the virtualenv
    activate_this = join(bin_dir, 'activate_this.py')
    execfile(activate_this, dict(__file__=activate_this))

    import pip
    from pip.commands.install import InstallCommand

    # Debug logging for pip
    pip.logger.consumers = [({virtualenv_log_level}, sys.stdout)]

    # If we are on a version of pip before 1.2, load version control modules
    # for installing 'editables'
    if hasattr(pip, 'version_control'):
        pip.version_control()

    # Run pip install
    try:
        c = InstallCommand()
    except TypeError:
        from pip.baseparser import create_main_parser
        main_parser = create_main_parser()
        c = InstallCommand(main_parser)

    fd, file_path = tempfile.mkstemp()
    with os.fdopen(fd, 'w') as f:
        f.write('\n'.join(REQUIREMENTS))
    options, args = c.parser.parse_args(['-r', file_path])
    options.require_venv = True
    options.ignore_installed = True
    requirementSet = c.run(options, args)

    os.unlink(file_path)

    make_environment_relocatable(base)
'''


def parse_args():
    sensitive_arguments = [
        's3_access_key',
        's3_secret_key',
    ]
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '-V', '--version',
        action='version',
        version='%(prog)s ' + terrarium.__version__,
    )
    ap.add_argument(
        '-v', '--verbose',
        action='append_const',
        const=-10,
        default=[logging.INFO],
        dest='v',
        help='Increase verbosity',
    )
    ap.add_argument(
        '-q', '--quiet',
        action='append_const',
        const=10,
        default=[logging.INFO],
        dest='v',
        help='Decrease verbosity',
    )
    ap.add_argument(
        '-t', '--target',
        dest='target',
        default=os.environ.get('VIRTUAL_ENV', None),
        help='''
            Replace or build new environment at this location. If you are
            already within a virtual environment, this option defaults to
            VIRTUAL_ENV.
        ''',
    )
    ap.add_argument(
        '--pip-log-level',
        default=25,
        help='''
        Set the log level for pip
        ''',
    )
    ap.add_argument(
        '--virtualenv-log-level',
        default=25,
        help='''
        Set the log level for virtualenv
        ''',
    )
    ap.add_argument(
        '--no-download',
        default=True,
        action='store_false',
        dest='download',
        help='''
            If an external storage location is specified, terrarium will
            attempt to download an existing terrarium bundle instead of
            building a new one. Using --no-download forces terrarium to build a
            new environment.
        ''',
    )
    ap.add_argument(
        '--require-download',
        default=False,
        action='store_true',
        help='''
            If we fail to download a terrarium bundle from the storage
            location, do not proceed to build one.
        ''',
    )
    ap.add_argument(
        '--no-upload',
        default=True,
        action='store_false',
        dest='upload',
        help='''
            If an external storage location is specified, terrarium will upload
            a new environment after it has been built. Using --no-upload,
            terrarium will not upload the resulting environment to the external
            storage location.
        ''',
    )
    ap.add_argument(
        '--no-backup',
        default=True,
        action='store_false',
        dest='backup',
        help='''
            By default, terrarium preserves the old environment. See
            --backup-suffix. Using this option, terrarium will delete the old
            environment.
        ''',
    )
    ap.add_argument(
        '--backup-suffix',
        default='.bak',
        help='''
            The suffix to use when preserving an old environment. This option
            is ignored if --no-backup is used. Default is .bak.
        '''
    )
    ap.add_argument(
        '--no-compress',
        default=True,
        action='store_false',
        dest='compress',
        help='''
            By default, terrarium compresses the archive using gzip before
            uploading it.
        ''',
    )
    ap.add_argument(
        '--storage-dir',
        default=os.environ.get('TERRARIUM_STORAGE_DIR', None),
        help='''
            Path to a directory in which terrarium bundles will be retrieved
            and stored for speedy re-installation. This will usually be a
            shared drive.
        ''',
    )
    ap.add_argument(
        '--digest-type',
        default='md5',
        help='Choose digest type (md5, sha, see hashlib). Default is md5.',
    )
    ap.add_argument(
        '--no-bootstrap',
        default=True,
        action='store_false',
        dest='bootstrap',
        help='''
            By default, terrarium will create a script called
            'terrarium_bootstrap.py' in the new environment bin directory.
            Running this script will create a new environment at the specified
            location using all of the packages that were defined at the time of
            its creation. To prevent this script from being created, use
            --no-bootstrap.
        ''',
    )
    default_remote_key_format = '''
        %(arch)s-%(python_vmajor)s.%(python_vminor)s-%(digest)s
    '''.strip()
    ap.add_argument(
        '--remote-key-format',
        default=default_remote_key_format,
        help='''
            Key name format to use when storing the archive. Default is "%s"
        ''' % default_remote_key_format.replace('%', '%%'),
    )

    ap.add_argument(
        '--s3-bucket',
        default=os.environ.get('S3_BUCKET', None),
        help='''
            S3 bucket name. Defaults to S3_BUCKET env variable.
        '''
    )
    ap.add_argument(
        '--s3-access-key',
        default=os.environ.get('S3_ACCESS_KEY', None),
        help='''
            Defaults to S3_ACCESS_KEY env variable.
        '''
    )
    ap.add_argument(
        '--s3-secret-key',
        default=os.environ.get('S3_SECRET_KEY', None),
        help='''
            Defaults to S3_SECRET_KEY env variable.
        '''
    )
    ap.add_argument(
        '--s3-max-retries',
        default=os.environ.get('S3_MAX_RETRIES', 3),
        help='''
            Number of times to attempt a S3 operation before giving up.
            Default is 3.
        ''',
    )

    subparsers = ap.add_subparsers(
        title='Basic Commands',
        dest='command',
    )
    commands = {
        'hash': subparsers.add_parser(
            'hash',
            help='Display digest for current requirement set',
        ),
        'key': subparsers.add_parser(
            'key',
            help='Display remote key for current requirement set and platform',
        ),
        'install': subparsers.add_parser(
            'install',
            help='''
                Replace current environment with the one given by the
                requirement set.
            ''',
        ),
        'revert': subparsers.add_parser(
            'revert',
            help='''
                Restore the most recent backed-up virtualenv, if it exists.
            ''',
        ),
    }

    for command in commands.values():
        command.add_argument('reqs', nargs=argparse.REMAINDER)

    args = ap.parse_args()
    args.add_sensitive_arguments(*sensitive_arguments)

    if not boto and args.s3_bucket is not None:
        ap.error(
            '--s3-bucket requires that you have boto installed, '
            'which does not appear to be the case'
        )

    return args


def main():
    args = parse_args()

    log_level = max(logging.DEBUG, sum(args.v))
    logger.setLevel(log_level)
    logger.addHandler(StreamHandler())

    logger.debug('Initialized with %s', args)

    terrarium = Terrarium(args)

    r = 0
    if args.command == 'hash':
        sys.stdout.write('%s\n' % terrarium.digest)
    if args.command == 'key':
        key = terrarium.make_remote_key()
        sys.stdout.write('%s\n' % key)
    elif args.command == 'install':
        r = terrarium.install()
    elif args.command == 'revert':
        r = terrarium.restore_previously_backed_up_environment()
    sys.exit(r)

if __name__ == '__main__':
    main()
