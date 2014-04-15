import sys
from setuptools import setup

# Update here and in terrarium.py
version = '1.0.0rc5-dev'

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


def main():
    python_version = sys.version_info[:2]
    install_requires = [
        'virtualenv>=1.7.2,<=1.9.1',
    ]
    if python_version < (2, 7) or (3, 0) <= python_version <= (3, 1):
        install_requires += ['argparse']

    setup(
        name='terrarium',
        version=version,
        author='Kyle Gibson',
        author_email='kyle.gibson@frozenonline.com',
        description='Package and ship relocatable python virtualenvs',
        license='BSD',
        url='http://github.com/policystat/terrarium',
        packages=['terrarium'],
        long_description='''
            Terrarium will package up and compress a virtualenv for you based
            on pip requirements and then let you ship that environment around.
            Do the complex dependency math one time and then every subsequent
            install is basically at the speed of file transfer + decompression.
        ''',
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
