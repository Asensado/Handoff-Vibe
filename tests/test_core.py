import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from handoff_ui import backend as B
from handoff_ui.models import identify, product_id, valid_mac

loader = importlib.machinery.SourceFileLoader('prepare', str(Path(__file__).resolve().parents[1] / 'packaging/prepare-bluetooth'))
spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)

class ModelTests(unittest.TestCase):
    def test_unsupported_id_overrules_friendly_name(self):
        self.assertEqual(identify({'Name': 'AirPods Pro', 'Modalias': 'bluetooth:v004Cp2011d0001'}), (None, 'unsupported'))
    def test_known_model_id(self):
        model, status = identify({'Alias': 'Renamed headphones', 'Modalias': 'bluetooth:v004Cp2014d0001'})
        self.assertEqual((model.key, status), ('airpodspro2', 'detected'))
    def test_beats_and_name_only_confirmation(self):
        model, status = identify({'Name': 'Powerbeats Fit Linux-Apple Handoff'})
        self.assertEqual((model.key, status), ('powerbeatsfit', 'confirm'))
    def test_unknown_identifier_not_overridden(self):
        self.assertEqual(identify({'Name': 'AirPods Pro', 'Modalias': 'bluetooth:v004Cp9999d0001'}), (None, 'unknown'))
    def test_studio_buds_rejected(self):
        self.assertEqual(identify({'Name': "Gab’s Beats Studio Buds +"}), (None, 'unsupported'))
    def test_apple_ble_model_little_endian(self):
        model, status = identify({'ManufacturerData': {76: [7, 25, 1, 0x12, 0x20]}})
        self.assertEqual((model.key, status), ('beatsfitpro', 'detected'))
    def test_no_arbitrary_manufacturer_match(self):
        self.assertIsNone(product_id({'ManufacturerData': {123: [7, 25, 1, 0x12, 0x20]}}))
    def test_short_packet(self):
        self.assertIsNone(product_id({'ManufacturerData': {76: [7, 25]}}))
    def test_mac_validation(self):
        self.assertTrue(valid_mac('AA:BB:CC:DD:EE:FF'))
        for address in ('../service', 'AA:BB:CC:DD:EE:FF; true', None, ''):
            self.assertFalse(valid_mac(address))

class PreparationTests(unittest.TestCase):
    def test_preserve_other_settings_and_sections(self):
        original = '# hello\n[General]\nName = Laptop\nDeviceID = bluetooth:1234:0000:0000\n[Policy]\nAutoEnable = true\n'
        result = helper.prepared_config(original)
        self.assertEqual(result, '# hello\n[General]\nDeviceID = bluetooth:004C:0000:0000\nName = Laptop\n[Policy]\nAutoEnable = true\n')
        self.assertEqual(helper.prepared_config(result), result)
    def test_add_missing_section(self):
        self.assertIn('[General]\nDeviceID = bluetooth:004C:0000:0000', helper.prepared_config('[Policy]\nAutoEnable = true\n'))
    def test_duplicate_active_settings_removed(self):
        result = helper.prepared_config('[General]\nDeviceID=x\nDeviceID=y\n# DeviceID=z\n')
        self.assertEqual(result.count('DeviceID = bluetooth:'), 1)
        self.assertIn('# DeviceID=z', result)

class ConfigTests(unittest.TestCase):
    def test_invalid_profiles_filtered_and_selection_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'gui.json'
            path.write_text(json.dumps({'selected': 'bad', 'devices': [{'mac': 'AA:BB:CC:DD:EE:FF', 'model': 'powerbeatsfit'}, {'mac': 'invalid', 'model': 'airpods2'}]}))
            with patch.object(B, 'CONFIG', path):
                config = B.load_config()
            self.assertEqual(len(config['devices']), 1)
            self.assertEqual(config['selected'], 'AA:BB:CC:DD:EE:FF')
    def test_bad_config_shape_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'gui.json'
            path.write_text('{"devices": null, "theme": "invalid"}')
            with patch.object(B, 'CONFIG', path):
                config = B.load_config()
            self.assertEqual(config['devices'], [])
            self.assertEqual(config['theme'], 'system')

    def test_unit_rejects_injection(self):
        with self.assertRaises(ValueError):
            B.unit_for({'mac': '../../something'})

