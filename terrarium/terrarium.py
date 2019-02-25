#!/usr/bin/env python
from __future__ import absolute_import

import argparse
import glob
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile

try:
    import boto  # noqa
    import boto.s3.connection
    import boto.exception
except ImportError:
    boto = None  # noqa

# import google cloud storage lib
try:
    import gcloud.storage as gcs
except ImportError:
    gcs = None


logger = logging.getLogger(__name__)


PYTHONWARNINGS_IGNORE_PIP_PYTHON2_DEPRECATION = (
    'ignore:DEPRECATION::pip._internal.cli.base_command'
)

PYTHONWARNINGS = [
    PYTHONWARNINGS_IGNORE_PIP_PYTHON2_DEPRECATION,
]


class Terrarium(object):
    def __init__(self, args):
        self.args = args
        self._requirements = None

    def get_digest(self):
        return calculate_digest_for_requirements(
            digest_type=self.args.digest_type,
            requirements=self.requirements,
        )

    @property
    def requirements(self):
        if self._requirements is not None:
            return self._requirements
        lines = []
        for path in self.args.reqs:
            if os.path.exists(path):
                lines.extend(parse_requirements(path=path))
        self._requirements = lines
        return self._requirements

    def restore_previously_backed_up_environment(self):
        backup = self.get_backup_location()
        if not self.environment_exists(backup):
            raise RuntimeError(
                'Failed to restore backup. '
                "It doesn't appear to exist at {}".format(backup),
            )

        target = self.get_target_location()
        logger.info('Deleting environment at %s', target)
        rmtree(target)

        logger.info('Renaming %s to %s', backup, target)
        os.rename(backup, target)

    def get_target_location(self):
        return os.path.abspath(self.args.target)

    def get_backup_location(self, target=None):
        if target is None:
            target = self.get_target_location()
        return ''.join([target, self.args.backup_suffix])

    def environment_exists(self, env):
        path_to_activate = os.path.join(env, 'bin', 'activate')
        return os.path.exists(path_to_activate)

    def install(self):
        '''
        1. Attempt to download prebuilt environment
        2. Otherwise, attempt to build one (unless prohibited)
        3. If there's already an existing environment,
            temporarily move it out of the way.
        4. Install the environment from either #2 or #1
        5. If installation fails, restore the previous environment
        6. Otherwise, move the previous environment to the backup location
        '''
        target_path = self.get_target_location()
        backup_path = self.get_backup_location()

        existing_target = self.environment_exists(target_path)
        existing_backup = self.environment_exists(backup_path)

        downloaded = False
        if self.args.download:
            local_archive_path = self.download()
            if local_archive_path:
                downloaded = True

        new_env_created = False
        if not downloaded:
            if self.args.require_download:
                raise RuntimeError(
                    'Failed to download environment and download is required. '
                    'Refusing to build a new environment.'
                )
            local_archive_path = create_environment(self.requirements)
            if local_archive_path:
                new_env_created = True

        if not local_archive_path:
            raise RuntimeError('No environment was downloaded or created')

        target_path_temp = target_path + '.temp'
        try:
            if existing_target:
                os.rename(target_path, target_path_temp)
            install_environment(local_archive_path, target_path)
        except: # noqa - is there a better way to do this?
            if existing_target:
                # restore the original environment
                rmtree(target_path)
                os.rename(target_path_temp, target_path)
            raise

        if existing_backup:
            logger.debug('Removing backup path')
            rmtree(backup_path)

        if existing_target:
            if self.args.backup:
                os.rename(target_path_temp, backup_path)
            else:
                rmtree(target_path_temp)

        if new_env_created and self.args.upload:
            self.upload(local_archive_path)

    def _get_s3_bucket(self):
        conn = boto.s3.connection.S3Connection(
            aws_access_key_id=self.args.s3_access_key,
            aws_secret_access_key=self.args.s3_secret_key
        )
        return boto.s3.bucket.Bucket(conn, name=self.args.s3_bucket)

    def _get_gcs_bucket(self):
        conn = gcs.get_connection(
            self.args.gcs_project,
            self.args.gcs_client_email,
            self.args.gcs_private_key
        )
        return conn.get_bucket(self.args.gcs_bucket)

    def download(self):
        local_path = make_temp_file()

        # make remote key for extenal storage system
        remote_key = self.make_remote_key()

        if self.args.storage_dir:
            local_path = os.path.join(self.args.storage_dir, remote_key)
            if os.path.exists(local_path):
                return local_path

        if self._download_from_s3(remote_key, local_path):
            return local_path

        if self._download_from_gcs(remote_key, local_path):
            return local_path

    def _download_from_s3(self, remote_key, local_path):
        if not boto or not self.args.s3_bucket:
            return
        bucket = self._get_s3_bucket()
        key = bucket.get_key(remote_key)
        if not key:
            return
        logger.info(
            'Downloading %s/%s from S3 ...',
            self.args.s3_bucket,
            remote_key,
        )
        key.get_contents_to_filename(local_path)
        return True

    def _download_from_gcs(self, remote_key, local_path):
        if not gcs or not self.args.gcs_bucket:
            return
        bucket = self._get_gcs_bucket()
        blob = bucket.get_key(remote_key)
        if not blob:
            return
        logger.info(
            'Downloading %s/%s from Google Cloud Storage ...',
            self.args.gcs_bucket,
            remote_key,
        )
        blob.download_to_file(local_path)
        return True

    def make_remote_key(self):
        import platform
        major, minor, patch = platform.python_version_tuple()
        context = {
            'digest': self.get_digest(),
            'python_vmajor': major,
            'python_vminor': minor,
            'python_vpatch': patch,
            'arch': platform.machine(),
        }
        return self.args.remote_key_format % context

    def upload_to_storage_dir(self, archive, storage_dir):
        logger.info('Copying environment to storage directory')
        dest = os.path.join(storage_dir, self.make_remote_key())
        if os.path.exists(dest):
            raise RuntimeError(
                'Environment already exists at {}'.format(dest),
            )
        temp = make_temp_file(dir=storage_dir)
        shutil.copyfile(archive, temp)
        os.rename(temp, dest)
        logger.info('Archive copied to storage directory')

    def upload_to_s3(self, archive):
        logger.info('Uploading environment to S3')
        attempts = 0
        bucket = self._get_s3_bucket()
        key = bucket.new_key(self.make_remote_key())

        while True:
            try:
                key.set_contents_from_filename(archive)
                logger.debug('upload finished')
                return True
            except Exception:
                attempts = attempts + 1
                logger.warning('There was an error uploading the file')
                if attempts > self.args.s3_max_retries:
                    logger.error('Attempted to upload archive to S3, but failed')
                    raise
                else:
                    logger.info('Retrying S3 upload')

    def upload_to_gcs(self, archive):
        logger.info('Uploading environment to Google Cloud Storage')
        attempts = 0
        bucket = self._get_gcs_bucket()
        blob = bucket.new_key(self.make_remote_key())

        while True:
            try:
                blob.upload_from_filename(archive)
                logger.debug('upload finished')
                return True
            except Exception:
                attempts = attempts + 1
                logger.warning('There was an error uploading the file')
                if attempts > self.args.gcs_max_retries:
                    logger.error(
                        'Attempted to upload archive to Google Cloud Storage, '
                        'but failed'
                    )
                    raise
                else:
                    logger.info('Retrying Google Cloud Storage upload')

    def upload(self, archive):
        if self.args.storage_dir:
            self.upload_to_storage_dir(archive, self.args.storage_dir)
        if boto and self.args.s3_bucket:
            self.upload_to_s3(archive)
        if gcs and self.args.gcs_bucket:
            self.upload_to_gcs(archive)


