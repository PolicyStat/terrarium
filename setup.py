import os
from setuptools import setup

# Update here and in terrarium.py
version = '1.0.0rc3'

classifiers = [
    'Development Status :: 4 - Beta',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Operating System :: POSIX :: Linux',
    'Operating System :: Unix',
    'Programming Language :: Python',
    'Programming Language :: Python :: 2',
    'Programming Language :: Python :: 2.5',
    'Programming Language :: Python :: 2.6',
    'Programming Language :: Python :: 2.7',
    'Topic :: Utilities',
]

rel_file = lambda *args: os.path.join(
        os.path.dirname(os.path.abspath(__file__)), *args)


def get_readme():
    return open(rel_file('README.md')).read()


def get_requirements():
    data = open(rel_file('requirements.txt')).read()
    lines = map(lambda s: s.strip(), data.splitlines())
    return filter(None, lines)


setup_options = dict(
    name='terrarium',
    version=version,
    author='Kyle Gibson',
    author_email='kyle.gibson@frozenonline.com',
    description='Package and ship relocatable python virtualenvs',
    license='BSD',
    url='http://github.com/policystat/terrarium',
    packages=['terrarium'],
    long_description=get_readme(),
    install_requires=get_requirements(),
    entry_points={
        'console_scripts':
            ['terrarium = terrarium.terrarium:main']
    },
    classifiers=classifiers,
    zip_safe=False,
)

setup(**setup_options)