class MigrationTests(unittest.TestCase):
    def migration_fixture(self, home):
        old = home / '.config/systemd/user/airpods-handoff.service'
        old.parent.mkdir(parents=True)
        old.write_text('[Unit]\nDescription=Powerbeats Fit Linux-Apple Handoff\n[Service]\nExecStart=/old/airpods-handoff AA:BB:CC:DD:EE:FF\n')
        return old
    def test_migration_preserves_state_and_backs_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            old = self.migration_fixture(home)
            original = old.read_bytes()
            config = {'devices': [], 'selected': None}
            commands = []
            with patch.object(Path, 'home', return_value=home), patch.object(B, 'CONFIG_DIR', home / 'config'), patch.object(B, 'ensure_unit'), patch.object(B, 'save_config'), patch.object(B, 'service_state', return_value={'ActiveState': 'active', 'UnitFileState': 'enabled'}), patch.object(B, 'run', side_effect=lambda args, **_: commands.append(args) or ''):
                migrated = B.migrate_legacy(config)
            self.assertFalse(old.exists())
            self.assertEqual(migrated['model'], 'powerbeatsfit')
            self.assertEqual((Path(config['migration_backup']) / old.name).read_bytes(), original)
            self.assertTrue(any('enable' in c and '--now' in c for c in commands))
            self.assertFalse(migrated.get('legacy', False))
    def test_failed_start_restores_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            old = self.migration_fixture(home)
            original = old.read_bytes()
            config = {'devices': [], 'selected': None}
            commands = []
            def run(args, **_):
                commands.append(args)
                if 'enable' in args and '--now' in args:
                    raise RuntimeError('Cannot start replacement')
                return ''
            with patch.object(Path, 'home', return_value=home), patch.object(B, 'CONFIG_DIR', home / 'config'), patch.object(B, 'ensure_unit'), patch.object(B, 'save_config'), patch.object(B, 'service_state', return_value={'ActiveState': 'active', 'UnitFileState': 'enabled'}), patch.object(B, 'run', side_effect=run):
                with self.assertRaisesRegex(RuntimeError, 'original service was restored'):
                    B.migrate_legacy(config)
            self.assertEqual(old.read_bytes(), original)
            self.assertEqual(config['devices'], [])
            self.assertIn(['systemctl', '--user', 'start', 'airpods-handoff.service'], commands)
    def test_disabled_service_remains_disabled_and_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.migration_fixture(home)
            config = {'devices': [], 'selected': None}
            commands = []
            with patch.object(Path, 'home', return_value=home), patch.object(B, 'CONFIG_DIR', home / 'config'), patch.object(B, 'ensure_unit'), patch.object(B, 'save_config'), patch.object(B, 'service_state', return_value={'ActiveState': 'inactive', 'UnitFileState': 'disabled'}), patch.object(B, 'run', side_effect=lambda args, **_: commands.append(args) or ''):
                B.migrate_legacy(config)
            self.assertFalse(any('enable' in c or ('start' in c) for c in commands))
    def test_unknown_legacy_model_can_be_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            old = self.migration_fixture(home)
            old.write_text(old.read_text().replace('Powerbeats Fit Linux-Apple Handoff', 'Audio switching'))
            config = {'devices': [], 'selected': None}
            with patch.object(Path, 'home', return_value=home), patch.object(B, 'CONFIG_DIR', home / 'config'), patch.object(B, 'ensure_unit'), patch.object(B, 'save_config'), patch.object(B, 'service_state', return_value={'ActiveState': 'inactive', 'UnitFileState': 'disabled'}), patch.object(B, 'run', return_value=''):
                result = B.migrate_legacy(config, model_override='powerbeatsfit')
            self.assertEqual(result['model'], 'powerbeatsfit')
            self.assertEqual(result['name'], 'Powerbeats Fit')

    def test_preflight_failure_leaves_original_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            old = self.migration_fixture(home)
            with patch.object(Path, 'home', return_value=home), patch.object(B, 'ensure_unit', side_effect=RuntimeError('Conflict')), patch.object(B, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'Conflict'):
                    B.migrate_legacy({'devices': []})
                run.assert_not_called()
            self.assertTrue(old.exists())

if __name__ == '__main__':
    unittest.main()

