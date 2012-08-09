# Terrarium

Package and ship relocatable python virtualenvs, like a boss.

Terrarium will package up 
and compress a virtualenv for you 
based on pip requirements 
and then let you ship that environment around. 
Do the complex dependency math one time 
and then every subsequent install is basically 
at the speed of file transfer + decompression.

	$ ter install req1.txt req2.txt --ter-cache=/shared/folder

## The Problem Terrarium Solves

Pip and virtualenv are awesome, 
but pip is not designed
to allow consistent and reproducable updates of existing environments.
Pip is also a general installation tool,
meaning that it's not near as fast
as shipping around compressed source code.
This means that even if you have well-made requirements files,
your pip-based deploys are either slow or inconsistent.

## Options

	ter install [requirements...]
	ter hash [requirements...]
	ter exists [requirements...]

	--storage-dir

Path to a directory in which virtualenvs will be retrieved and stored for
speedy re-installation. This will usually be a shared drive. That allows other
folks on your team (or servers) to benefit from crazy-fast installations. 

	--s3-bucket

If given, upload the packaged virtualenv to this s3 bucket instead of to the
`storage-dir`.

	-t DIR, --target=DIR

virtualenv environment on which to act

	--no-download

Don't download and use an already-built virtualenv, even if a matching
virtualenv exists

	--no-upload

Don't upload the finished virtualenv to the configure filesystem path or s3
directory

	--s3-access-key
	--s3-secret-key


### Bootstrap Script

A virtualenv boostrap script is created as part of the packaging and lives at
`path/to/virtualenv/terrarium_boostrap.py`. This script can be used to create a
virtualenv with the same requirements.

