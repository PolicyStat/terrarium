from __future__ import with_statement

import unittest
import subprocess
import shlex
import tempfile
import shutil
import os
import platform


class TestTerrarium(unittest.TestCase):
    def setUp(self):
        self.target = tempfile.mkdtemp(prefix='test_terrarium_target-')
        self.storage_dir = tempfile.mkdtemp(prefix='test_terrarium_storage-')
        self.python = os.path.join(self.target, 'bin', 'python')
        _, self.requirements = tempfile.mkstemp(prefix='test_terrarium_req-')

    def tearDown(self):
        shutil.rmtree(self.target)
        if os.path.exists('%s.bak' % self.target):
            shutil.rmtree('%s.bak' % self.target)
        shutil.rmtree(self.storage_dir)
        os.unlink(self.requirements)

    def _run(self, command, **kwargs):
        defaults = {
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
        }
        defaults.update(kwargs)
        kwargs = defaults
        params = shlex.split(command)
        result = subprocess.Popen(params, **kwargs)
        output = result.communicate()
        return output, result.returncode

    def _python(self, command='', **kwargs):
        output, return_code = self._run(
            '%s %s' % (
                self.python,
                command,
            )
        )
        return output, return_code

    def _terrarium(self, command='', **kwargs):
        terrarium = self._get_path(
            '..',
            'terrarium',
            'terrarium.py',
        )
        output, return_code = self._run(
            '%s -vv %s' % (terrarium, command)
        )
        return output, return_code

    def _install(self, **kwargs):
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
        output, return_code = self._terrarium(command)
        return output, return_code

    def _key(self, **kwargs):
        command = 'key %s' % (
            self.requirements,
        )
        output, return_code = self._terrarium(command)
        self.assertEqual(return_code, 0)
        requirements_key = output[0].strip()
        return requirements_key

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

    def _add_requirements(self, *requirements):
        with open(self.requirements, 'w') as f:
            f.writelines('\n'.join(requirements))

    def _add_test_requirement(self):
        test_requirement = self._get_path('fixtures', 'test_requirement')
        self._add_requirements(test_requirement)

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

    def test_no_params(self):
        output, return_code = self._terrarium()
        self.assertEqual(return_code, 2)

    def test_help(self):
        output, return_code = self._terrarium('-h')
        self.assertEqual(return_code, 0)

    def test_install_empty_requirements(self):
        # Check that we can install an empty requirements file
        self.assertTrue(not os.path.exists(self.python))
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
