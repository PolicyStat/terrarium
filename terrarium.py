#!/usr/bin/env python

import argparse
import hashlib
import logging
import os
import sys
import tempfile

try:
    import boto  # noqa
except ImportError:
    boto = None  # noqa

from virtualenv import (  # noqa
    call_subprocess,
    create_bootstrap_script,
    join,
    make_environment_relocatable,
    path_locations,
)

logger = logging.getLogger(__name__)


class Terrarium(object):
    def __init__(self, args):
        self.args = args
        self._requirements = None
        self._digest = None
        logger.debug('Terrarium created with %s', args)

    @property
    def digest(self):
        if self._digest is not None:
            return self._digest
        m = hashlib.new(self.args.digest_type)
        m.update('\n'.join(self.requirements))
        self._digest = m.hexdigest()
        return self._digest

    @property
    def requirements(self):
        if self._requirements is not None:
            return self._requirements
        lines = []
        for arg in self.args.reqs:
            if os.path.exists(arg):
                with open(arg, 'r') as f:
                    for line in f.readlines():
                        line = line.strip()
                        if line:
                            lines.append(line)
        self._requirements = sorted(lines)
        return self._requirements

    def install(self):
        logger.debug('Running install')

        fd, bootstrap = tempfile.mkstemp(
            prefix='terrarium_bootstrap-',
            suffix='.py',
        )
        self.create_bootstrap(bootstrap)

        #call_subprocess(['python', bootstrap])

        os.close(fd)

    def create_bootstrap(self, dest):
        extra_text = '''
def set_logger_level(level):
    for i in range(len(logger.consumers)):
        consumer = logger.consumers[i]
        if consumer[1] == sys.stdout:
            logger.consumers[i] = (level, sys.stdout)

def adjust_options(options, args):
    options.use_distribute = True
    options.system_site_packages = False

REQUIREMENTS = %(REQUIREMENTS)s

def after_install(options, base):
    set_logger_level(Logger.INFO)
    import shlex
    from pip.commands.install import InstallCommand
    from pip import version_control
    # Load version control modules
    version_control()
    c = InstallCommand()
    reqs = shlex.split(' '.join(REQUIREMENTS))
    options, args = c.parser.parse_args(reqs)
    requirementSet = c.run(options, args)
    # making a virtualenv relocatable can fail for a variety of reasons of
    # which are all silently discarded unless you increase the logging
    # verbosity
    set_logger_level(Logger.DEBUG)
    home_dir, lib_dir, inc_dir, bin_dir = path_locations(base)
    activate_this = join(bin_dir, 'activate_this.py')
    execfile(activate_this, dict(__file__=activate_this))
    make_environment_relocatable(base)
        '''
        output = create_bootstrap_script(
            extra_text % {'REQUIREMENTS': self.requirements}
        )
        with open(dest, 'w') as f:
            f.write(output)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '-v', '--verbose',
        action='append_const',
        const=-10,
        default=[logging.WARN],
        dest='v',
        help='Increase verbosity',
    )
    ap.add_argument(
        '-q', '--quiet',
        action='append_const',
        const=10,
        default=[logging.WARN],
        dest='v',
        help='Decrease verbosity',
    )
    ap.add_argument(
        '--digest-type',
        default='md5',
        help='Choose digest type (md5, sha, ...)',
    )

    ap.add_argument(
        '--no-download',
        default=True,
        action='store_false',
        dest='download',
        help='''
            Normally, terrarium will pull down an existing bundle instead of
            building a new one. This option forces terrarium to build a new
            environment.
        ''',
    )
    ap.add_argument(
        '--no-upload',
        default=True,
        action='store_false',
        dest='upload',
        help='''
            Normally, terrarium will attempt to upload a new environment after
            it has been built. This option prevents this behavior.
        ''',
    )
    ap.add_argument(
        '--storage-dir',
        default=None,
        help='''
            Path to a directory in which virtualenvs will be retrieved and
            stored for speedy re-installation. This will usually be a shared
            drive.  That allows other folks on your team (or servers) to
            benefit from crazy-fast installations.
        ''',
    )
    ap.add_argument(
        '-E', '--environment',
        default=os.environ.get('VIRTUAL_ENV', None),
        help='Path to the virtualenv',
    )

    if boto:
        ap.add_argument(
            '--s3-bucket',
            default=os.environ.get('S3_BUCKET', None),
        )
        ap.add_argument(
            '--s3-access-key',
            default=os.environ.get('S3_ACCESS_KEY', None),
        )
        ap.add_argument(
            '--s3-secret-key',
            default=os.environ.get('S3_SECRET_KEY', None),
        )
        ap.add_argument(
            '--s3-max-retries',
            default=os.environ.get('S3_MAX_RETRIES', 1),
            help='Number of times to attempt a S3 action before giving up',
        )

    subparsers = ap.add_subparsers(
        title='Basic Commands',
        dest='command',
    )
    commands = {
        'hash': subparsers.add_parser(
            'hash',
            help='Display digest for current requirement set',
        ),
        'exists': subparsers.add_parser(
            'exists',
            help='''
                Return exit code 0 if environment matches requirement set
            ''',
        ),
        'install': subparsers.add_parser(
            'install',
            help='''
                Replace current environment with the one given by the
                requirement set
            ''',
        ),
    }

    for command in commands.values():
        command.add_argument('reqs', nargs=argparse.REMAINDER)
    args = ap.parse_args()

    logger.setLevel(sum(args.v))
    logger.addHandler(logging.StreamHandler())

    terrarium = Terrarium(args)

    if args.command == 'hash':
        print terrarium.digest
    elif args.command == 'exists':
        sys.exit(0)
    elif args.command == 'install':
        terrarium.install()
    else:
        ap.print_help()

if __name__ == '__main__':
    main()
