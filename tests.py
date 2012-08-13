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
        self.target = tempfile.mkdtemp(prefix='test_terrarium')
        self.storage = tempfile.mkdtemp(prefix='test_terrarium')
        self.python = os.path.join(self.target, 'bin', 'python')
        _, self.requirements = tempfile.mkstemp(prefix='test_terrarium')

    def tearDown(self):
        shutil.rmtree(self.target)
        shutil.rmtree(self.storage)
        os.unlink(self.requirements)

    def _run(self, command, **kwargs):
        defaults = {
            'stdout': subprocess.PIPE,
            'stderr': subprocess.STDOUT,
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
        output, return_code = self._run(
            './terrarium/terrarium.py %s' % command
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
            if value is not None:
                options.append(value)
        command = ' '.join(options) + command
        output, return_code = self._terrarium(command)
        return output, return_code

    def _add_requirements(self, *requirements):
        with open(self.requirements, 'w') as f:
            f.writelines('\n'.join(requirements))

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
        self._add_requirements('decorator')
        output, return_code = self._install()
        self.assertEqual(return_code, 0)
        actual = self._can_import_requirements(
            'decorator',
            'asdasdasd',  # should not exist
        )
        expected = ['decorator']
        self.assertEqual(actual, expected)

    def test_hash_default_empty_requirements(self):
        command = 'hash %s' % (
            self.requirements,
        )
        output, return_code = self._terrarium(command)
        self.assertEqual(return_code, 0)
        self.assertEqual(
            output[0].strip(),
            'd41d8cd98f00b204e9800998ecf8427e',
        )