def define_args():
    import terrarium
    ap = argparse.ArgumentParser(
        prog='terrarium',
        version=terrarium.__version__,
    )
    ap.add_argument(
        '-V', '--verbose',
        action='count',
        default=0,
        dest='verbose_count',
        help='Increase verbosity. Default shows only warnings and errors.',
    )
    ap.add_argument(
        '-q', '--quiet',
        action='store_true',
        default=False,
        dest='quiet',
        help='Silence output completely',
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
            attempt to download an existing terrarium environment instead of
            building a new one. Using --no-download forces terrarium to build a
            new environment.
        ''',
    )
    ap.add_argument(
        '--require-download',
        default=False,
        action='store_true',
        help='''
            If we fail to download a terrarium environment from the storage
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
            Path to a directory in which terrarium environments will be retrieved
            and stored for speedy re-installation. This will usually be a
            shared drive.
        ''',
    )
    ap.add_argument(
        '--digest-type',
        default='md5',
        help='Choose digest type (md5, sha, see hashlib). Default is md5.',
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

    # gcs relavent arguments
    ap.add_argument(
        '--gcs-bucket',
        default=os.environ.get('GCS_BUCKET', None),
        help='''
            Google Cloud Storage bucket name.
            Defaults to GCS_BUCKET env variable.
        '''
    )
    ap.add_argument(
        '--gcs-project',
        default=os.environ.get('GCS_PROJECT', None),
        help='''
            Google Cloud Storage project.
            Defaults to GCS_PROJECT env variable.
        '''
    )
    ap.add_argument(
        '--gcs-client-email',
        default=os.environ.get('GCS_CLIENT_EMAIL', None),
        help='''
            Google Cloud Storage client email.
            Defaults to GCS_CLIENT_EMAIL env variable.
        '''
    )
    ap.add_argument(
        '--gcs-private-key',
        default=os.environ.get('GCS_PRIVATE_KEY', None),
        help='''
            Google Cloud Storage private key.
            Defaults to GCS_PRIVATE_KEY env variable.
        '''
    )
    ap.add_argument(
        '--gcs-max-retries',
        default=os.environ.get('GCS_MAX_RETRIES', 3),
        help='''
            Number of times to attempt a GCS operation before giving up.
            Default is 3.
        '''
    )

    subparsers = ap.add_subparsers(
        title='Basic Commands',
        dest='command',
    )
    subparsers.required = True

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
    return ap


def get_displayable_args(args):
    sensitive_arguments = set([
        's3_access_key',
        's3_secret_key',
        'gcs_client_email',
        'gcs_private_key',
    ])
    for key, val in sorted(args.__dict__.items()):
        if val is not None and key in sensitive_arguments:
            val = '*****'
        yield key, val


def parse_args(ap):
    args = ap.parse_args()
    assert args.__class__._get_kwargs
    args.__class__._get_kwargs = get_displayable_args

    if not boto and args.s3_bucket is not None:
        ap.error(
            '--s3-bucket requires that you have boto installed, '
            'which does not appear to be the case'
        )

    if not gcs and args.gcs_bucket is not None:
        ap.error(
            '--gcs-bucket requires that you have gcloud installed, '
            'which does not appear to be the case'
        )

    return args


def call_subprocess(command, log_level=logging.INFO):
    logger.debug('call_subprocess: %s', command)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    while process.poll() is None:
        while True:
            stdout = process.stdout.readline()
            stderr = process.stderr.readline()
            if not stdout and not stderr:
                break
            stdout = stdout.strip()
            if stdout:
                logger.log(log_level, stdout.decode())
            stderr = stderr.strip()
            if stderr:
                logger.warning(stderr.decode())

    rc = process.returncode
    if rc:
        raise RuntimeError('{cmd} exited with code {code}'.format(
            cmd=command[0],
            code=rc,
        ))


def create_virtualenv(directory):
    command = [
        'virtualenv',
        directory,
    ]
    call_subprocess(command)


def pip_install_wheels(virtualenv, wheel_dir):
    logger.debug('pip_install_wheels: %s, %s', virtualenv, wheel_dir)
    pip_path = os.path.join(virtualenv, 'bin', 'pip')
    requirements_path = os.path.join(wheel_dir, 'requirements.txt')

    # Copy requirements.txt to the virtualenv
    shutil.copyfile(
        requirements_path,
        os.path.join(virtualenv, 'requirements.txt'),
    )

    # note: --find-links + --requirement
    # the reason the command below isn't using --find-links + --requirement is
    # because of how pip behaves when requirements.txt contains a remote source
    # requirement. In this situation, pip ignores the wheel in the wheel_dir
    # and instead downloads the requirement from the source

    wheels = glob.glob(os.path.join(wheel_dir, '*.whl'))
    if not wheels:
        logger.warning('wheel directory has no wheels: %s', wheel_dir)
        return

    command = [
        pip_path,
        'install',
        '--no-index',
        '--no-cache-dir',
    ]
    command.extend(wheels)
    call_subprocess(command)


def install_environment(local_archive_path, local_directory):
    logger.debug('install_environment: %s, %s', local_archive_path, local_directory)
    wheel_dir = tempfile.mkdtemp(prefix='terrarium-wheel-')
    extract_tar_archive(local_archive_path, wheel_dir)
    requirements_path = os.path.join(wheel_dir, 'requirements.txt')
    if not os.path.exists(requirements_path):
        raise RuntimeError('Environment is missing requirements.txt')

    create_virtualenv(local_directory)
    pip_install_wheels(local_directory, wheel_dir)


def pip_wheel(wheel_dir, requirements):
    requirements_path = os.path.join(wheel_dir, 'requirements.txt')
    with open(requirements_path, 'w') as f:
        f.write(flatten_requirements(requirements))

    command = [
        'pip',
        'wheel',
        '--wheel-dir', wheel_dir,
        '--requirement', requirements_path,
    ]
    call_subprocess(command)


def flatten_requirements(requirements):
    if not requirements:
        return ''
    return '\n'.join(requirements) + '\n'


def create_environment(requirements, compress=True):
    logger.debug('create_environment')
    wheel_dir = tempfile.mkdtemp(prefix='terrarium-wheel-')
    pip_wheel(wheel_dir, requirements)
    archive_path = create_tar_archive(wheel_dir)
    if not compress:
        return archive_path
    compressed_archive_path = gzip_compress(archive_path)
    return compressed_archive_path


def calculate_digest_for_requirements(digest_type, requirements):
    h = hashlib.new(digest_type)
    h.update(flatten_requirements(requirements))
    return h.hexdigest()


def gzip_compress(target):
    call_subprocess(['gzip', target])
    return '{}.gz'.format(target)


def create_tar_archive(directory):
    logger.debug('create_tar_archive: %s', directory)
    archive_path = make_temp_file()
    command = [
        'tar',
        '--create',
        '--file', archive_path,
        '--directory', directory,
        '.'
    ]
    call_subprocess(command)
    return archive_path


# http://www.astro.keele.ac.uk/oldusers/rno/Computing/File_magic.html
MAGIC_NUM = {
    # magic code, offset
    'ELF': ('.ELF', 0),
    'GZIP': ('\x1f\x8b', 0),
    'BZIP': ('\x42\x5a', 0),
    'TAR': ('ustar', 257),
}


def detect_file_type(path):
    'Examine the first few bytes of the given path to detect the file type'
    with open(path) as f:
        for file_type, magic in MAGIC_NUM.items():
            f.seek(magic[1])
            if magic[0] == f.read(len(magic[0])):
                return file_type
    return None


def extract_tar_archive(archive, target):
    logger.debug('extract_tar_archive: %s, %s', archive, target)
    archive_type = detect_file_type(archive)

    compression_map = {
        'GZIP': '--gzip',
        'BZIP': '--bzip2',
        'TAR': '',
    }

    compression_opt = compression_map.get(archive_type)

    if compression_opt is None:
        raise RuntimeError(
            'Failed to extract archive, unknown or unsupported file type',
        )

    if not os.path.exists(target):
        os.mkdir(target)
    command = [
        'tar',
        '--extract',
        compression_opt,
        '--file', archive,
        '--directory', target,
    ]
    call_subprocess(command)


def parse_requirements(path, ignore_comments=True):
    logger.debug('parse_requirements: %s', path)
    with open(path) as f:
        lines = f.readlines()
    for line in lines:
        line = line.strip()
        if ignore_comments and line.startswith('#'):
            continue
        if line.startswith(('-r', '--requirement')):
            _, ref_name = line.split()
            ref_path = os.path.join(os.path.dirname(path), ref_name)
            ref_lines = parse_requirements(
                ref_path,
                ignore_comments=ignore_comments,
            )
            for inner_line in ref_lines:
                yield inner_line
        else:
            yield line


def rmtree(path):
    if not os.path.exists(path):
        return
    logger.debug('rmtree: %s', path)
    try:
        if os.path.islink(path):
            os.unlink(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.unlink(path)
    except OSError as why:
        raise RuntimeError(
            'Failed to remove {path}. '
            'Make sure you have permissions to this path. {why}'.format(
                path=path,
                why=why,
            )
        )


def make_temp_file(**kwargs):
    prefix = kwargs.pop('prefix', 'terrarium-')
    fd, path_to_file = tempfile.mkstemp(prefix=prefix, **kwargs)
    os.close(fd)
    return path_to_file


def initialize_logging(args):
    if args.quiet:
        logger.disabled = True
    else:
        level = logging.WARNING
        level -= args.verbose_count * 10
        level = max(level, logging.DEBUG)
        logger.setLevel(level)


def update_python_warnings():
    existing_warnings = os.environ.get('PYTHONWARNINGS', '').strip()
    warnings = []
    if existing_warnings:
        warnings = existing_warnings.split(',')
    warnings.extend(PYTHONWARNINGS)
    os.environ['PYTHONWARNINGS'] = ','.join(warnings)


def main():
    update_python_warnings()

    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG,
        format='[%(levelname)s] %(message)s',
    )

    ap = define_args()
    args = parse_args(ap)
    initialize_logging(args)

    logger.debug('Initialized with %s', args)

    terrarium = Terrarium(args)

    try:
        if args.command == 'hash':
            digest = terrarium.get_digest()
            sys.stdout.write('{}\n'.format(digest))
        if args.command == 'key':
            key = terrarium.make_remote_key()
            sys.stdout.write('{}\n'.format(key))
        elif args.command == 'install':
            terrarium.install()
        elif args.command == 'revert':
            terrarium.restore_previously_backed_up_environment()
    except RuntimeError as e:
        logger.error(e.message)
        sys.exit(1)


if __name__ == '__main__':
    main()
