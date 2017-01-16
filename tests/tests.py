from __future__ import with_statement

import unittest
import subprocess
import shlex
import tempfile
import shutil
import os
import platform
import copy
import sys


class TerrariumTester(unittest.TestCase):

    def setUp(self):
        _, requirements = tempfile.mkstemp(prefix='test_terrarium_req-')
        target = tempfile.mkdtemp(prefix='test_terrarium_target-')
        self.initial_config = {
            'target': target,
            'storage_dir': tempfile.mkdtemp(prefix='test_terrarium_storage-'),
            'python': os.path.join(target, 'bin', 'python'),
            'terrarium': 'terrarium',
            'requirements': requirements,
            'environ': {},
            'opts': '',
        }
        self.configs = []
        self.config_push(initial=True)

    @property
    def config(self):
        return self.configs[0]

    @property
    def target(self):
        return self.config['target']

    @property
    def storage_dir(self):
        return self.config['storage_dir']

    @property
    def python(self):
        return self.config['python']

    @property
    def terrarium(self):
        return self.config['terrarium']

    @property
    def environ(self):
        return self.config['environ']

    @property
    def requirements(self):
        return self.config['requirements']

    @property
    def opts(self):
        return self.config['opts']

    def config_pop(self):
        return self.configs.pop()

    def config_push(self, initial=True):
        if initial:
            config = copy.deepcopy(self.initial_config)
        else:
            config = copy.deepcopy(self.configs[0])
        self.configs.insert(0, config)
        return config

    def tearDown(self):
        for config in self.configs:
            if os.path.exists(config['target']):
                shutil.rmtree(config['target'])
            if os.path.exists('%s.bak' % config['target']):
                shutil.rmtree('%s.bak' % config['target'])
            if os.path.exists(config['storage_dir']):
                shutil.rmtree(config['storage_dir'])
            if os.path.exists(config['requirements']):
                os.unlink(config['requirements'])

    def _run(self, command, **kwargs):
        defaults = {
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
        }
        defaults.update(kwargs)
        env = {}
        if self.environ:
            env.update(os.environ)
            env.update(self.environ)
            defaults['env'] = env
        kwargs = defaults
        sys.stdout.write('Executing "%s"\n' % command)
        params = shlex.split(command)
        result = subprocess.Popen(params, **kwargs)
        output = result.communicate()
        return output, result.returncode

    def _get_path(self, *paths):
        paths = list(paths)
        paths.insert(
            0,
            os.path.dirname(
                os.path.abspath(__file__)
            ),
        )
        return os.path.abspath(
            os.path.join(*paths)
        )

    def _get_path_terrarium(self):
        return self._get_path('..')

    def _python(self, command='', **kwargs):
        output, return_code = self._run(
            '%s %s' % (
                self.python,
                command,
            )
        )
        return output, return_code

    def _terrarium(self, command='', call_using_python=False, **kwargs):
        options = []
        for key, value in kwargs.items():
            options.append('--%s' % key.replace('_', '-'))
            if value is not None and value is not True:
                options.append(value)
        command = ' '.join([
            self.terrarium,
            ' '.join(options),
            self.opts,
            command,
        ])
        if call_using_python:
            output, return_code = self._python(command)
        else:
            output, return_code = self._run(
                command,
            )
        return output, return_code

    def _install(self, call_using_python=False, **kwargs):
        command = 'install %s' % (
            self.requirements,
        )
        output, return_code = self._terrarium(
            command,
            target=self.target,
            call_using_python=call_using_python,
            **kwargs
        )
        return output, return_code

    def _key(self, **kwargs):
        command = 'key %s' % (
            self.requirements,
        )
        output, return_code = self._terrarium(command)
        self.assertEqual(return_code, 0)
        requirements_key = output[0].strip()
        return requirements_key

    def _add_requirements(self, *requirements):
        with open(self.requirements, 'a') as f:
            f.writelines('\n'.join(requirements))
            f.write('\n')

    def _add_test_requirement(self):
        test_requirement = self._get_path('fixtures', 'test_requirement')
        self._add_requirements(test_requirement)

    def _add_terrarium_requirement(self):
        import virtualenv
        self._add_requirements(
            self._get_path_terrarium(),
            'virtualenv==%s' % virtualenv.virtualenv_version
        )

    def _clear_requirements(self, *requirements):
        with open(self.requirements, 'w'):
            pass

    def _can_import_requirements(self, *requirements):
        imported = []
        for r in requirements:
            output, return_code = self._python(
                '-c "import %s"' % r
            )
            if return_code == 0:
                imported.append(r)
        return imported

    def assertInstall(self, *args, **kwargs):
        expected_return_code = kwargs.pop('return_code', 0)
        output, return_code = self._install(*args, **kwargs)
        # Print output so it is displayed in the event of an error
        sys.stdout.write('\n'.join(output))
        self.assertEqual(return_code, expected_return_code)
        return output

    def assertExists(self, path):
        self.assertTrue(os.path.exists(path))

    def assertNotExists(self, path):
        self.assertFalse(os.path.exists(path))


