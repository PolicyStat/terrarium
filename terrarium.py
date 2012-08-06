#!/usr/bin/env python

import logging
import os
import hashlib
#import tempfile
#import sys

import argparse

logger = logging.getLogger(__name__)


class Terrarium(object):
    def __init__(self, requirements, digest='md5'):
        self.requirements = self._load_requirements(requirements)
        self.digest = self.get_digest(digest)

    def get_digest(self, digest='md5'):
        if hasattr(self, 'digest'):
            return self.digest
        m = hashlib.new(digest)
        m.update('\n'.join(self.requirements))
        self.digest = m.hexdigest()
        return self.digest

    def _load_requirements(self, requirements):
        lines = []
        for arg in requirements:
            if os.path.exists(arg):
                with open(arg, 'r') as f:
                    for line in f.readlines():
                        line = line.strip()
                        if line:
                            lines.append(line)
        return sorted(lines)


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
        '--digest',
        default='md5',
        help='Choose digest type (md5, sha, ...)',
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

    try:
        import boto # noqa
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
    except ImportError:
        pass

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

    terrarium = Terrarium(args.reqs, digest=args.digest)

    if args.command == 'hash':
        print terrarium.get_digest()
    elif args.command == 'exists':
        pass
    elif args.command == 'install':
        pass
    else:
        ap.print_help()

if __name__ == '__main__':
    main()
