###########
Development
###########

Installing requirements
#######################

Using pip
=========

.. code-block:: shell-session

   $ pip install -r requirements/docs.txt -r requirements/testing.txt

Building the documentation locally
##################################

#. Install the documentation requirements:

   .. code-block:: shell-session

      $ pip install -r requirements/docs.txt

#. Change directory to ``docs`` and run ``make html``:

   .. code-block:: shell-session

      $ cd docs
      $ make html

#. Load HTML documentation in a web browser of your choice:

   .. code-block:: shell-session

      $ firefox docs/_build/html/index.html

Running tests
#############

#. Install the development requirements:

   .. code-block:: shell-session

      $ pip install -r requirements/testing.txt

#. Run ``nosetests`` in the project root.

   .. code-block:: shell-session

      $ nosetests

To run all tests against all supported versions of python,
use ``tox``.

Running tests with tox
======================

``tox`` allows us to use
one command to
run tests against
all versions of python
that we support.

Setting up tox
--------------

#. Decide how you want to manage multiple python versions.

   #. System level using a package manager such as ``apt-get``.
      This approach will likely require adding additional
      ``apt-get`` sources
      in order to install
      alternative versions of python.
   #. Use `pyenv <https://github.com/yyuu/pyenv-installer#installation>`_
      to manage and install multiple python versions.
      After installation,
      see the
      `pyenv command reference <https://github.com/yyuu/pyenv/blob/master/COMMANDS.md>`_.

#. Install ``tox``.

   .. code-block:: shell-session

       $ pip install tox

#. `Configure tox <http://tox.readthedocs.org/en/latest>`_.

Running tox
-----------

Now that you have ``tox`` setup, you just need to run the command ``tox`` from the project root directory.

.. code-block:: shell-session

   $ tox

Getting involved
################

The terrarium project welcomes help in any of the following ways:

* Making pull requests on github for code,
  tests and documentation.
* Participating on open issues and pull requests,
  reviewing changes
  
Pull Request Checklist
======================

To have the best chance at an immediate merge,
your pull request should have:

* A passing Travis-CI build.
  If it fails,
  check the console output for reasons why.
* New unit tests
  for new features
  or bug fixes.
* New documentation in ``docs``
  for any new features.
  You do want people to know
  how to use your new stuff,
  right?

Release process
###############

#. Update
   `CHANGELOG <https://github.com/PolicyStat/terrarium/blob/master/CHANGELOG.rst>`_.
#. Bump the version number in
   `__init__.py <https://github.com/PolicyStat/terrarium/blob/master/terrarium/__init__.py>`_
   on master.
#. Tag the version.
#. Push to PyPI.