class TestTerrarium(TerrariumTester):

    def test_no_params(self):
        output, return_code = self._terrarium()
        self.assertEqual(return_code, 2)

    def test_help(self):
        output, return_code = self._terrarium('-h')
        self.assertEqual(return_code, 0)

    def test_install_empty_requirements(self):
        # Check that we can install an empty requirements file
        self.assertNotExists(self.python)
        self.assertInstall()

        # check for activate script
        self.assertExists(
            os.path.join(self.target, 'bin', 'activate')
        )

        # Check for python binary
        self.assertExists(self.python)

        # Check for python
        version = platform.python_version_tuple()
        pythonVV = 'python%s.%s' % (version[0], version[1])
        self.assertExists(
            os.path.join(self.target, 'bin', pythonVV)
        )

        # Check for terrarium bootstrap script
        self.assertExists(
            os.path.join(self.target, 'bin', 'terrarium_bootstrap.py')
        )

    def test_install_with_requirement(self):
        # Verify that a requirement can be used after it is installed
        self._add_test_requirement()
        self.assertInstall()
        # Include a negative test as a control
        actual = self._can_import_requirements(
            'test_requirement',
            'asdasdasd',  # should not exist
        )
        expected = ['test_requirement']
        self.assertEqual(actual, expected)

    def test_install_requirements_with_dependency(self):
        """ This test involves a requirements file with two items,
            test_requirement and foo_requirement. foo_requirement
            has test_requirement as a dependency. We check that,
            if test_requirement comes first in the requirements,
            the install of foo_requirement will be successful.
        """
        self._add_requirements(
            self._get_path('fixtures', 'test_requirement'),
            self._get_path('fixtures', 'foo_requirement'),
        )
        self.assertInstall()
        actual = self._can_import_requirements(
            'test_requirement',
            'foo_requirement',
        )
        expected = ['test_requirement', 'foo_requirement']
        self.assertEqual(actual, expected)

    def test_install_with_requirement_comments(self):
        # Verify that a requirement file with comment lines can be used.
        self._add_requirements(
            self._get_path('fixtures', 'test_requirement'),
            '# This is a comment line in the requirements file.',
        )
        self.assertInstall()
        actual = self._can_import_requirements(
            'test_requirement',
        )
        expected = ['test_requirement']
        self.assertEqual(actual, expected)

    def test_install_editable_with_hash_egg_name(self):
        # Verify that a requirement file with a hash egg name can be used and
        # is not confused with a comment
        # If the #egg=foobar is removed, pip will fail
        self._add_requirements(
            '-e git+git://github.com/PolicyStat/terrarium.git#egg=foobar',
        )
        self.assertInstall()
        actual = self._can_import_requirements(
            'terrarium',
        )
        expected = ['terrarium']
        self.assertEqual(actual, expected)

    def test_hash_default_empty_requirements(self):
        # Verify that the hash of an empty requirements file is predictable
        command = 'hash %s' % (
            self.requirements,
        )
        output, return_code = self._terrarium(command)
        self.assertEqual(return_code, 0)
        self.assertEqual(
            output[0].strip(),
            'd41d8cd98f00b204e9800998ecf8427e',
        )

    def test_install_replace_backup_exists(self):
        # Verify that a backup of the old environment is created when replacing
        # it
        self.assertInstall()
        self.assertInstall()
        self.assertExists('%s.bak' % self.target)

    def test_install_no_backup(self):
        # Verify that --no-backup deletes the backup when replacing an existing
        # environment
        self.assertInstall()
        self.assertInstall(no_backup=True)
        self.assertNotExists('%s.bak' % self.target)

    def test_install_replace_old_backup_removed(self):
        # After doing two installs, we have test and test.bak. On a third
        # install, test.bak already exists, so renaming test to test.bak will
        # fail. Verify that the original test.bak is deleted, only the
        # most-recent backup is preserved
        self.assertInstall()
        self.assertInstall()
        self.assertExists('%s.bak' % self.target)
        self.assertInstall()
        self.assertExists('%s.bak' % self.target)

    def test_install_old_backup_symlink(self):
        # Create a scenario where the backup (from a previous install) is
        # actually a symlink instead of a directory
        os.symlink(self.target, '%s.bak' % self.target)
        self.assertInstall()
        self.assertInstall()

    def test_install_replace_activate_virtualenv_path(self):
        # Verify that when replacing an existing virtualenv, the VIRTUAL_ENV
        # path in the activate script matches the original path of the
        # replaced environment
        self.assertInstall()
        self.assertInstall()

        activate = os.path.join(self.target, 'bin', 'activate')
        with open(activate) as f:
            contents = f.read()
            self.assertTrue(
                'VIRTUAL_ENV="%s"' % self.target
                in contents
            )

    def test_install_storage_dir_archive(self):
        # Verify that the --storage-dir option causes terrarium create an
        # archive for the given requirement set
        self.assertInstall(storage_dir=self.storage_dir)

        requirements_key = self._key()

        archive = os.path.join(self.storage_dir, requirements_key)
        self.assertExists(archive)

        # Verify that the environment is returned to a usable state
        activate = os.path.join(self.target, 'bin', 'activate')
        with open(activate) as f:
            contents = f.read()
            self.assertTrue(
                'VIRTUAL_ENV="%s"' % self.target
                in contents
            )

    def test_install_storage_dir_archive_by_environ(self):
        # Verify that the --storage-dir option causes terrarium create an
        # archive for the given requirement set
        self.environ['TERRARIUM_STORAGE_DIR'] = self.storage_dir

        self.assertInstall()

        requirements_key = self._key()

        archive = os.path.join(self.storage_dir, requirements_key)
        self.assertExists(archive)

        # Verify that the environment is returned to a usable state
        activate = os.path.join(self.target, 'bin', 'activate')
        with open(activate) as f:
            contents = f.read()
            self.assertTrue(
                'VIRTUAL_ENV="%s"' % self.target
                in contents
            )

    def test_install_storage_dir_no_archive(self):
        # Verify that the --no-upload option causes terrarium to not create an
        # archive for the given requirement set
        self.assertInstall(
            storage_dir=self.storage_dir,
            no_upload=True,
        )

        requirements_key = self._key()

        archive = os.path.join(self.storage_dir, requirements_key)
        self.assertNotExists(archive)

    def test_install_storage_dir_archive_extracted(self):
        # Verify that an archived terrarium can be later extracted and used

        # Build an archive
        self._add_test_requirement()
        self.assertInstall(storage_dir=self.storage_dir)

        requirements_key = self._key()

        archive = os.path.join(self.storage_dir, requirements_key)
        self.assertExists(archive)

        # Just install a blank environment
        self._clear_requirements()

        # Replace the environment with something else
        self.assertInstall(no_backup=True)

        actual = self._can_import_requirements(
            'test_requirement',  # Should not exist in the replacement
        )
        expected = []
        self.assertEqual(actual, expected)

        # Now attempt to install from the archive
        self._add_test_requirement()
        output = self.assertInstall(
            no_backup=True,
            storage_dir=self.storage_dir,
        )
        self.assertEqual(output[0], '')
        self.assertTrue('Extracting terrarium bundle' in output[1])

        actual = self._can_import_requirements(
            'test_requirement',  # Should exist now
        )
        expected = ['test_requirement']
        self.assertEqual(actual, expected)

    def test_install_with_terrarium_in_environment(self):
        # Verify that terrarium can replace an existing environment, the one
        # that terrarium executes from

        self._add_test_requirement()
        self._add_terrarium_requirement()

        self.assertInstall()

        actual = self._can_import_requirements(
            'test_requirement',
            'terrarium',
        )
        expected = [
            'test_requirement',
            'terrarium',
        ]
        self.assertEqual(actual, expected)

        # Use terrarium contained in the new environment
        config = self.config_push()
        config['terrarium'] = os.path.join(
            self.target,
            'bin',
            'terrarium',
        )

        output = self.assertInstall(
            no_backup=True,
            call_using_python=True,
        )
        self.assertFalse('Requirement already satisfied' in output[0])

        actual = self._can_import_requirements(
            'test_requirement',
            'terrarium',
        )
        expected = [
            'test_requirement',
            'terrarium',
        ]
        self.assertEqual(actual, expected)

    def test_extract_with_terrarium_in_environment(self):
        # Verify that terrarium can install after being extracted from an
        # archive that was previously installed

        self._add_terrarium_requirement()

        self.assertInstall(storage_dir=self.storage_dir)

        # Use terrarium contained in the new environment
        config = self.config_push()
        config['terrarium'] = os.path.join(
            self.target,
            'bin',
            'terrarium',
        )

        self.assertInstall(
            no_backup=True,
            storage_dir=self.storage_dir,
        )
        self.assertExists(self.python)

    def test_logging_output(self):
        self._add_test_requirement()
        self._add_terrarium_requirement()

        config = self.config_push()
        config['opts'] = ''

        output = self.assertInstall()

        self.assertNotEqual('', output[0])
        self.assertEqual(output[1], (
            'Building new environment\n'
            'Copying bootstrap script to new environment\n'
            'Terrarium is finished\n'
        ))

    def test_boto_required_to_use_s3_bucket(self):
        self._add_test_requirement()

        output = self.assertInstall(
            return_code=2,
            s3_bucket='bucket',
        )
        self.assertTrue(
            'error: --s3-bucket requires that you have boto installed, '
            'which does not appear to be the case'
            in output[1]
        )

    def test_gcs_required_to_use_gcs_bucket(self):
        self._add_test_requirement()

        output = self.assertInstall(
            return_code=2,
            gcs_bucket='bucket',
        )
        self.assertTrue(
            'error: --gcs-bucket requires that you have gcloud installed, '
            'which does not appear to be the case'
            in output[1]
        )

    def test_sensitive_arguments_are_sensitive(self):
        command = 'hash %s' % (
            self.requirements,
        )
        output, return_code = self._terrarium(
            command,
            verbose=True,
            s3_secret_key='should_not_appear',
            s3_access_key='do_not_show_me',
        )
        self.assertEqual(return_code, 0)
        self.assertTrue(
            output[1].startswith('Initialized with Namespace')
        )
        self.assertTrue(
            'should_not_appear' not in output[1]
        )

        self.assertTrue(
            'do_not_show_me' not in output[1]
        )

    def test_restore_previously_backed_up_environment(self):
        output, return_code = self._terrarium(
            'revert',
            target=self.target,
        )
        self.assertEqual(return_code, 1)

        self._add_test_requirement()
        self.assertInstall()
        with open(os.path.join(self.target, 'foo'), 'w') as f:
            f.write('bar')
        self.assertInstall()
        with open(os.path.join(self.target, 'moo'), 'w') as f:
            f.write('cow')
        self.assertExists('%s.bak' % self.target)
        output, return_code = self._terrarium(
            'revert',
            target=self.target,
        )
        self.assertEqual(return_code, 0)
        self.assertNotExists('%s.bak' % self.target)
        self.assertExists(os.path.join(self.target, 'foo'))
        self.assertNotExists(os.path.join(self.target, 'moo'))

    def test_require_download(self):
        self._add_test_requirement()

        output = self.assertInstall(
            return_code=1,
            storage_dir=self.storage_dir,
            require_download=True,
        )
        self.assertEqual(
            output[1],
            'Download archive failed\n'
            'Failed to download bundle and download is required. '
            'Refusing to build a new bundle.\n',
        )
        self.assertNotExists(self.python)
