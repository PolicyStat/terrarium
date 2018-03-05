#########
Terrarium
#########

.. image:: https://img.shields.io/pypi/v/terrarium.svg
   :target: https://crate.io/packages/terrarium

.. image:: https://secure.travis-ci.org/PolicyStat/terrarium.png?branch=master
   :target: http://travis-ci.org/PolicyStat/terrarium

* `Installation <https://terrarium.readthedocs.org/en/latest/installation.html>`_
* `Documentation <https://terrarium.readthedocs.org>`_
* `Release Notes <https://terrarium.readthedocs.org/en/latest/release_notes.html>`_
* `Github Page <https://github.com/PolicyStat/terrarium>`_
* `Issue Tracking <https://github.com/PolicyStat/terrarium/issues>`_

Package and ship relocatable python virtual environments,
like a boss.

Terrarium will package up
and compress a virtualenv for you based on pip requirements
and then let you ship that environment around.
Do the complex dependency math one time
and then every subsequent install is basically at the speed of
file transfer + decompression.

The Problem Terrarium Solves
############################

Pip and virtualenv are awesome,
but pip is not designed to allow
consistent and reproducible updates of existing environments.
Pip is also a general installation tool,
meaning that it's not near as fast as shipping around compressed source code.
This means that even if you have well-made requirements files,
your pip-based deploys are either slow or inconsistent.

To get started using terrarium,
see the `Quick Start <https://terrarium.readthedocs.org/en/latest/quickstart.html>`_
guide.
