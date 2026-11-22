"""BlueZ and systemd integration. All blocking calls run on the GUI's worker."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from gi.repository import Gio, GLib
from .models import BY_KEY, valid_mac, identify

CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'handoff'
CONFIG = CONFIG_DIR / 'gui.json'
ROOT = Path(__file__).resolve().parent.parent
INSTALLED = ROOT == Path('/usr/share/handoff')
DAEMON = '/usr/libexec/handoff/airpods-handoff' if INSTALLED else str(ROOT / 'build/airpods-handoff')
HELPER = '/usr/libexec/handoff/prepare-bluetooth'


def run(args, check=True, timeout=15):
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f'{args[0]} failed')
    return result.stdout.strip()


def load_config():
    try:
        data = json.loads(CONFIG.read_text())
        if not isinstance(data, dict):
            raise ValueError('Expected an object')
    except (OSError, ValueError):
        data = {}
    candidates = data.get('devices', [])
    if not isinstance(candidates, list):
        candidates = []
    data['devices'] = [d for d in candidates if isinstance(d, dict) and valid_mac(d.get('mac')) and d.get('model') in BY_KEY]
    for d in data['devices']:
        d['mac'] = d['mac'].upper()
        if not isinstance(d.get('name'), str) or not d['name']:
            d['name'] = BY_KEY[d['model']].name
    if data.get('theme') not in ('system', 'light', 'dark'):
        data['theme'] = 'system'
    if data.get('selected') not in [d['mac'] for d in data['devices']]:
        data['selected'] = data['devices'][0]['mac'] if data['devices'] else None
    return data


def save_config(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(dir=CONFIG_DIR, prefix='.gui-')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(temp, CONFIG)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def legacy_device():
    import shlex
    path = Path.home() / '.config/systemd/user/airpods-handoff.service'
    try:
        text = path.read_text()
    except OSError:
        return None
    match = re.search(r'^ExecStart=(.*)$', text, re.M)
    try:
        args = shlex.split(match[1]) if match else []
    except ValueError:
        return None
    if len(args) != 2 or Path(args[0]).name != 'airpods-handoff' or not valid_mac(args[1]):
        return None
    hint = {'Name': re.search(r'^Description=(.*)$', text, re.M)[1] if 'Description=' in text else ''}
    model, _ = identify(hint)
    return {'mac': args[1].upper(), 'name': model.name if model else 'Existing headset', 'model': model.key if model else None, 'legacy': True}


def unit_for(device):
    if not valid_mac(device.get('mac')):
        raise ValueError('Invalid Bluetooth address')
    if device.get('legacy'):
        legacy = legacy_device()
        if not legacy or legacy['mac'] != device['mac']:
            raise RuntimeError('The existing service changed. Add this headset again.')
        return 'airpods-handoff.service'
    return 'handoff@' + device['mac'].replace(':', '') + '.service'


def ensure_unit(device):
    if device.get('legacy'):
        return
    if not os.path.isfile(DAEMON):
        raise RuntimeError('The Handoff engine is missing. Install the Debian package or build the source first.')
    # One fixed template; the validated instance is the only variable argument.
    directory = Path.home() / '.config/systemd/user'
    directory.mkdir(parents=True, exist_ok=True)
    template = directory / 'handoff@.service'
    content = f'''[Unit]
Description=Handoff audio switching (%i)
After=bluetooth.target pipewire-pulse.service pulseaudio.service
StartLimitIntervalSec=60
StartLimitBurst=8

[Service]
Type=simple
ExecStart="{DAEMON}" %i
Restart=on-failure
RestartSec=4
NoNewPrivileges=true

[Install]
WantedBy=default.target
'''
    if template.exists() and template.read_text() != content:
        raise RuntimeError('A different handoff@.service already exists. Back it up or rename it before continuing.')
    if not template.exists():
        template.write_text(content)
        run(['systemctl', '--user', 'daemon-reload'])


def service_action(device, action):
    if action not in ('start', 'stop', 'restart', 'enable', 'disable'):
        raise ValueError('Unknown service action')
    if action in ('start', 'restart', 'enable'):
        ensure_unit(device)
    args = ['systemctl', '--user', action]
    if action == 'enable':
        args.append('--now')
    args.append(unit_for(device))
    run(args)


def service_state(device):
    output = run(['systemctl', '--user', 'show', unit_for(device), '--property=ActiveState,SubState,UnitFileState,ExecMainStatus'], timeout=5)
    return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)


def read_logs(device):
    return run(['journalctl', '--user', '-u', unit_for(device), '-n', '220', '--no-pager', '-o', 'short-iso'], timeout=8)


def protocol_state(device):
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime or device.get('legacy'):
        return {}
    try:
        return json.loads((Path(runtime) / 'handoff' / (device['mac'].replace(':', '') + '.json')).read_text())
    except (OSError, ValueError):
        return {}


def bluetooth_ready(path=Path('/etc/bluetooth/main.conf')):
    try:
        section = ''
        for line in path.read_text().splitlines():
            clean = line.strip()
            if clean.startswith('['):
                section = clean.lower()
            if section == '[general]' and re.fullmatch(r'DeviceID\s*=\s*bluetooth:004c:0000:0000\s*', clean, re.I):
                return True
    except OSError:
        pass
    return False


class BlueZ:
    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

    def call(self, path, interface, method, parameters=None, timeout=8000):
        result = self.bus.call_sync('org.bluez', path, interface, method, parameters, None, Gio.DBusCallFlags.NONE, timeout, None)
        return result.unpack() if result is not None else ()

    def objects(self):
        return self.call('/', 'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects')[0]

    def devices(self):
        items, adapters = [], []
        for path, interfaces in self.objects().items():
            if 'org.bluez.Adapter1' in interfaces:
                adapters.append((path, interfaces['org.bluez.Adapter1']))
            props = interfaces.get('org.bluez.Device1')
            if not props:
                continue
            mac = props.get('Address', '')
            if not valid_mac(mac):
                continue
            model, verdict = identify(props)
            items.append(dict(path=path, mac=mac.upper(), name=props.get('Alias', props.get('Name', mac)), model=model.key if model else None,
                              verdict=verdict, paired=props.get('Paired', False), connected=props.get('Connected', False)))
        return items, adapters

    def set_property(self, path, interface, prop, value):
        return self.call(path, 'org.freedesktop.DBus.Properties', 'Set', GLib.Variant('(ssv)', (interface, prop, value)))

    def discover(self, enabled):
        adapters = [(p, i['org.bluez.Adapter1']) for p, i in self.objects().items() if 'org.bluez.Adapter1' in i]
        if not adapters:
            raise RuntimeError('No Bluetooth adapter found. Connect an adapter and try again.')
        powered = [p for p, a in adapters if a.get('Powered')]
        if not powered:
            raise RuntimeError('Bluetooth is off. Turn it on in Bluetooth settings, then scan again.')
        for path in powered:
            if enabled:
                # BlueZ discovery is reference counted by D-Bus connection.
                self.call(path, 'org.bluez.Adapter1', 'StartDiscovery')
            else:
                try:
                    self.call(path, 'org.bluez.Adapter1', 'StopDiscovery')
                except GLib.Error:
                    pass

    def connect(self, device):
        if not device.get('paired'):
            # Uses the desktop's Bluetooth agent for any required confirmation.
            try:
                self.call(device['path'], 'org.bluez.Device1', 'Pair', timeout=60000)
            except GLib.Error as error:
                if Gio.DBusError.get_remote_error(error) != 'org.bluez.Error.AlreadyExists':
                    raise
        self.set_property(device['path'], 'org.bluez.Device1', 'Trusted', GLib.Variant('b', True))
        try:
            self.call(device['path'], 'org.bluez.Device1', 'Connect', timeout=25000)
        except GLib.Error as error:
            if Gio.DBusError.get_remote_error(error) != 'org.bluez.Error.AlreadyConnected':
                raise


def migrate_legacy(config, model_override=None):
    """Transactional adoption of the known upstream per-user service.

    Keep its original bytes and prior activity/startup state; roll back on failure.
    Never migrate a system service, arbitrary unit, or unrecognized command.
    """
    import datetime
    import shutil
    device = legacy_device()
    if not device:
        return None
    if model_override in BY_KEY:
        device['model'] = model_override
        if device['name'] == 'Existing headset':
            device['name'] = BY_KEY[model_override].name
    if not device['model']:
        raise RuntimeError('An existing service was found, but its headset model could not be identified. Choose its model in setup to migrate it.')
    old = Path.home() / '.config/systemd/user/airpods-handoff.service'
    if old.is_symlink():
        raise RuntimeError('The existing service is a custom symlink. Automatic migration is unavailable; the original service has been kept.')
    new = dict(device)
    new.pop('legacy', None)
    # Check dependencies and unit conflicts before stopping anything.
    ensure_unit(new)
    previous = service_state(device)
    enabled = previous.get('UnitFileState') == 'enabled'
    active = previous.get('ActiveState') in ('active', 'activating')
    backup = CONFIG_DIR / 'backups' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(old, backup / old.name)
    (backup / 'state.json').write_text(json.dumps({'enabled': enabled, 'active': active, 'mac': device['mac']}))
    removed = False
    try:
        run(['systemctl', '--user', 'stop', 'airpods-handoff.service'])
        run(['systemctl', '--user', 'disable', 'airpods-handoff.service'])
        old.unlink()
        removed = True
        run(['systemctl', '--user', 'daemon-reload'])
        if enabled:
            service_action(new, 'enable')
            if not active:
                service_action(new, 'stop')
        elif active:
            service_action(new, 'start')
        new_state = service_state(new)
        if active and new_state.get('ActiveState') not in ('active', 'activating'):
            raise RuntimeError('The replacement service did not start.')
        updated = dict(config)
        updated['devices'] = [d for d in config.get('devices', []) if d['mac'] != new['mac']] + [new]
        updated['selected'] = new['mac']
        updated['migration_backup'] = str(backup)
        updated['cli_mode'] = False
        save_config(updated)
        config.clear()
        config.update(updated)
        return new
    except Exception as exc:
        failures = []
        for args in (['systemctl', '--user', 'disable', '--now', unit_for(new)],):
            try:
                run(args)
            except Exception as error:
                failures.append(str(error))
        if removed:
            shutil.copy2(backup / old.name, old)
        for args in ([['systemctl', '--user', 'daemon-reload']] +
                     ([['systemctl', '--user', 'enable', 'airpods-handoff.service']] if enabled else []) +
                     ([['systemctl', '--user', 'start', 'airpods-handoff.service']] if active else [])):
            try:
                run(args)
            except Exception as error:
                failures.append(str(error))
        suffix = (' Rollback needs attention: ' + '; '.join(failures)) if failures else ' The original service was restored.'
        raise RuntimeError('Migration failed: ' + str(exc) + suffix) from exc


def restore_cli(config):
    """Restore the original CLI unit, with rollback of all GUI service states."""
    import shutil
    import shlex
    devices = list(config.get('devices', []))
    if not devices:
        raise RuntimeError('Set up a headset before transitioning to the CLI version.')
    old = Path.home() / '.config/systemd/user/airpods-handoff.service'
    if old.exists() or old.is_symlink():
        raise RuntimeError('A CLI service already exists. It was kept unchanged.')
    backup_path = config.get('migration_backup')
    if backup_path:
        backup = Path(backup_path).resolve()
        allowed = (CONFIG_DIR / 'backups').resolve()
        if not backup.is_relative_to(allowed) or backup == allowed:
            raise RuntimeError('The original service backup is outside the Handoff backup folder.')
        source = backup / old.name
        if source.is_symlink() or not source.is_file():
            raise RuntimeError('The original service backup is missing. Your GUI service has been kept.')
        text = source.read_text()
        state = json.loads((backup / 'state.json').read_text())
        match = re.search(r'^ExecStart=(.*)$', text, re.M)
        args = shlex.split(match[1]) if match else []
        if len(args) != 2 or not valid_mac(args[1]) or args[1].upper() != state.get('mac') or not Path(args[0]).is_absolute():
            raise RuntimeError('The backup does not contain the expected original Handoff command.')
        if not os.path.isfile(args[0]) or not os.access(args[0], os.X_OK):
            raise RuntimeError('The original CLI executable is no longer available. Restore its original installation before trying again.')
        selected = next((d for d in devices if d['mac'] == state['mac']), None)
        if selected is None:
            raise RuntimeError('The backed-up headset is no longer in your profiles. Add it again before restoring.')
    else:
        selected = next((d for d in devices if d['mac'] == config.get('selected')), devices[0])
        if not os.path.isfile(DAEMON):
            raise RuntimeError('The command-line audio engine is missing.')
        text = f'''[Unit]
Description={BY_KEY[selected['model']].name} Linux-Apple Handoff
After=bluetooth.target

[Service]
Type=simple
ExecStart="{DAEMON}" {selected['mac']}
Restart=on-failure
RestartSec=4

[Install]
WantedBy=default.target
'''
        current = service_state(selected)
        state = dict(mac=selected['mac'], enabled=current.get('UnitFileState') == 'enabled', active=current.get('ActiveState') in ('active', 'activating'))
    snapshots = [(dict(d), service_state(d)) for d in devices]
    wrote = False
    try:
        for d, _ in snapshots:
            service_action(d, 'stop')
            service_action(d, 'disable')
        old.parent.mkdir(parents=True, exist_ok=True)
        # Refuse to overwrite a service created by another process during transition.
        with old.open('x') as f:
            f.write(text)
        wrote = True
        run(['systemctl', '--user', 'daemon-reload'])
        if state.get('enabled'):
            run(['systemctl', '--user', 'enable', 'airpods-handoff.service'])
        if state.get('active'):
            run(['systemctl', '--user', 'start', 'airpods-handoff.service'])
            legacy = dict(selected, legacy=True)
            if service_state(legacy).get('ActiveState') not in ('active', 'activating'):
                raise RuntimeError('The restored CLI service did not start.')
        updated = dict(config, cli_mode=True, selected=selected['mac'])
        save_config(updated)
        config.clear()
        config.update(updated)
        return selected
    except Exception as exc:
        failures = []
        if wrote:
            try:
                run(['systemctl', '--user', 'disable', '--now', 'airpods-handoff.service'])
                old.unlink()
                run(['systemctl', '--user', 'daemon-reload'])
            except Exception as error:
                failures.append(str(error))
        for d, before in snapshots:
            try:
                if before.get('UnitFileState') == 'enabled':
                    service_action(d, 'enable')
                    if before.get('ActiveState') not in ('active', 'activating'):
                        service_action(d, 'stop')
                elif before.get('ActiveState') in ('active', 'activating'):
                    service_action(d, 'start')
            except Exception as error:
                failures.append(str(error))
        suffix = ' The GUI services were restored.' if not failures else ' Rollback needs attention: ' + '; '.join(failures)
        raise RuntimeError('CLI transition failed: ' + str(exc) + suffix) from exc


EXTENSION_UUID = 'handoff-vibe@asensado.github.io'

def extension_call(method, params=None):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    try:
        result = bus.call_sync('org.gnome.Shell.Extensions', '/org/gnome/Shell/Extensions', 'org.gnome.Shell.Extensions', method, params, None, Gio.DBusCallFlags.NONE, 8000, None)
        return result.unpack()
    except GLib.Error as exc:
        raise RuntimeError('GNOME top-bar status needs GNOME Shell 48. After installing the update, sign out and back in once so GNOME discovers the extension, then enable it here. ' + str(exc)) from exc


def extension_enabled():
    info = extension_call('GetExtensionInfo', GLib.Variant('(s)', (EXTENSION_UUID,)))[0]
    if not info:
        raise RuntimeError('Sign out and back in once after installing this update, then enable GNOME top-bar status here. The companion extension supports GNOME Shell 48.')
    return info.get('state') == 1


def set_extension_enabled(enabled):
    if enabled:
        result = extension_call('EnableExtension', GLib.Variant('(s)', (EXTENSION_UUID,)))
    else:
        result = extension_call('DisableExtension', GLib.Variant('(s)', (EXTENSION_UUID,)))
    if not result or not result[0]:
        raise RuntimeError('GNOME could not change the extension. Check the Extensions app for compatibility or disabled extensions.')
