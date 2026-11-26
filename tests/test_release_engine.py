import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from handoff_ui import releases as R
from handoff_ui.engine import snapshot, unpack
from handoff_ui.models import identify


class Releases(unittest.TestCase):
    def release(self, **changes):
        item = dict(tag_name='v0.3.0', name='New build', body='Notes', assets=[], draft=False, prerelease=False)
        item.update(changes)
        return item

    def test_stable_sort_and_ignore_unusable_versions(self):
        result = R.parse_releases([self.release(tag_name='v0.2.0'), self.release(),
            self.release(tag_name='v99.0.0', draft=True), self.release(tag_name='v0.4.0-beta'),
            self.release(tag_name='v88.0.0', prerelease=True)])
        self.assertEqual([r['version'] for r in result], ['0.3.0', '0.2.0'])

    def test_history_includes_beta_and_experimental_without_changing_updates(self):
        payload = [self.release(tag_name='v0.2.0'),
                   self.release(tag_name='v0.3.0-beta.1', prerelease=True),
                   self.release(tag_name='v0.4.0-experimental.2', prerelease=True),
                   self.release(tag_name='v0.5.0-rc1'),
                   self.release(tag_name='v9.0.0', draft=True)]
        history = R.parse_releases(payload, include_prereleases=True)
        self.assertEqual([item['channel'] for item in history], ['beta', 'experimental', 'beta', 'stable'])
        self.assertEqual([item['version'] for item in R.parse_releases(payload)], ['0.2.0'])
        self.assertNotIn('9.0.0', [item['version'] for item in history])

    def test_github_prerelease_flag_without_suffix_is_beta(self):
        result = R.parse_releases([self.release(prerelease=True)], include_prereleases=True)
        self.assertEqual(result[0]['channel'], 'beta')
        self.assertEqual(R.release_identity('v0.1.0-PRE', True)[2], 'beta')

    def test_only_fixed_repository_downloads(self):
        name = 'handoff-vibe_0.3.0_amd64.deb'
        safe = dict(name=name, browser_download_url=R.REPOSITORY + '/releases/download/v0.3.0/' + name,
                    digest='sha256:' + 'a' * 64, size=100)
        unsafe = dict(safe, browser_download_url='https://example.com/' + name)
        result = R.parse_releases([self.release(assets=[unsafe, safe])])[0]
        self.assertEqual(len(result['assets']), 1)
        self.assertEqual(R.update_asset(result, 'amd64')['name'], name)
        with self.assertRaises(ValueError):
            R.update_asset(result, 'arm64')
        result['assets'][0]['digest'] = ''
        with self.assertRaises(ValueError):
            R.update_asset(result, 'amd64')

    def test_sha256_download_and_mismatch(self):
        data = b'debian package fixture'
        asset = dict(url=R.REPOSITORY + '/releases/download/v0.3.0/example.deb', size=len(data),
                     digest='sha256:' + hashlib.sha256(data).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(R, 'build_opener') as opener:
                opener.return_value.open.return_value = io.BytesIO(data)
                target = Path(directory) / 'valid.deb'
                R.download_asset(asset, target)
                self.assertEqual(target.read_bytes(), data)
            with patch.object(R, 'build_opener') as opener:
                opener.return_value.open.return_value = io.BytesIO(b'x' * len(data))
                with self.assertRaises(ValueError):
                    R.download_asset(asset, Path(directory) / 'invalid.deb')


class Engine(unittest.TestCase):
    def test_powerbeats_identifier(self):
        model, status = identify({'Modalias': 'bluetooth:v004Cp202FdD41F'})
        self.assertEqual((model.key, status), ('powerbeatsfit', 'detected'))

    def test_remote_audio_does_not_disable_controls(self):
        state = snapshot(dict(Connected=True, AudioSource='other', SupportsANC=True,
                              NoiseControlMode='anc', ListeningTimeRemaining=270, BatteryLeft=80))
        self.assertTrue(state['controls_ready'])
        self.assertEqual(state['owner'], 'other')
        self.assertEqual(state['listening_minutes'], 270)

    def test_disconnected_and_unlearned_estimate(self):
        state = snapshot({})
        self.assertFalse(state['ready'])
        self.assertFalse(state['controls_ready'])
        self.assertEqual(state['listening_minutes'], -1)
        self.assertEqual(state['battery_left'], -1)


if __name__ == '__main__':
    unittest.main()
