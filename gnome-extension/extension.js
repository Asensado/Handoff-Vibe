// SPDX-License-Identifier: GPL-3.0-or-later
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {statusFor, protocolFromProperties, unpack, commandMatches} from './state.js';
import {ProximityCard} from './earport/proximityCard.js';

const BUS = 'io.github.anoryth.EarPort';
const PATH = '/io/github/anoryth/EarPort';
const IFACE = 'io.github.anoryth.EarPort1';
const PROPERTIES = ['Connected', 'DeviceAddress', 'AudioSource', 'Reconnecting',
    'SupportsANC', 'SupportsAdaptive', 'NoiseControlMode', 'BatteryLeft', 'BatteryRight',
    'BatteryCase', 'ChargingLeft', 'ChargingRight', 'ChargingCase',
    'ListeningTimeRemaining', 'NearbyBattery'];

function verticalBox(params = {}) {
    return new St.BoxLayout({...params,
        ...('orientation' in St.BoxLayout.prototype
            ? {orientation: Clutter.Orientation.VERTICAL} : {vertical: true})});
}

export default class HandoffVibeStatus extends Extension {
    enable() {
        this._cancellable = new Gio.Cancellable();
        this._config = null;
        this._protocol = null;
        this._service = 'inactive';
        this._lastOwner = '';
        this._switchUntil = 0;
        this._button = new PanelMenu.Button(0.0, 'Handoff Vibe');
        const panel = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        panel.add_child(new St.Icon({icon_name: 'audio-headphones-symbolic', style_class: 'system-status-icon'}));
        this._dot = new St.Label({text: '●', y_align: Clutter.ActorAlign.CENTER});
        this._label = new St.Label({text: 'Waiting', y_align: Clutter.ActorAlign.CENTER});
        panel.add_child(this._dot);
        panel.add_child(this._label);
        this._button.add_child(panel);

        // Device and noise controls belong to this top-bar menu. There is no
        // Quick Settings tile and no duplicate volume or output selector.
        const header = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        header.add_style_class_name('handoff-device-header');
        header.add_child(new St.Icon({icon_name: 'audio-headphones-symbolic', icon_size: 32,
            style_class: 'handoff-device-icon'}));
        const details = verticalBox({x_expand: true});
        this._deviceName = new St.Label({text: 'Handoff Vibe', style_class: 'handoff-device-name'});
        this._batteries = new St.Label({text: '', style_class: 'handoff-device-batteries', opacity: 180});
        this._remaining = new St.Label({text: '', style_class: 'handoff-listening-time', visible: false, opacity: 180});
        details.add_child(this._deviceName);
        details.add_child(this._batteries);
        details.add_child(this._remaining);
        header.add_child(details);
        this._button.menu.addMenuItem(header);
        this._button.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem('Noise Control'));
        this._modes = new Map();
        for (const [mode, title] of [['off', 'Off'], ['anc', 'Noise Cancellation'],
            ['transparency', 'Transparency'], ['adaptive', 'Adaptive']]) {
            const item = new PopupMenu.PopupMenuItem(title);
            const icon = new St.Icon({gicon: mode === 'adaptive' ? this._icon('earport-nc-adaptive-symbolic.svg') : Gio.icon_new_for_string(`${this.path}/icons/handoff-noise-${mode}-symbolic.svg`),
                icon_size: 20, style_class: 'popup-menu-icon'});
            item.insert_child_at_index(icon, 1);
            item.add_style_class_name('handoff-noise-mode');
            item.connect('activate', () => this._callBackend('SetNoiseControlMode', new GLib.Variant('(s)', [mode])));
            this._modes.set(mode, item);
            this._button.menu.addMenuItem(item);
        }
        this._button.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._connectItem = new PopupMenu.PopupMenuItem('Connect');
        this._connectItem.connect('activate', () => this._callBackend('Connect'));
        this._button.menu.addMenuItem(this._connectItem);
        const open = new PopupMenu.PopupMenuItem('Open Handoff Vibe…');
        open.connect('activate', () => this._openApp());
        this._button.menu.addMenuItem(open);
        Main.panel.addToStatusArea(this.uuid, this._button);

