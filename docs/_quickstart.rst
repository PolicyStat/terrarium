.. code-block:: shell-session

    terrarium [options] COMMAND [requirements files...]

See ``terrarium --help`` for a complete list of options and commands.

.. note::

    The following documentation assumes you are familiar with `virtualenv
    <http://www.virtualenv.org/en/latest/>`_. If not, run through `this
    tutorial <http://docs.python-guide.org/en/latest/dev/virtualenvs/>`_. We'll
    wait.

Creating a new environment
##########################

The following example will create a new virtual environment named ``env`` that
includes the packages defined in ``requirements.txt``

.. code-block:: shell-session

    $ terrarium --target path/to/env install requirements.txt

Replacing an existing environment
#################################

The following example demonstrates how terrarium can be used to replace an
existing activated virtual environment with a different set of packages.

.. code-block:: shell-session

    $ terrarium --target path/to/env install requirements.txt
    $ source path/to/env/bin/activate
    $ terrarium install other_requirements.txt

.. note::
    The environment that was replaced is renamed to ``env.bak``,
    and can be restored using ``terrarium revert``.

.. note::
    After installing the ``other_requirements``,
    it is not necessary to run ``deactivate``
    or ``activate``
    to begin using the new environment.
