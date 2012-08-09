#!/usr/bin/env python

import argparse
import hashlib
import logging
import os
import sys
import tempfile
import shutil

try:
    import boto  # noqa
except ImportError:
    boto = None  # noqa

from virtualenv import (  # noqa
    call_subprocess,
    create_bootstrap_script,
)

logger = logging.getLogger(__name__)


class Terrarium(object):
    def __init__(self, args):
        self.args = args
        self._requirements = None
        self._digest = None
        logger.debug('Terrarium created with %s', args)

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
                        if line:
                            lines.append(line)
        self._requirements = sorted(lines)
        return self._requirements

    def install(self):
        logger.debug('Running install')

        environment = self.args.environment
        prompt = os.path.basename(environment)
        if os.path.isdir(environment):
            environment = tempfile.mkdtemp(
                prefix=os.path.basename(environment),
                dir=os.path.dirname(environment),
            )

        if self.args.download:
            if self.download(environment):
                return

        logger.info('Building new environment')
        fd, bootstrap = tempfile.mkstemp(
            prefix='terrarium_bootstrap-',
            suffix='.py',
        )
        self.create_bootstrap(bootstrap)

        call_subprocess([
            sys.executable,
            bootstrap,
            '--prompt=(%s)' % prompt,
            environment
        ])
        os.close(fd)

        if self.args.upload:
            self.upload(environment)

    def download(self, environment):
        if self.args.storage_dir:
            remote_archive = os.path.join(
                self.args.storage_dir,
                self.digest,
            )
            if os.path.exists(remote_archive):
                logger.info(
                    'Copying environment from %s'
                    % self.args.storage_dir,
                )
                local_archive = '%s.tar.gz' % environment
                shutil.copyfile(
                    remote_archive,
                    local_archive,
                )
                return True
            logger.error('Download archive failed')
        if boto and self.args.s3_bucket:
            bucket = self._get_s3_bucket()
            if bucket:
                key = bucket.get_key(self.digest)
                if key:
                    logger.info('Downloading environment from S3')
                    fd, archive = tempfile.mkstemp()
                    key.get_contents_to_filename(archive)
                    # TODO
                    os.close(fd)
                    os.unlink(archive)
                    return True

    def _get_s3_bucket(self):
        if not boto:
            return None
        conn = boto.S3Connection(
            aws_access_key_id=self.args.s3_access_key,
            aws_secret_access_key=self.args.s3_secret_key
        )
        try:
            conn.create_bucket(
                self.args.s3_bucket,
                policy='public-read',
            )
        except boto.S3CreateError:
            pass
        return boto.Bucket(conn, name=self.args.s3_bucket)

    def archive(self, environment):
        logger.info('Building environment archive')
        # TODO
        return None

    def upload(self, environment):
        if self.args.storage_dir:
            logger.info('Copying environment to storage directory')
            dest = os.path.join(
                self.args.storage_dir,
                self.digest,
            )
            if os.path.exists(dest):
                logger.error(
                    'Environment already exists at %s'
                    % dest,
                )
            else:
                archive = self.archive(environment)
                if not archive:
                    logger.error('Archiving failed')
                shutil.copyfile(archive, dest)
                logger.info('Archive copied to storage directory')
        if boto and self.args.s3_bucket:
            logger.info('Uploading environment to S3')
            attempts = 0
            bucket = self._get_s3_bucket()
            if bucket:
                key = bucket.new_key(self.digest)
                archive = self.archive(environment)
                if not archive:
                    logger.error('Archiving failed')
                try:
                    key.set_contents_from_filename(archive)
                    logger.debug('upload finished')
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

    def create_bootstrap(self, dest):
        extra_text = (
            TERRARIUM_BOOTSTRAP_EXTRA_TEXT %
                {'REQUIREMENTS': self.requirements}
        )
        output = create_bootstrap_script(extra_text)
        with open(dest, 'w') as f:
            f.write(output)


TERRARIUM_BOOTSTRAP_EXTRA_TEXT = '''
def adjust_options(options, args):
    options.use_distribute = True
    options.system_site_packages = False

REQUIREMENTS = %(REQUIREMENTS)s

def after_install(options, base):
    # Debug logging for virtualenv
    logger.consumers = [(logger.DEBUG, sys.stdout)]

    home_dir, lib_dir, inc_dir, bin_dir = path_locations(base)

    # Update prefix and executable to point to the virtualenv
    sys.prefix = os.path.abspath(base)
    sys.executable = join(os.path.abspath(bin_dir), 'python')

    # Create a symlink for pythonM.N
    pyversion = (sys.version_info[0], sys.version_info[1])
    os.symlink('python', join(bin_dir, 'python%%d.%%d' %% pyversion))

    # Activate the virtualenv
    activate_this = join(bin_dir, 'activate_this.py')
    execfile(activate_this, dict(__file__=activate_this))

    import pip
    from pip.commands.install import InstallCommand
    import shlex

    # Debug logging for pip
    pip.logger.consumers = [(pip.logger.DEBUG, sys.stdout)]

    # Load version control modules for installing 'editables'
    pip.version_control()

    # Run pip install
    c = InstallCommand()
    reqs = shlex.split(' '.join(REQUIREMENTS))
    options, args = c.parser.parse_args(reqs)
    options.require_venv = True
    requirementSet = c.run(options, args)

    make_environment_relocatable(base)
'''


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '-v', '--verbose',
        action='append_const',
        const=-10,
        default=[logging.WARN],
        dest='v',
        help='Increase verbosity',
    )
    ap.add_argument(
        '-q', '--quiet',
        action='append_const',
        const=10,
        default=[logging.WARN],
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
            is ignored if --no-backup is used.
        '''
    )
    ap.add_argument(
        '--storage-dir',
        default=None,
        help='''
            Path to a directory in which terrarium bundles will be retrieved
            and stored for speedy re-installation. This will usually be a
            shared drive.
        ''',
    )
    ap.add_argument(
        '--digest-type',
        default='md5',
        help='Choose digest type (md5, sha, see hashlib)',
    )

    if boto:
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
            default=os.environ.get('S3_MAX_RETRIES', 1),
            help='Number of times to attempt a S3 operation before giving up',
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
        'exists': subparsers.add_parser(
            'exists',
            help='''
                Return exit code 0 if environment matches requirement set
            ''',
        ),
        'install': subparsers.add_parser(
            'install',
            help='''
                Replace current environment with the one given by the
                requirement set.
            ''',
        ),
    }

    for command in commands.values():
        command.add_argument('reqs', nargs=argparse.REMAINDER)
    return ap.parse_args()


def main():
    args = parse_args()

    logger.setLevel(sum(args.v))
    logger.addHandler(logging.StreamHandler())

    terrarium = Terrarium(args)

    if args.command == 'hash':
        print terrarium.digest
    elif args.command == 'exists':
        sys.exit(0)
    elif args.command == 'install':
        terrarium.install()

if __name__ == '__main__':
    main()