        this._proximity = new ProximityCard(this.getSettings(), {
            left: this._icon('earport-bud-left-symbolic.svg'),
            right: this._icon('earport-bud-right-symbolic.svg'),
            case: this._icon('earport-case-symbolic.svg'),
        }, this._icon('earport-charging-symbolic.svg'), () => this._callBackend('Connect'));
        this._createProxy();
        const folder = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_runtime_dir(), 'handoff']));
        try {
            this._monitor = folder.monitor_directory(Gio.FileMonitorFlags.NONE, this._cancellable);
            this._monitor.connect('changed', () => this._refresh());
        } catch (_) { /* The service creates its runtime directory on first start. */ }
        this._refresh();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _icon(name) {
        return Gio.icon_new_for_string(`${this.path}/earport/icons/${name}`);
    }

    _openApp() {
        const app = Gio.DesktopAppInfo.new('io.github.asensato.Handoff.desktop');
        if (app)
            app.launch([], global.create_app_launch_context(0, -1));
    }

    _createProxy() {
        const cancellable = this._cancellable;
        Gio.DBusProxy.new_for_bus(Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_AUTO_START,
            null, BUS, PATH, IFACE, cancellable, (_source, result) => {
                if (cancellable.is_cancelled())
                    return;
                try {
                    this._proxy = Gio.DBusProxy.new_for_bus_finish(result);
                    this._proxySignals = [
                        this._proxy.connect('g-properties-changed', () => this._paint()),
                        this._proxy.connect('notify::g-name-owner', () => this._refresh()),
                    ];
                    this._paint();
                } catch (_) { /* Runtime-file fallback remains available. */ }
            });
    }

    _liveProtocol() {
        if (!this._proxy?.get_name_owner())
            return null;
        const properties = {};
        for (const name of PROPERTIES)
            properties[name] = unpack(this._proxy.get_cached_property(name));
        const now = Date.now() / 1000;
        const protocol = protocolFromProperties(this._config, properties, now);
        if (!protocol)
            return null;
        if (['linux', 'other'].includes(protocol.owner)) {
            if (this._lastOwner && this._lastOwner !== protocol.owner)
                this._switchUntil = now + 3;
            this._lastOwner = protocol.owner;
        }
        protocol.switching_until = this._switchUntil;
        return protocol;
    }

    _callBackend(method, parameters = null) {
        const owner = this._proxy?.get_name_owner();
        const selected = this._config?.selected;
        if (!owner || !selected) {
            Main.notify('Handoff Vibe', 'Start Handoff before using headset controls.');
            return;
        }
        const connection = this._proxy.get_connection();
        const cancellable = this._cancellable;
        connection.call(owner, PATH, 'org.freedesktop.DBus.Properties', 'GetAll',
            new GLib.Variant('(s)', [IFACE]), null, Gio.DBusCallFlags.NO_AUTO_START, 4000,
            cancellable, (bus, result) => {
                if (cancellable.is_cancelled() || !this._button)
                    return;
                try {
                    const properties = unpack(bus.call_finish(result))[0];
                    if (this._config?.selected !== selected || this._proxy?.get_name_owner() !== owner ||
                        !commandMatches(this._config, properties))
                        throw new Error('The headset service changed. Refresh before sending a command.');
                    // Target the verified unique owner, never a replacement well-known name.
                    bus.call(owner, PATH, IFACE, method, parameters, null,
                        Gio.DBusCallFlags.NO_AUTO_START, 4000, cancellable, (source, reply) => {
                            if (cancellable.is_cancelled() || !this._button)
                                return;
                            try {
                                source.call_finish(reply);
                            } catch (error) {
                                Main.notify('Handoff Vibe', error.message);
                            }
                            this._paint();
                        });
                } catch (error) {
                    Main.notify('Handoff Vibe', error.message);
                }
            });
    }

    _readJson(path, callback) {
        const cancellable = this._cancellable;
        Gio.File.new_for_path(path).load_contents_async(cancellable, (source, result) => {
            if (cancellable.is_cancelled())
                return;
            let value = null;
            try {
                const [ok, bytes] = source.load_contents_finish(result);
                if (ok)
                    value = JSON.parse(new TextDecoder().decode(bytes));
            } catch (_) { /* Missing before first setup or service start. */ }
            callback(value);
        });
    }

    _serviceState(unit, callback) {
        const cancellable = this._cancellable;
        Gio.DBus.session.call('org.freedesktop.systemd1', '/org/freedesktop/systemd1',
            'org.freedesktop.systemd1.Manager', 'GetUnit', new GLib.Variant('(s)', [unit]),
            null, Gio.DBusCallFlags.NONE, 2000, cancellable, (bus, result) => {
                if (cancellable.is_cancelled())
                    return;
                let path;
                try {
                    [path] = unpack(bus.call_finish(result));
                } catch (error) {
                    callback(Gio.DBusError.get_remote_error(error) === 'org.freedesktop.systemd1.NoSuchUnit'
                        ? 'inactive' : 'unavailable');
                    return;
                }
                bus.call('org.freedesktop.systemd1', path, 'org.freedesktop.DBus.Properties',
                    'Get', new GLib.Variant('(ss)', ['org.freedesktop.systemd1.Unit', 'ActiveState']),
                    null, Gio.DBusCallFlags.NONE, 2000, cancellable, (connection, response) => {
                        if (cancellable.is_cancelled())
                            return;
                        try {
                            const [value] = unpack(connection.call_finish(response));
                            callback(value);
                        } catch (_) {
                            callback('unavailable');
                        }
                    });
            });
    }

    _refresh() {
        if (!this._button)
            return;
        if (this._busy) {
            this._refreshAgain = true;
            return;
        }
        this._busy = true;
        this._readJson(GLib.build_filenamev([GLib.get_user_config_dir(), 'handoff', 'gui.json']), config => {
            if (this._config?.selected !== config?.selected) {
                this._lastOwner = '';
                this._switchUntil = 0;
            }
            this._config = config;
            const mac = config?.selected;
            if (config?.cli_mode || !mac || !/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/i.test(mac)) {
                this._service = 'inactive';
                this._protocol = null;
                this._finishRefresh();
                return;
            }
            const compact = mac.replaceAll(':', '').toUpperCase();
            this._paint();
            this._serviceState(`handoff@${compact}.service`, service => {
                this._service = service;
                this._readJson(GLib.build_filenamev([GLib.get_user_runtime_dir(), 'handoff', `${compact}.json`]), protocol => {
                    this._protocol = protocol;
                    this._finishRefresh();
                });
            });
        });
    }

    _finishRefresh() {
        this._busy = false;
        this._paint();
        if (this._refreshAgain) {
            this._refreshAgain = false;
            this._refresh();
        }
    }

    _paint() {
        if (!this._button)
            return;
        const live = this._liveProtocol();
        const protocol = live || this._protocol;
        const service = live ? 'active' : this._service;
        const now = Date.now() / 1000;
        const [text, color] = statusFor(this._config, service, protocol, now);
        this._label.text = text;
        this._dot.set_style(`color: ${color}; margin-left: 4px; margin-right: 5px;`);
        this._button.accessible_name = `Handoff Vibe: ${text}`;
        const device = this._config?.devices?.find(item => item.mac === this._config.selected);
        this._deviceName.text = device?.name || 'Handoff Vibe';
        const fresh = protocol && now - protocol.updated >= 0 && now - protocol.updated < 20;
        const levels = [];
        for (const [key, title] of [['left', 'Left'], ['right', 'Right'], ['case', 'Case']]) {
            const value = fresh ? protocol[`battery_${key}`] : -1;
            if (Number.isInteger(value) && value >= 0 && value <= 100)
                levels.push(`${title} ${value}%${protocol[`charging_${key}`] ? ' ⚡' : ''}`);
        }
        this._batteries.text = levels.length ? levels.join(' · ') : text;
        const minutes = fresh ? protocol.listening_minutes : -1;
        this._remaining.visible = Number.isInteger(minutes) && minutes >= 0;
        if (this._remaining.visible)
            this._remaining.text = `About ${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')} of listening left`;
        for (const [mode, item] of this._modes) {
            item.visible = mode !== 'adaptive' || Boolean(fresh && protocol.supports_adaptive);
            item.setSensitive(Boolean(fresh && protocol.controls_ready));
            item.setOrnament(fresh && protocol.noise_control === mode
                ? PopupMenu.Ornament.CHECK : PopupMenu.Ornament.NONE);
        }
        this._connectItem.visible = Boolean(this._config?.selected && !(fresh && protocol.ready));
        this._connectItem.setSensitive(Boolean(this._proxy?.get_name_owner()));
        this._proximity?.update(fresh ? protocol.nearby || {} : {}, Boolean(fresh && protocol.ready));
    }

    disable() {
        if (this._timer)
            GLib.Source.remove(this._timer);
        this._timer = null;
        this._cancellable?.cancel();
        this._monitor?.cancel();
        this._monitor = null;
        if (this._proxy)
            for (const id of this._proxySignals || [])
                this._proxy.disconnect(id);
        this._proxy = null;
        this._proxySignals = [];
        this._proximity?.destroy();
        this._proximity = null;
        this._button?.destroy();
        this._button = null;
        this._busy = false;
        this._refreshAgain = false;
    }
}
