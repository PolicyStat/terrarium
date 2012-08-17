# Terrarium

[![Build Status](https://secure.travis-ci.org/PolicyStat/terrarium.png)](http://travis-ci.org/PolicyStat/terrarium)

Package and ship relocatable python virtual environments, like a boss.

Terrarium will package up and compress a virtualenv for you based on pip
requirements and then let you ship that environment around.  Do the
complex dependency math one time and then every subsequent install is
basically at the speed of file transfer + decompression.

## The Problem Terrarium Solves

Pip and virtualenv are awesome, but pip is not designed to allow
consistent and reproducable updates of existing environments.  Pip is
also a general installation tool, meaning that it's not near as fast as
shipping around compressed source code.  This means that even if you
have well-made requirements files, your pip-based deploys are either
slow or inconsistent.

## Installation

Install using pip:

    pip install git://github.com/PolicyStat/terrarium#egg=terrarium

## Basic Usage

    terrarium [options] COMMAND [requirements files...]

Creating a new environment:

    terrarium --target testenv install requirements.txt more_requirements.txt

After this command finishes, `testenv` will be configured with all of
the requirements specified in `requirements.txt` and
`more_requirements.txt`.

Additionally, terrarium creates a script in `testenv/bin/terrarium_bootstrap.py` that can be used to generate a fresh environment using exactly the same requirements. This behavior can be disabled by using the `--no-bootstrap` option.

If `testenv` is an already existing environment, it will replace it with a fresh environment, and preserve the old environment as `testenv.bak`.

    source testenv/bin/activate
    terrarium install test_requirements.txt

When a virtualenv is already activated, the --target option defaults to
the activated environment. Terrarium will replace the activated
environment (`testenv`) with a fresh environment defined by `test_requirements.txt`.
The old environment is preserved at `testenv.bak`.

## Terrarium archives

    terrarium --target testenv --storage-dir /mnt/storage install requirements.txt more_requirements.txt

After building a fresh environment, terrarium will archive and compress
the environment, and then copy it to the location specified by
`storage-dir`.

Subsequent installs for the same requirement set that specify the same
`storage-dir`, terrarium will copy and extract the compressed archive
from `/mnt/storage`.

To display exactly how terrarium will name the archive, you can run the
following command:

    terrarium key requirements.txt more_requirements.txt
    x86_64-2.6-c33a239222ddb1f47fcff08f3ea1b5e1

By default the key includes the system architecture, python version and
the MD5 digest of the sorted contents of the requirements files. The
digest used can be customized with `--digest-type`, and the key format
can be specified using `--remote-key-format`.

You can prevent terrarium from either uploading or downloading archives
using the `--no-upload` and `--no-download` options.

## Using S3 storage backend

terrarium supports storing and retrieving archives on Amazon S3. These
options will only be available if `boto` is installed.

    --s3-bucket
    --s3-access-key
    --s3-secret-key
    --s3-max-retries

Each of these options can be specified using environment variables, e.g.
`S3_BUCKET` instead of being passed in as a parameter.
