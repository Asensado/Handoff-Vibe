# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Asensado
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from handoff_ui import backend as B, engine as E, releases as R
from handoff_ui.settings import normalize_settings

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('retired_updater', str(ROOT / 'packaging/update-handoff'))
spec = importlib.util.spec_from_loader(loader.name, loader)
updater = importlib.util.module_from_spec(spec)
loader.exec_module(updater)


class SecurityReview(unittest.TestCase):
    def test_privileged_installer_fails_closed_for_every_install_action(self):
        for action in ('enable', 'run', 'run-automatic'):
            with self.subTest(action=action), patch.object(updater.os, 'geteuid', return_value=0), \
                 patch.object(sys, 'argv', ['update-handoff', action]), patch('subprocess.run') as run:
                with self.assertRaisesRegex(SystemExit, 'authenticated release signing'):
                    updater.main()
                run.assert_not_called()

    def test_old_opt_in_can_only_be_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            marker, hook = Path(directory) / 'marker', Path(directory) / 'hook'
            marker.touch(); hook.touch()
            with patch.object(updater, 'MARKER', marker), patch.object(updater, 'HOOK', hook), \
                 patch.object(updater.os, 'geteuid', return_value=0), \
                 patch.object(sys, 'argv', ['update-handoff', 'disable']):
                updater.main()
            self.assertFalse(marker.exists())
            self.assertFalse(hook.exists())

    def test_installed_helper_ignores_python_startup_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            marker = folder / 'injected'
            (folder / 'sitecustomize.py').write_text(f'open({str(marker)!r}, "w").write("injected")')
            helper = folder / 'update-handoff'
            helper.write_bytes((ROOT / 'packaging/update-handoff').read_bytes())
            helper.chmod(0o755)
            result = subprocess.run([str(helper), 'run'], cwd=folder,
                env=dict(os.environ, PYTHONPATH=directory), capture_output=True, text=True, timeout=3)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())
            self.assertNotIn('Traceback', result.stderr)

    def test_regular_entrypoints_reject_root_before_loading_application(self):
        for name in ('handoff', 'handoff-vibe', 'packaging/handoff-engine'):
            result = subprocess.run(['/usr/bin/python3', '-I', '-c',
                'import os,runpy,sys; os.geteuid=lambda:0; runpy.run_path(sys.argv[1])', str(ROOT / name)],
                capture_output=True, text=True, timeout=3)
            self.assertIn('regular desktop user', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_persisted_settings_are_typed_and_bounded(self):
        for value in (None, [], 'bad', {'auto_connect': 'false'}, {'ear_pause_mode': 'bad'},
                      {'ear_pause_mode': True}, {'ear_pause_mode': 8}):
            settings = normalize_settings(value)
            self.assertIs(settings['auto_connect'], False)
            self.assertEqual(settings['ear_pause_mode'], 1)
        self.assertEqual(normalize_settings({'ear_pause_mode': 0})['ear_pause_mode'], 0)

    def test_bad_nested_profile_does_not_crash_gui_config_load(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'gui.json'
            config.write_text(json.dumps({'devices': [{'mac': 'AA:BB:CC:DD:EE:FF', 'model': []}],
                                          'ear_pause_mode': 'invalid'}))
            with patch.object(B, 'CONFIG', config):
                result = B.load_config()
            self.assertEqual(result['devices'], [])
            self.assertEqual(result['ear_pause_mode'], 1)

    def test_runtime_io_failure_does_not_abandon_supervision(self):
        bus = Mock()
        def call(*args):
            if args[3] == 'NameHasOwner':
                return Mock(unpack=lambda: (False,))
            raise E.GLib.Error('no backend')
        bus.call_sync.side_effect = call
        child = Mock(pid=12345)
        child.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, XDG_RUNTIME_DIR=directory), \
             patch.object(sys, 'argv', ['engine', 'AABBCCDDEEFF']), \
             patch.object(E.Gio, 'bus_get_sync', return_value=bus), \
             patch.object(E.subprocess, 'Popen', return_value=child), \
             patch.object(E, 'stop_backend') as stop, patch.object(E.signal, 'signal'), \
             patch.object(E.GLib, 'timeout_add_seconds'), \
             patch.object(E.tempfile, 'mkstemp', side_effect=PermissionError('runtime unwritable')), \
             patch.object(sys, 'stderr', new_callable=io.StringIO) as diagnostic:
            self.assertEqual(E.main(), 1)
            stop.assert_called_once_with(child)
            self.assertIn('supervision failed', diagnostic.getvalue())

    def test_command_uses_verified_unique_owner_and_device(self):
        bus = Mock()
        def call(*args):
            if args[3] == 'GetNameOwner':
                return Mock(unpack=lambda: (':1.23',))
            if args[3] == 'GetAll':
                return Mock(unpack=lambda: ({'DeviceAddress': 'AA:BB:CC:DD:EE:FF'},))
            return Mock(unpack=lambda: ())
        bus.call_sync.side_effect = call
        with patch.object(B.Gio, 'bus_get_sync', return_value=bus):
            B.engine_call('SetNoiseControlMode', device={'mac': 'AA:BB:CC:DD:EE:FF'})
            self.assertEqual(bus.call_sync.call_args.args[0], ':1.23')
            bus.reset_mock()
            with self.assertRaisesRegex(RuntimeError, 'service changed'):
                B.engine_call('SetNoiseControlMode', device={'mac': '11:22:33:44:55:66'})
            self.assertNotIn('SetNoiseControlMode', [c.args[3] for c in bus.call_sync.call_args_list])

    def test_release_comparison_accepts_prerelease_and_unknown_versions(self):
        self.assertTrue(R.is_newer('0.2.0', '0.2.0-PRE.2'))
        self.assertTrue(R.is_newer('0.3.0', '0.2.0-PRE.2'))
        self.assertFalse(R.is_newer('0.2.0', 'unknown'))
        self.assertFalse(R.is_newer('bad', '0.2.0'))