class RestoreTests(unittest.TestCase):
    def fixture(self, home):
        config_dir = home / '.config/handoff'
        backup = config_dir / 'backups/original'
        backup.mkdir(parents=True)
        executable = home / 'original/airpods-handoff'
        executable.parent.mkdir()
        executable.write_text('#!/bin/sh\nexit 0\n')
        executable.chmod(0o755)
        text = f'[Unit]\nDescription=Powerbeats Fit Linux-Apple Handoff\n[Service]\nExecStart={executable} AA:BB:CC:DD:EE:FF\n'
        (backup / 'airpods-handoff.service').write_text(text)
        (backup / 'state.json').write_text(json.dumps(dict(mac='AA:BB:CC:DD:EE:FF', enabled=True, active=True)))
        d = dict(mac='AA:BB:CC:DD:EE:FF', model='powerbeatsfit', name='Powerbeats Fit')
        return config_dir, dict(devices=[d], selected=d['mac'], migration_backup=str(backup)), text, executable

    def test_restore_exact_original_and_persist_cli_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            directory, config, text, _ = self.fixture(home)
            commands=[]
            with patch.object(Path,'home',return_value=home), patch.object(B,'CONFIG_DIR',directory), patch.object(B,'save_config'), patch.object(B,'service_state',return_value=dict(ActiveState='active',UnitFileState='enabled')), patch.object(B,'ensure_unit'), patch.object(B,'run',side_effect=lambda args,**_:commands.append(args) or ''):
                B.restore_cli(config)
            self.assertEqual((home/'.config/systemd/user/airpods-handoff.service').read_text(),text)
            self.assertTrue(config['cli_mode'])
            self.assertIn(['systemctl','--user','start','airpods-handoff.service'],commands)

    def test_missing_original_binary_leaves_gui_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); directory,config,_,executable=self.fixture(home)
            executable.unlink()
            with patch.object(Path,'home',return_value=home), patch.object(B,'CONFIG_DIR',directory), patch.object(B,'run') as run:
                with self.assertRaisesRegex(RuntimeError,'executable is no longer available'): B.restore_cli(config)
                run.assert_not_called()
            self.assertFalse(config.get('cli_mode',False))

    def test_cli_start_failure_restores_gui(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); directory,config,_,_=self.fixture(home)
            commands=[]
            def run(args,**_):
                commands.append(args)
                if args == ['systemctl','--user','start','airpods-handoff.service']: raise RuntimeError('CLI failed')
                return ''
            with patch.object(Path,'home',return_value=home), patch.object(B,'CONFIG_DIR',directory), patch.object(B,'save_config'), patch.object(B,'ensure_unit'), patch.object(B,'service_state',return_value=dict(ActiveState='active',UnitFileState='enabled')), patch.object(B,'run',side_effect=run):
                with self.assertRaisesRegex(RuntimeError,'GUI services were restored'): B.restore_cli(config)
            self.assertFalse((home/'.config/systemd/user/airpods-handoff.service').exists())
            self.assertFalse(config.get('cli_mode',False))
            self.assertIn(['systemctl','--user','enable','--now','handoff@AABBCCDDEEFF.service'],commands)

    def test_external_backup_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); directory,config,_,_=self.fixture(home)
            config['migration_backup'] = str(home/'outside')
            with patch.object(Path,'home',return_value=home),patch.object(B,'CONFIG_DIR',directory),patch.object(B,'run') as run:
                with self.assertRaisesRegex(RuntimeError,'outside the Handoff backup folder'): B.restore_cli(config)
                run.assert_not_called()

    def test_transition_without_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); directory,config,_,executable=self.fixture(home)
            config.pop('migration_backup')
            with patch.object(Path,'home',return_value=home),patch.object(B,'CONFIG_DIR',directory),patch.object(B,'DAEMON',str(executable)),patch.object(B,'save_config'),patch.object(B,'ensure_unit'),patch.object(B,'service_state',return_value=dict(ActiveState='inactive',UnitFileState='disabled')),patch.object(B,'run',return_value=''):
                B.restore_cli(config)
            self.assertTrue(config['cli_mode'])
            with patch.object(Path,'home',return_value=home):
                self.assertEqual(B.legacy_device()['mac'], config['selected'])
            self.assertIn(str(executable),(home/'.config/systemd/user/airpods-handoff.service').read_text())

class VerseTests(unittest.TestCase):
    def test_same_local_day_is_stable_and_next_day_changes(self):
        from datetime import date,timedelta
        from handoff_ui.verses import daily_verse
        day=date(2026,11,22)
        self.assertEqual(daily_verse(day),daily_verse(day))
        self.assertNotEqual(daily_verse(day),daily_verse(day+timedelta(days=1)))
    def test_month_and_year_boundaries(self):
        from datetime import date
        from handoff_ui.verses import daily_verse
        self.assertNotEqual(daily_verse(date(2026,12,31)),daily_verse(date(2027,1,1)))
    def test_catalog_contains_clean_unique_text(self):
        from handoff_ui.verses import CATALOG
        self.assertEqual(len(CATALOG),31)
        self.assertEqual(len({v['reference'] for v in CATALOG}),31)
        self.assertTrue(all('\\' not in v['text'] and 'strong=' not in v['text'] for v in CATALOG))
