#!/bin/bash

# This speeds up re-installing packages
PIP_CACHE=$HOME/.pip-cache

run_tests() {
    #set -o xtrace
    source ~/.python/bin/activate
    virtualenv testenv
    source testenv/bin/activate
    pip install --download-cache=$PIP_CACHE virtualenv==$1 nose==1.2.1
    shift  # pop off the first argument
    pip install --download-cache=$PIP_CACHE -r requirements.txt
    python setup.py install
    virtualenv --version
    nosetests -v $@
    deactivate
    rm -fR testenv
}

run_tests 1.7.1.2 $@
run_tests 1.7.2 $@
# These versions are currently supported
#run_tests 1.8 $@
#run_tests 1.8.1 $@
run_tests 1.8.2 $@
run_tests 1.8.3 $@
run_tests 1.8.4 $@
