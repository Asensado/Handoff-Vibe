import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {statusFor} from './state.js';

export default class HandoffVibeStatus extends Extension {
    enable() {
        this._cancellable = new Gio.Cancellable();
        this._button = new PanelMenu.Button(0.0, 'Handoff Vibe');
        const box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        box.add_child(new St.Icon({icon_name: 'audio-headphones-symbolic', style_class: 'system-status-icon'}));
        this._dot = new St.Label({text: '●', y_align: Clutter.ActorAlign.CENTER});
        this._label = new St.Label({text: 'Waiting', y_align: Clutter.ActorAlign.CENTER});
        box.add_child(this._dot);
        box.add_child(this._label);
        this._button.add_child(box);
        this._device = new PopupMenu.PopupMenuItem('Handoff Vibe', {reactive: false});
        this._button.menu.addMenuItem(this._device);
        const open = new PopupMenu.PopupMenuItem('Open Handoff Vibe');
        open.connect('activate', () => {
            const app = Gio.DesktopAppInfo.new('io.github.asensato.Handoff.desktop');
            if (app)
                app.launch([], global.create_app_launch_context(0, -1));
            else
                Main.notify('Handoff Vibe', 'The application launcher is unavailable. Reinstall the Handoff package.');
        });
        this._button.menu.addMenuItem(open);
        Main.panel.addToStatusArea(this.uuid, this._button);
        this._refresh();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 4, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _readJson(path, callback) {
        const file = Gio.File.new_for_path(path);
        const cancellable = this._cancellable;
        file.load_contents_async(cancellable, (source, result) => {
            if (cancellable.is_cancelled())
                return;
            let parsed = null;
            try {
                const [ok, bytes] = source.load_contents_finish(result);
                if (ok)
                    parsed = JSON.parse(new TextDecoder().decode(bytes));
            } catch (_) {
                // Missing state is normal before a headset has been set up.
            }
            callback(parsed);
        });
    }

    _serviceState(unit, callback) {
        const cancellable = this._cancellable;
        Gio.DBus.session.call('org.freedesktop.systemd1', '/org/freedesktop/systemd1',
            'org.freedesktop.systemd1.Manager', 'GetUnit', new GLib.Variant('(s)', [unit]),
            null, Gio.DBusCallFlags.NONE, 3000, cancellable, (bus, result) => {
                if (cancellable.is_cancelled())
                    return;
                let path;
                try {
                    [path] = bus.call_finish(result).deepUnpack();
                } catch (error) {
                    const name = Gio.DBusError.get_remote_error(error);
                    callback(name === 'org.freedesktop.systemd1.NoSuchUnit' ? 'inactive' : 'unavailable');
                    return;
                }
                bus.call('org.freedesktop.systemd1', path, 'org.freedesktop.DBus.Properties',
                    'Get', new GLib.Variant('(ss)', ['org.freedesktop.systemd1.Unit', 'ActiveState']),
                    null, Gio.DBusCallFlags.NONE, 3000, cancellable, (connection, response) => {
                        if (cancellable.is_cancelled())
                            return;
                        try {
                            const [value] = connection.call_finish(response).deepUnpack();
                            callback(value.deepUnpack());
                        } catch (_) {
                            callback('unavailable');
                        }
                    });
            });
    }

    _refresh() {
        if (this._busy)
            return;
        this._busy = true;
        this._readJson(GLib.build_filenamev([GLib.get_user_config_dir(), 'handoff', 'gui.json']), config => {
            if (!this._button)
                return;
            const mac = config?.selected;
            const devices = Array.isArray(config?.devices) ? config.devices : [];
            const device = devices.find(d => d?.mac === mac);
            this._device.label.text = device?.name ?? 'Handoff Vibe';
            if (config?.cli_mode || !mac || !/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/i.test(mac)) {
                this._paint(config, 'inactive', null);
                return;
            }
            const compact = mac.replaceAll(':', '').toUpperCase();
            this._serviceState(`handoff@${compact}.service`, service => {
                const runtime = GLib.get_user_runtime_dir();
                this._readJson(GLib.build_filenamev([runtime, 'handoff', `${compact}.json`]), protocol => {
                    this._paint(config, service, protocol);
                });
            });
        });
    }

    _paint(config, service, protocol) {
        this._busy = false;
        if (!this._button)
            return;
        const [text, color] = statusFor(config, service, protocol, Date.now() / 1000);
        this._label.text = text;
        this._dot.set_style(`color: ${color}; margin-left: 4px; margin-right: 5px;`);
        this._button.accessible_name = `Handoff Vibe: ${text}`;
    }

    disable() {
        if (this._timer)
            GLib.Source.remove(this._timer);
        this._timer = null;
        this._cancellable?.cancel();
        this._cancellable = null;
        this._button?.destroy();
        this._button = null;
        this._dot = null;
        this._label = null;
        this._device = null;
        this._busy = false;
    }
}
