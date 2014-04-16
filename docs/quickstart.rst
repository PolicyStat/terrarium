###########
Quick Start
###########

Creating a new environment
##########################

The following example will create a new virtual environment named ``env`` that
includes the packages defined in ``requirements.txt``

.. code-block:: shell-session

    $ terrarium --target env install requirements.txt

Replacing an existing environment
#################################

The following example demonstrates how terrarium can be used to replace an
existing activated virtual environment with a different set of packages.

.. code-block:: shell-session

    $ terrarium --target env install requirements.txt
    $ source env/bin/activate
    $ terrarium install other_requirements.txt
