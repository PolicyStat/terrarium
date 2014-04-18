import codecs
import os
import re
import sys
from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))

classifiers = [
    'Development Status :: 4 - Beta',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Operating System :: POSIX :: Linux',
    'Operating System :: Unix',
    'Programming Language :: Python',
    'Programming Language :: Python :: 2',
    'Programming Language :: Python :: 2.6',
    'Programming Language :: Python :: 2.7',
    'Topic :: Utilities',
]


def read(*parts):
    # intentionally *not* adding an encoding option to open, See:
    # https://github.com/pypa/virtualenv/issues/201#issuecomment-3145690
    return codecs.open(os.path.join(here, *parts), 'r').read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(
        r"^__version__ = ['\"]([^'\"]*)['\"]",
        version_file,
        re.M,
    )
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


def main():
    python_version = sys.version_info[:2]
    install_requires = [
        'virtualenv>=1.7.2,<=1.9.1',
    ]
    if python_version < (2, 7) or (3, 0) <= python_version <= (3, 1):
        install_requires += ['argparse']

    setup(
        name='terrarium',
        version=find_version('terrarium', '__init__.py'),
        author='Kyle Gibson',
        author_email='kyle.gibson@frozenonline.com',
        description='Package and ship relocatable python virtualenvs',
        license='BSD',
        url='http://github.com/policystat/terrarium',
        packages=['terrarium'],
        long_description=read('README.rst'),
        install_requires=install_requires,
        entry_points={
            'console_scripts':
                ['terrarium = terrarium.terrarium:main']
        },
        classifiers=classifiers,
        zip_safe=False,
    )


if __name__ == '__main__':
    main()
