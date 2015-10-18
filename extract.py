#!/usr/bin/env python3

import argparse
import tempfile
import subprocess
import os
import fnmatch
import shutil

parser = argparse.ArgumentParser(description='extract recursive rars')
parser.add_argument('archive', help='rar archive to extract from')
parser.add_argument('-p', help='rar password', default=None)
parser.add_argument('--pat', '-e', help='only extract files with that match the pattern, e.g: *.mkv')
parser.add_argument('target_dir', help='target directory (uses archive name as default)', nargs='?', default=None)

args = parser.parse_args()


def rar_cmd(archive, target_dir, password):
    password_str = ' -p{}'.format(password) if password else ''

    return 'unrar x {} {} {}'.format(archive, target_dir, password_str)


def zip_cmd(archive, target_dir, password):
    return 'unzip {archive} -d {target_dir}'

archive_cmds = {
    'rar': rar_cmd,
    'zip': zip_cmd,
}

extensions = {
    'rar': 'rar',
    'zip': 'zip',
    'zep': 'zip',
}


def match_patterns(filename, patterns):
    for pattern in patterns:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


def find_files(directory, patterns=None):
    for root, dirs, files in os.walk(directory):
        for basename in files:
            if patterns is None or match_patterns(basename, patterns):
                yield os.path.join(root, basename)


def is_archive(file):
    return match_patterns(file, ['*.{}'.format(extension) for extension in extensions.values()])


def extract(archive):
    try:
        archive_extension = os.path.splitext(archive)[1][1:]
        extension = extensions[archive_extension]
    except KeyError:
        exit('unknown extension "{}"'.format(archive_extension))

    with tempfile.TemporaryDirectory() as tempdir:
        print('extracting from {} to {}'.format(archive, tempdir))
        subprocess.check_output(
            archive_cmds[extension](
                archive=archive,
                target_dir=tempdir,
                password=args.p,
            ),
            shell=True
        )
        for file_ in find_files(tempdir):
            if is_archive(file_):
                extract(file_)
            else:
                if match_patterns(file_, [args.pat]):
                    try:
                        os.unlink(os.path.join(args.target_dir, os.path.basename(file_)))
                    except FileNotFoundError:
                        pass
                    shutil.move(file_, args.target_dir)

extract(args.archive)
