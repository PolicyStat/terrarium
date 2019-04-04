##########
User Guide
##########

.. include:: _quickstart.rst

Saving and using environment archives
#####################################

Terrarium provides options for archiving and compressing
a freshly installed
and built environment,
either locally or remotely (via Amazon S3).

When these options are used,
terrarium will first check if the environment has already been saved.
In that case,
terrarium will download the environment archive instead of downloading
and building each individual package specified in the requirements files.

Storing terrarium environments locally
======================================

Storing terrarium environments locally (or on a shared network disk)
can be achieved using the ``--storage-dir`` option.

.. code-block:: shell-session

    $ terrarium --target env --storage-dir path/to/environments install requirements.txt

After building a fresh environment from the requirements in ``requirements.txt``,
terrarium will archive and compress the environment.
Finally,
the compressed version is then copied to the path specified by ``--storage-dir``.

Storing terrarium environments on Cloud Storage Services (S3, GCS)
==================================================================

Terrarium also supports storing and retrieving archives stored on these storage services:

  * Amazon Web Service - S3
  * Google Cloud Platform - Google Cloud Storage

Amazon S3
---------

The following options are only available if ``boto`` is installed.

  * ``--s3-bucket``
  * ``--s3-access-key``
  * ``--s3-secret-key``
  * ``--s3-max-retries``

Google Cloud Storage
--------------------

The following options are only available if ``gcloud`` is installed.

  * ``--gcs-bucket``
  * ``--gcs-client-email``
  * ``--gcs-secret-key``
  * ``--gcs-max-retries``

.. note::
    Each of the above options can be specified using environment variables,
    e.g. ``S3_BUCKET``, ``GCS_BUCKET``
    instead of being passed in as a parameter.

Using Python 3 inside virtualenv
================================

Use ``-p`` argument to choose Python executable installed in virtualenv:

.. code-block:: shell-session

    $ terrarium -p python3.6 --target env --storage-dir path/to/environments install requirements.txt

Tips
####

Using an alternative index server
=================================

If you're using an index server other than PyPI
(perhaps an index server with internal-only packages),
then you need to be able to tell terrarium to use that index URL.
Terrarium does not have the
``-i`` (``--index-url``)
option that pip has,
so how do you indicate the index URL?
Well, you may recall that pip requirements files can also contain command-line options...
So add a line like this to one of your requirements files:

::

    --index-url http://internal-index-server.corp/index

You can add a line like the above to
an existing requirements file
that has a list of packages
or you could add it to
a separate requirements file
and then add that to the terrarium command-line.

.. code-block:: shell-session

    $ terrarium --target testenv install internal-index-server.txt requirements.txt
