#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Asensado
"""Package complete tracked source and publish a configured, tested GitHub release."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent.parent
REPO = 'Asensado/Handoff-Vibe'


def spec():
    data = json.loads((ROOT / 'RELEASE.json').read_text())
    if not re.fullmatch(r'\d+\.\d+\.\d+', data['version']):
        raise ValueError('Invalid release version')
    if not re.fullmatch('v' + re.escape(data['version']) + r'(?:-[A-Za-z0-9.-]+)?', data['tag']):
        raise ValueError('Release tag does not match the version')
    if type(data.get('prerelease')) is not bool:
        raise ValueError('prerelease must be an explicit boolean')
    return data


def archive(data):
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    package = dist / f"handoff-vibe_{data['version']}_amd64.deb"
    if not package.is_file():
        raise FileNotFoundError(package)
    source = dist / f"handoff-vibe-{data['version']}-source.zip"
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as output:
        for name in sorted(filter(None, paths)):
            path = ROOT / name
            if path.is_file():
                output.write(path, f"handoff-vibe-{data['version']}/{name}")
    installer = dist / 'INSTALL-UPDATE.sh'
    shutil.copy2(ROOT / installer.name, installer)
    assets = [package, source, installer]
    checksums = dist / 'SHA256SUMS'
    checksums.write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n' for path in assets))
    return assets + [checksums]


def publish(data, assets):
    if os.environ.get('GITHUB_REPOSITORY') != REPO:
        raise ValueError('This publishing configuration targets only ' + REPO)
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    command = ['gh', 'release']
    existing = subprocess.run(command + ['view', data['tag'], '--repo', REPO, '--json', 'isDraft,targetCommitish'],
                              text=True, capture_output=True)
    if existing.returncode == 0:
        release = json.loads(existing.stdout)
        if not release['isDraft']:
            raise ValueError('Refusing to overwrite an already published release')
        if release['targetCommitish'] != sha:
            raise ValueError('The existing draft targets a different source commit')
    else:
        args = command + ['create', data['tag'], '--repo', REPO, '--target', sha,
                          '--title', data['title'], '--notes-file', str(ROOT / 'RELEASE_NOTES.md'), '--draft']
        if data['prerelease']:
            args.append('--prerelease')
        subprocess.run(args, check=True)
    subprocess.run(command + ['upload', data['tag'], '--repo', REPO, '--clobber'] + [str(path) for path in assets], check=True)
    # Assets are present before the draft becomes public. A rerun never replaces
    # an already-published release or silently moves an existing tag.
    subprocess.run(command + ['edit', data['tag'], '--repo', REPO, '--draft=false'], check=True)
    print(f"Published https://github.com/{REPO}/releases/tag/{data['tag']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    data = spec()
    assets = archive(data)
    if args.publish:
        publish(data, assets)
    else:
        for path in assets:
            print(path)


if __name__ == '__main__':
    main()
