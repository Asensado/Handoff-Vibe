# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Asensado
"""BlueZ and systemd integration. All blocking calls run on the GUI's worker."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import socket
from gi.repository import Gio, GLib
from .models import BY_KEY, valid_mac, identify
from .settings import normalize_settings

CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'handoff'
CONFIG = CONFIG_DIR / 'gui.json'
ROOT = Path(__file__).resolve().parent.parent
INSTALLED = ROOT == Path('/usr/share/handoff')
DAEMON = '/usr/libexec/handoff/airpods-handoff' if INSTALLED else str(ROOT / 'build/airpods-handoff')
HELPER = '/usr/libexec/handoff/prepare-bluetooth'
EXTENSION_UUID = 'handoff-vibe@asensado.github.io'


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
    data = normalize_settings(data)
    candidates = data.get('devices', [])
    if not isinstance(candidates, list):
        candidates = []
    data['devices'] = [d for d in candidates if isinstance(d, dict) and valid_mac(d.get('mac')) and isinstance(d.get('model'), str) and d['model'] in BY_KEY]
    for d in data['devices']:
        d['mac'] = d['mac'].upper()
        if not isinstance(d.get('name'), str) or not d['name']:
            d['name'] = BY_KEY[d['model']].name
    if data.get('theme') not in ('system', 'light', 'dark'):
        data['theme'] = 'system'
    if data.get('selected') not in [d['mac'] for d in data['devices']]:
        data['selected'] = data['devices'][0]['mac'] if data['devices'] else None
    # The service's Start/Pause action controls core device switching.
    data['apple_handoff'] = True
    data.setdefault('auto_connect', False)
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
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if runtime and valid_mac(device.get('mac')):
        path = Path(runtime) / 'handoff' / (device['mac'].replace(':', '').upper() + '.log')
        try:
            with path.open('rb') as log:
                log.seek(0, 2)
                log.seek(max(0, log.tell() - 65536))
                text = log.read().decode('utf-8', errors='replace')
            if text:
                return text
        except OSError:
            pass
    return run(['journalctl', '--user', '-u', unit_for(device), '-n', '220', '--no-pager', '-o', 'short-iso'], timeout=8)


def protocol_state(device):
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime or device.get('legacy'):
        return {}
    try:
        return json.loads((Path(runtime) / 'handoff' / (device['mac'].replace(':', '') + '.json')).read_text())
    except (OSError, ValueError):
        return {}


EARPORT_BUS = 'io.github.anoryth.EarPort'
EARPORT_PATH = '/io/github/anoryth/EarPort'
EARPORT_IFACE = 'io.github.anoryth.EarPort1'


def engine_call(method, params=None, *, device=None):
    if not isinstance(device, dict) or not valid_mac(device.get('mac')):
        raise RuntimeError('Select a headset before sending a command.')
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    owner = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
        'org.freedesktop.DBus', 'GetNameOwner', GLib.Variant('(s)', (EARPORT_BUS,)),
        None, Gio.DBusCallFlags.NO_AUTO_START, 4000, None).unpack()[0]
    properties = bus.call_sync(owner, EARPORT_PATH, 'org.freedesktop.DBus.Properties',
        'GetAll', GLib.Variant('(s)', (EARPORT_IFACE,)), None,
        Gio.DBusCallFlags.NO_AUTO_START, 4000, None).unpack()[0]
    address = properties.get('DeviceAddress', '')
    if isinstance(address, GLib.Variant):
        address = address.unpack()
    if not isinstance(address, str) or address.upper() != device['mac'].upper():
        raise RuntimeError('The headset service changed. Refresh before sending another command.')
    result = bus.call_sync(owner, EARPORT_PATH, EARPORT_IFACE, method, params,
                          None, Gio.DBusCallFlags.NO_AUTO_START, 4000, None)
    return result.unpack() if result else ()


def engine_setting(key, enabled, device):
    methods = {'auto_connect': 'SetAutoConnect', 'apple_handoff': 'SetAppleHandoff', 'ear_pause_mode': 'SetEarPauseMode'}
    if key not in methods:
        raise ValueError('Unknown headset setting')
    engine_call(methods[key], GLib.Variant('(i)', (int(enabled),)) if key == 'ear_pause_mode' else GLib.Variant('(b)', (bool(enabled),)), device=device)


def set_noise_control(device, mode):
    if mode not in ('off', 'anc', 'transparency') or not valid_mac(device.get('mac')):
        raise ValueError('Invalid noise-control request')
    state = protocol_state(device)
    if state.get('backend') == 'earport':
        engine_call('SetNoiseControlMode', GLib.Variant('(s)', (mode,)), device=device)
        return dict(state, noise_pending=mode)
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime:
        raise RuntimeError('Your desktop session is unavailable')
    path = Path(runtime) / 'handoff' / (device['mac'].replace(':', '').upper() + '.sock')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(4)
        client.connect(str(path))
        client.sendall(json.dumps({'command': 'set-noise-control', 'mode': mode}).encode() + b'\n')
        reply = b''
        while b'\n' not in reply:
            chunk = client.recv(4096)
            if not chunk or len(reply) + len(chunk) > 8192:
                raise RuntimeError('The headset service returned an invalid response')
            reply += chunk
    data = json.loads(reply.split(b'\n', 1)[0])
    if not data.get('ok'):
        raise RuntimeError(data.get('error', 'The headset command failed'))
    return data.get('status', {})


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
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    (CONFIG_DIR / 'backups').mkdir(exist_ok=True, mode=0o700)
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
    """Compatibility error for callers of the retired export API; no side effects."""
    raise RuntimeError('CLI transfer has been retired. Handoff Vibe no longer creates or restores CLI services; existing migration backups are preserved.')


def extension_call(method, params=None):
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result = bus.call_sync('org.gnome.Shell.Extensions', '/org/gnome/Shell/Extensions',
            'org.gnome.Shell.Extensions', method, params, None, Gio.DBusCallFlags.NONE, 8000, None)
        return result.unpack()
    except GLib.Error as exc:
        raise RuntimeError('Could not reach GNOME extension settings. After installing an update, '
            'sign out and back in, then check the Extensions app. ' + str(exc)) from exc


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


def proximity_settings():
    folder = (Path('/usr/share/gnome-shell/extensions') / EXTENSION_UUID / 'schemas') if INSTALLED else ROOT / 'gnome-extension/schemas'
    source = Gio.SettingsSchemaSource.new_from_directory(str(folder), Gio.SettingsSchemaSource.get_default(), False)
    schema = source.lookup('org.gnome.shell.extensions.handoff-earport', False)
    if not schema:
        raise RuntimeError('The GNOME companion schema is unavailable')
    return Gio.Settings.new_full(schema, None, None)


def proximity_enabled():
    return proximity_settings().get_boolean('proximity-card')


def set_proximity_enabled(enabled):
    proximity_settings().set_boolean('proximity-card', bool(enabled))
    Gio.Settings.sync()
