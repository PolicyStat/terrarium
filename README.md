# Terrarium

[![Build Status](https://travis-ci.org/PolicyStat/terrarium.png?branch=master)](https://travis-ci.org/PolicyStat/terrarium)
[![Downloads](https://pypip.in/v/terrarium/badge.png)](https://crate.io/packages/terrarium/)

Package and ship relocatable python virtual environments, like a boss.

Terrarium will package up and compress a virtualenv for you based on pip
requirements and then let you ship that environment around.  Do the
complex dependency math one time and then every subsequent install is
basically at the speed of file transfer + decompression.

## The Problem Terrarium Solves

Pip and virtualenv are awesome, but pip is not designed to allow
consistent and reproducible updates of existing environments.  Pip is
also a general installation tool, meaning that it's not near as fast as
shipping around compressed source code.  This means that even if you
have well-made requirements files, your pip-based deploys are either
slow or inconsistent.
