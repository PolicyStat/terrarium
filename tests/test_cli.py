import os
import shlex
import subprocess
import sys
import unittest
import uuid


def run_command(command):
    params = {
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
    }
    result = subprocess.Popen(
        shlex.split(command),
        **params
    )
    stdout, stderr = result.communicate()
    sys.stdout.write(stdout)
    sys.stdout.write(stderr)
    return result.returncode, stdout.strip(), stderr.strip()


def terrarium(options):
    command = 'terrarium {}'.format(options)
    return run_command(command)


def pip(env, options):
    pip_path = os.path.join(env, 'bin', 'pip')
    command = '{} {}'.format(pip_path, options)
    return run_command(command)


def pip_freeze(env, strip_versions=True):
    rc, stdout, stderr = pip(env, 'freeze -l')
    assert rc == 0
    assert stderr == ''
    packages = stdout.split()
    if not strip_versions:
        return packages
    packages = [
        package.split('=', 1)[0]
        for package in packages
    ]
    return packages


class CommandLineInterfaceTestCase(unittest.TestCase):
    def setUp(self):
        self.target = _unique_name()

    def test_help(self):
        options = '--help'

        rc, stdout, stderr = terrarium(options)
        self.assertEqual(rc, 0)
        self.assertEqual(stderr, '')
        assert stdout.startswith('usage: terrarium')

    def test_no_params(self):
        options = ''

        rc, stdout, stderr = terrarium(options)
        self.assertEqual(rc, 2)
        self.assertEqual(stdout, '')
        assert stderr.startswith('usage: terrarium')
        assert stderr.endswith('terrarium: error: too few arguments')

    def test_install_to_target(self):
        file_name = _create_simple_requirements_file()

        options = '--target={} install {}'.format(self.target, file_name)

        expected_packages = ['terrarium', 'virtualenv']

        rc, stdout, stderr = terrarium(options)
        self.assertEqual(rc, 0)
        self.assertEqual(stdout, '')
        self.assertEqual(stderr, '')

        assert _file_exists(self.target, 'bin', 'activate')
        assert _file_exists(self.target, 'bin', 'terrarium')

        packages = pip_freeze(self.target)
        self.assertEqual(sorted(packages), sorted(expected_packages))

    def test_install_empty_requirements_creates_empty_virtualenv(self):
        file_name = _create_empty_requirements_file()

        options = '--target={} install {}'.format(self.target, file_name)

        expected_stdout = '[WARNING] wheel directory has no wheels'

        rc, stdout, stderr = terrarium(options)
        self.assertEqual(rc, 0)
        self.assertEqual(stderr, '')
        assert stdout.startswith(expected_stdout)
        assert _file_exists(self.target, 'bin', 'activate')

        packages = pip_freeze(self.target)
        self.assertEqual(packages, [])

    def test_install_with_requirements_file_that_includes_other_file(self):
        inner_file = _create_simple_requirements_file()
        requirement_include = '--requirement {}'.format(inner_file)
        file_name = _create_requirements_file([requirement_include])

        options = '--target={} install {}'.format(self.target, file_name)

        rc, stdout, stderr = terrarium(options)
        self.assertEqual(rc, 0)
        self.assertEqual(stdout, '')
        self.assertEqual(stderr, '')

        assert _file_exists(self.target, 'bin', 'activate')
        assert _file_exists(self.target, 'bin', 'terrarium')

    def test_install_will_backup_existing_target(self):
        file_name = _create_empty_requirements_file()

        assert not os.path.exists(self.target)

        # Create an existing target with some contents
        os.makedirs(self.target)
        _create_file('bar', self.target, 'foo')

        options = '--target={} install {}'.format(self.target, file_name)

        rc, stdout, stderr = terrarium(options)
        self.assertEqual(rc, 0)

        assert _file_exists(self.target, 'bin', 'activate')
        # The original existing target + contents was preserved
        assert _file_exists(self.target + '.bak', 'foo')

    def test_existing_backup_is_removed(self):
        file_name = _create_empty_requirements_file()
        backup_target = self.target + '.bak'

        # Create an existing target with some contents
        assert not os.path.exists(self.target)
        os.makedirs(self.target)
        _create_file('bar', self.target, 'original-target')

        # Create an existing backup target with some contents
        assert not os.path.exists(backup_target)
        os.makedirs(backup_target)
        _create_file('baz', backup_target, 'original-backup')

        options = '--target={} install {}'.format(self.target, file_name)

        rc, stdout, stderr = terrarium(options)
        self.assertEqual(rc, 0)

        assert _file_exists(self.target, 'bin', 'activate')
        # The original existing target + contents was preserved
        assert _file_exists(backup_target, 'original-target')
        assert not _file_exists(backup_target, 'original-backup')

    def test_install_with_backup_disabled(self):
        file_name = _create_empty_requirements_file()

        assert not os.path.exists(self.target)

        # Create an existing target with some contents
        os.makedirs(self.target)
        _create_file('bar', self.target, 'foo')

        options = '--target={} --no-backup install {}'.format(self.target, file_name)

        rc, stdout, stderr = terrarium(options)
        self.assertEqual(rc, 0)

        assert _file_exists(self.target, 'bin', 'activate')
        # The original target + contents is not backed up
        assert not os.path.exists(self.target + '.bak')

    def test_require_download(self):
        file_name = _create_empty_requirements_file()

        options = '--target={} --require-download install {}'.format(self.target, file_name)

        rc, stdout, stderr = terrarium(options)
        self.assertEqual(rc, 1)
        self.assertEqual(
            stdout,
            '[ERROR] Failed to download environment and download is required. '
            'Refusing to build a new environment.',
        )
        self.assertEqual(stderr, '')

    def test_require_download_with_empty_storage_dir(self):
        file_name = _create_empty_requirements_file()

        options = '--target={} --require-download --storage-dir=foo install {}'.format(
            self.target, file_name)

        rc, stdout, stderr = terrarium(options)
        self.assertEqual(rc, 1)
        self.assertEqual(
            stdout,
            '[ERROR] Failed to download environment and download is required. '
            'Refusing to build a new environment.',
        )
        self.assertEqual(stderr, '')

    def test_gcs_required_to_use_gcs_bucket(self):
        file_name = _create_empty_requirements_file()

        expected_stderr = (
            'terrarium: error: --gcs-bucket requires that you have '
            'gcloud installed, which does not appear to be the case'
        )

        options = '--target={} --gcs-bucket=foo install {}'.format(
            self.target, file_name)

        rc, stdout, stderr = terrarium(options)
        self.assertEqual(rc, 2)
        self.assertEqual(stdout, '')
        assert stderr.endswith(expected_stderr)

    def test_boto_required_to_use_s3_bucket(self):
        file_name = _create_empty_requirements_file()

        expected_stderr = (
            'terrarium: error: --s3-bucket requires that you have '
            'boto installed, which does not appear to be the case'
        )

        options = '--target={} --s3-bucket=foo install {}'.format(
            self.target, file_name)

        rc, stdout, stderr = terrarium(options)
        self.assertEqual(rc, 2)
        self.assertEqual(stdout, '')
        assert stderr.endswith(expected_stderr)


def _file_exists(*path_spec):
    return os.path.exists(os.path.join(*path_spec))


def _unique_name():
    return uuid.uuid4().hex


def _create_file(content, *path_spec):
    full_path = os.path.join(*path_spec)
    with open(full_path, 'w') as f:
        f.write(content)
    return full_path


def _create_requirements_file(requirements):
    file_name = '{}.txt'.format(_unique_name())
    content = ''.join([
        '{}\n'.format(requirement)
        for requirement in requirements
    ])
    return _create_file(content, file_name)


def _create_empty_requirements_file():
    return _create_requirements_file([])


def _create_simple_requirements_file():
    # TOX_PACKAGE will be the full path to the terrarium sdist.zip
    # Use it if it exists, because it will mean not waiting for pypi
    requirement = os.environ.get('TOX_PACKAGE', 'terrarium')
    return _create_requirements_file([requirement])
