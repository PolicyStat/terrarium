from __future__ import with_statement

import unittest
import subprocess
import shlex
import tempfile
import shutil
import os
import platform
import copy


class TerrariumTester(unittest.TestCase):
    def setUp(self):
        _, requirements = tempfile.mkstemp(prefix='test_terrarium_req-')
        target = tempfile.mkdtemp(prefix='test_terrarium_target-')
        self.initial_config = {
            'target': target,
            'storage_dir': tempfile.mkdtemp(prefix='test_terrarium_storage-'),
            'python': os.path.join(target, 'bin', 'python'),
            'terrarium': os.path.join(
                self._get_path_terrarium(),
                'terrarium',
                'terrarium.py',
            ),
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

    def _terrarium(self, command='', call_using_python=False):
        command = '%s %s %s' % (self.terrarium, self.opts, command)
        if call_using_python:
            output, return_code = self._python(command)
        else:
            output, return_code = self._run(
                command,
            )
        return output, return_code

    def _install(self, call_using_python=False, **kwargs):
        command = '-t %s install %s' % (
            self.target,
            self.requirements,
        )
        options = []
        for key, value in kwargs.items():
            options.append('--%s' % key.replace('_', '-'))
            if value is not None and value is not True:
                options.append(value)
        command = '%s %s' % (' '.join(options), command)
        output, return_code = self._terrarium(
            command,
            call_using_python=call_using_python,
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
        self._add_requirements(self._get_path_terrarium())

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


class TestTerrarium(TerrariumTester):
    def test_no_params(self):
        output, return_code = self._terrarium()
        self.assertEqual(return_code, 2)

    def test_help(self):
        output, return_code = self._terrarium('-h')
        self.assertEqual(return_code, 0)

    def test_install_empty_requirements(self):
        # Check that we can install an empty requirements file
        self.assertFalse(os.path.exists(self.python))
        output, return_code = self._install()
        self.assertEqual(return_code, 0)

        # check for activate script
        self.assertTrue(os.path.exists(
            os.path.join(self.target, 'bin', 'activate')
        ))

        # Check for python binary
        self.assertTrue(os.path.exists(self.python))

        # Check for python
        version = platform.python_version_tuple()
        pythonVV = 'python%s.%s' % (version[0], version[1])
        pythonVV_path = os.path.join(self.target, 'bin', pythonVV)
        self.assertTrue(os.path.exists(pythonVV_path))

        # Check for terrarium bootstrap script
        self.assertTrue(os.path.exists(
            os.path.join(self.target, 'bin', 'terrarium_bootstrap.py')
        ))

    def test_install_with_requirement(self):
        # Verify that a requirement can be used after it is installed
        self._add_test_requirement()
        output, return_code = self._install()
        self.assertEqual(return_code, 0)
        # Include a negative test as a control
        actual = self._can_import_requirements(
            'test_requirement',
            'asdasdasd',  # should not exist
        )
        expected = ['test_requirement']
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
        output, return_code = self._install()
        self.assertEqual(return_code, 0)
        output, return_code = self._install()
        self.assertEqual(return_code, 0)
        self.assertTrue(os.path.exists('%s.bak' % self.target))

    def test_install_replace_backup_removed(self):
        # Verify that --no-backup deletes the backup when replacing an existing
        # environment
        output, return_code = self._install()
        self.assertEqual(return_code, 0)
        output, return_code = self._install(no_backup=True)
        self.assertEqual(return_code, 0)
        self.assertFalse(os.path.exists('%s.bak' % self.target))

    def test_install_replace_old_backup_removed(self):
        # After doing two installs, we have test and test.bak. On a third
        # install, test.bak already exists, so renaming test to test.bak will
        # fail. Verify that the original test.bak is deleted, only the
        # most-recent backup is preserved
        output, return_code = self._install()
        self.assertEqual(return_code, 0)
        output, return_code = self._install()
        self.assertEqual(return_code, 0)
        self.assertTrue(os.path.exists('%s.bak' % self.target))
        output, return_code = self._install()
        self.assertEqual(return_code, 0)
        self.assertTrue(os.path.exists('%s.bak' % self.target))

    def test_install_old_backup_symlink(self):
        # Create a scenario where the backup (from a previous install) is
        # actually a symlink instead of a directory
        os.symlink(self.target, '%s.bak' % self.target)
        output, return_code = self._install()
        self.assertEqual(return_code, 0)
        output, return_code = self._install()
        self.assertEqual(return_code, 0)

    def test_install_replace_activate_virtualenv_path(self):
        # Verify that when replacing an existing virtualenv, the VIRTUAL_ENV
        # path in the activate script matches the original path of the
        # replaced environment
        output, return_code = self._install()
        self.assertEqual(return_code, 0)
        output, return_code = self._install()
        self.assertEqual(return_code, 0)

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
        output, return_code = self._install(storage_dir=self.storage_dir)
        self.assertEqual(return_code, 0)

        requirements_key = self._key()

        archive = os.path.join(self.storage_dir, requirements_key)
        self.assertTrue(os.path.exists(archive))

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

        output, return_code = self._install()
        self.assertEqual(return_code, 0)

        requirements_key = self._key()

        archive = os.path.join(self.storage_dir, requirements_key)
        self.assertTrue(os.path.exists(archive))

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
        output, return_code = self._install(
            storage_dir=self.storage_dir,
            no_upload=True,
        )
        self.assertEqual(return_code, 0)

        requirements_key = self._key()

        archive = os.path.join(self.storage_dir, requirements_key)
        self.assertFalse(os.path.exists(archive))

    def test_install_storage_dir_archive_extracted(self):
        # Verify that an archived terrarium can be later extracted and used

        # Build an archive
        self._add_test_requirement()
        output, return_code = self._install(storage_dir=self.storage_dir)
        self.assertEqual(return_code, 0)

        requirements_key = self._key()

        archive = os.path.join(self.storage_dir, requirements_key)
        self.assertTrue(os.path.exists(archive))

        # Just install a blank environment
        self._clear_requirements()

        # Replace the environment with something else
        output, return_code = self._install(no_backup=True)
        self.assertEqual(return_code, 0)

        actual = self._can_import_requirements(
            'test_requirement',  # Should not exist in the replacement
        )
        expected = []
        self.assertEqual(actual, expected)

        # Now attempt to install from the archive
        self._add_test_requirement()
        output, return_code = self._install(
            no_backup=True,
            storage_dir=self.storage_dir,
        )
        self.assertEqual(return_code, 0)
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

        output, return_code = self._install()
        self.assertEqual(return_code, 0)

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

        output, return_code = self._install(
            no_backup=True,
            call_using_python=True,
        )
        self.assertEqual(return_code, 0)
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

        output, return_code = self._install(
            storage_dir=self.storage_dir,
        )
        self.assertEqual(return_code, 0)

        # Use terrarium contained in the new environment
        config = self.config_push()
        config['terrarium'] = os.path.join(
            self.target,
            'bin',
            'terrarium',
        )

        output, return_code = self._install(
            no_backup=True,
            storage_dir=self.storage_dir,
        )
        self.assertEqual(return_code, 0)
        self.assertTrue(os.path.exists(self.python))

    def test_logging_output(self):
        self._add_test_requirement()
        self._add_terrarium_requirement()

        config = self.config_push()
        config['opts'] = ''

        output, return_code = self._install()
        self.assertEqual(return_code, 0)

        self.assertEqual(67, len(output[0].split('\n')))
        self.assertEqual(output[1], (
            'Building new environment\n'
            'Copying bootstrap script to new environment\n'
        ))
