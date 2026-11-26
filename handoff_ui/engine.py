# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Asensado
"""Handoff service supervisor for its separately licensed Earport backend."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from gi.repository import Gio, GLib

BUS = 'io.github.anoryth.EarPort'
PATH = '/io/github/anoryth/EarPort'
INTERFACE = 'io.github.anoryth.EarPort1'


def unpack(value):
    if isinstance(value, GLib.Variant):
        return unpack(value.unpack())
    if isinstance(value, dict):
        return {key: unpack(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [unpack(item) for item in value]
    return value


def snapshot(properties):
    p = unpack(properties)
    connected = p.get('Connected', False)
    return dict(updated=time.time(), backend='earport', ready=connected, switching=p.get('Reconnecting', False),
                error='', owner={'computer': 'linux'}.get(p.get('AudioSource'), p.get('AudioSource', '')),
                controls_ready=connected and p.get('SupportsANC', False),
                noise_control=p.get('NoiseControlMode', ''), noise_pending='', control_error='',
                battery_left=p.get('BatteryLeft', -1), battery_right=p.get('BatteryRight', -1),
                battery_case=p.get('BatteryCase', -1), charging_left=p.get('ChargingLeft', False),
                charging_right=p.get('ChargingRight', False), charging_case=p.get('ChargingCase', False),
                nearby=p.get('NearbyBattery', {}), auto_connect=p.get('AutoConnect', False),
                apple_handoff=p.get('AppleHandoff', False), supports_adaptive=p.get('SupportsAdaptive', False),
                listening_minutes=p.get('ListeningTimeRemaining', -1), ear_pause_mode=p.get('EarPauseMode', 1))


def main():
    import re
    compact = sys.argv[1].replace(':', '').upper() if len(sys.argv) == 2 else ''
    if not re.fullmatch('[0-9A-F]{12}', compact):
        return 2
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime:
        return 3
    folder = Path(runtime) / 'handoff'
    folder.mkdir(mode=0o700, exist_ok=True)
    lock = (folder / (compact + '.lock')).open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another Handoff engine manages this headset', file=sys.stderr)
        return 4
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    existing = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                            'NameHasOwner', GLib.Variant('(s)', (BUS,)), None,
                            Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
    if existing:
        print('Another Earport backend owns the control service. Stop it before starting Handoff.', file=sys.stderr)
        return 5
    root = Path(__file__).resolve().parent.parent
    executable = '/usr/libexec/handoff/earport-daemon' if root == Path('/usr/share/handoff') else str(root / 'earport/daemon/build/earport-daemon')
    env = dict(os.environ, HANDOFF_DEVICE_ADDRESS=':'.join(compact[i:i+2] for i in range(0, 12, 2)))
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    env['XDG_CONFIG_HOME'] = str(config_home / 'handoff/engine-config')
    # Some desktop users cannot read journald. Keep a private bounded runtime
    # log so Handoff's diagnostics do not depend on journal group membership.
    log_path = folder / (compact + '.log')
    if log_path.exists():
        log_path.replace(folder / (compact + '.previous.log'))
    log = os.fdopen(os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_APPEND, 0o600), 'w')
    child = subprocess.Popen([executable], env=env, stdout=log, stderr=subprocess.STDOUT)
    loop = GLib.MainLoop()
    configured = False
    result = 0
    previous_owner = ''
    switching_until = 0

    def save(status):
        descriptor, temporary = tempfile.mkstemp(dir=folder, prefix='.status-')
        try:
            with os.fdopen(descriptor, 'w') as output:
                json.dump(status, output)
            os.replace(temporary, folder / (compact + '.json'))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def tick():
        nonlocal configured, result, previous_owner, switching_until
        if os.fstat(log.fileno()).st_size > 2 * 1024 * 1024:
            os.ftruncate(log.fileno(), 0)
        if child.poll() is not None:
            result = child.returncode or 1
            save(dict(updated=time.time(), ready=False, backend='earport', error='The Bluetooth backend stopped.'))
            loop.quit()
            return False
        try:
            properties = bus.call_sync(BUS, PATH, 'org.freedesktop.DBus.Properties', 'GetAll',
                                      GLib.Variant('(s)', (INTERFACE,)), None,
                                      Gio.DBusCallFlags.NO_AUTO_START, 1500, None).unpack()[0]
            if not configured:
                try:
                    settings = json.loads((config_home / 'handoff/gui.json').read_text())
                except (OSError, ValueError):
                    settings = {}
                # Switching is Handoff's core function. The Start/Pause service
                # action is its single user-facing control.
                settings['apple_handoff'] = True
                for key, method in [('auto_connect', 'SetAutoConnect'), ('apple_handoff', 'SetAppleHandoff'), ('ear_pause_mode', 'SetEarPauseMode')]:
                    if key in settings:
                        bus.call_sync(BUS, PATH, INTERFACE, method, (GLib.Variant('(i)', (int(settings[key]),)) if key == 'ear_pause_mode' else GLib.Variant('(b)', (bool(settings[key]),))),
                                      None, Gio.DBusCallFlags.NO_AUTO_START, 2000, None)
                configured = True
            state = snapshot(properties)
            owner = state['owner']
            if previous_owner in ('linux', 'other') and owner in ('linux', 'other') and owner != previous_owner:
                switching_until = time.time() + 3
            if owner in ('linux', 'other'):
                previous_owner = owner
            state['switching_until'] = switching_until
            state['switching'] = state['switching'] or switching_until > time.time()
            save(state)
        except GLib.Error:
            save(dict(updated=time.time(), ready=False, backend='earport', error='Waiting for the Bluetooth backend.'))
        return True

    def stop(*_):
        loop.quit()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    GLib.timeout_add_seconds(2, tick)
    # Publish transitions immediately; a short switch can be missed by polling.
    subscription = bus.signal_subscribe(BUS, 'org.freedesktop.DBus.Properties', 'PropertiesChanged',
                                        PATH, None, Gio.DBusSignalFlags.NONE, lambda *_: tick())
    try:
        if tick():
            loop.run()
    finally:
        bus.signal_unsubscribe(subscription)
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        log.close()
        save(dict(updated=time.time(), ready=False, backend='earport', error=''))
    return result


if __name__ == '__main__':
    raise SystemExit(main())
