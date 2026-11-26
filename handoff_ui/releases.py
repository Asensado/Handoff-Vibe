# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Asensado
"""Public stable releases from the Handoff repository; no account token needed."""
import hashlib
import json
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler

REPOSITORY = 'https://github.com/Asensado/Handoff-Vibe'
API = 'https://api.github.com/repos/Asensado/Handoff-Vibe/releases?per_page=20'


class HTTPSOnly(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        if not url.startswith('https://'):
            raise ValueError('An update redirected to an insecure address')
        return super().redirect_request(request, fp, code, message, headers, url)


def version_tuple(tag):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(tag))
    return tuple(map(int, match.groups())) if match else None


def release_identity(tag, prerelease=False):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-([A-Za-z0-9][A-Za-z0-9.-]*))?', str(tag))
    if not match:
        return None
    base = tuple(map(int, match.groups()[:3]))
    suffix = match[4] or ''
    channel = 'stable'
    if prerelease or suffix:
        channel = 'experimental' if re.search(r'(experimental|alpha|dev|nightly|snapshot)', suffix, re.I) else 'beta'
    return base, suffix, channel


def parse_releases(payload, include_prereleases=False):
    if not isinstance(payload, list):
        raise ValueError('GitHub returned an invalid releases response')
    releases = []
    for item in payload:
        if not isinstance(item, dict) or item.get('draft'):
            continue
        identity = release_identity(item.get('tag_name', ''), item.get('prerelease', False))
        if identity is None:
            continue
        version, suffix, channel = identity
        if channel != 'stable' and not include_prereleases:
            continue
        tag = item['tag_name']
        url = REPOSITORY + '/releases/tag/' + tag
        assets = []
        for asset in item.get('assets', []):
            if not isinstance(asset, dict):
                continue
            name = asset.get('name', '')
            download = asset.get('browser_download_url', '')
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.+-]+\.deb', name):
                continue
            if download != REPOSITORY + '/releases/download/' + tag + '/' + name:
                continue
            assets.append(dict(name=name, url=download, digest=asset.get('digest', ''), size=asset.get('size', 0)))
        version_text = '.'.join(map(str, version)) + ('-' + suffix if suffix else '')
        releases.append(dict(version=version_text, channel=channel, tag=tag,
                             title=str(item.get('name') or tag)[:200],
                             body=str(item.get('body') or 'No release notes were provided.')[:40000],
                             date=str(item.get('published_at') or '')[:10], url=url, assets=assets))
    return sorted(releases, key=lambda release: (
        release_identity(release['tag'])[0], release['channel'] == 'stable',
        release.get('date', ''), release['version']), reverse=True)


def fetch_releases(include_prereleases=False):
    request = Request(API, headers={'User-Agent': 'Handoff-Vibe/0.2.0', 'Accept': 'application/vnd.github+json'})
    with build_opener(HTTPSOnly()).open(request, timeout=10) as response:
        data = response.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError('The release list was too large')
    return parse_releases(json.loads(data), include_prereleases=include_prereleases)


def update_asset(release, architecture):
    expected = f"handoff-vibe_{release['version']}_{architecture}.deb"
    for asset in release['assets']:
        if asset['name'] == expected:
            if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', str(asset.get('digest', ''))):
                raise ValueError('This release has no GitHub SHA-256 digest; automatic installation is unavailable')
            if not isinstance(asset.get('size'), int) or not 0 < asset['size'] <= 100 * 1024 * 1024:
                raise ValueError('The release package has an invalid size')
            return asset
    raise ValueError('This release has no Handoff package for this system architecture')


def download_asset(asset, destination):
    digest = hashlib.sha256()
    size = 0
    request = Request(asset['url'], headers={'User-Agent': 'Handoff-Vibe/0.2.0'})
    with build_opener(HTTPSOnly()).open(request, timeout=30) as source, open(destination, 'xb') as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > asset['size']:
                raise ValueError('The downloaded package exceeded its release size')
            digest.update(chunk)
            target.write(chunk)
    if size != asset['size'] or digest.hexdigest().lower() != asset['digest'].split(':')[1].lower():
        raise ValueError('The downloaded package did not match its GitHub SHA-256 digest')
