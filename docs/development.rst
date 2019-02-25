###########
Development
###########

Building the documentation locally
##################################

#. Install ``tox``

   .. code-block:: shell-session

      $ pip install tox

#. Use ``tox``

   .. code-block:: shell-session

      $ tox -e docs

#. Load HTML documentation in a web browser of your choice:

   .. code-block:: shell-session

      $ browser docs/_build/html/index.html

Running tests
#############

#. Install ``tox``

   .. code-block:: shell-session

      $ pip install tox

#. Use ``tox``

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
#. Generate source and wheel distributions: python setup.py sdist bdist_wheel
#. Upload to PyPI: twine upload dist/*
