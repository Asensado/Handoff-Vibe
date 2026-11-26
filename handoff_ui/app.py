#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Asensado
"""A small, native, terminal-free front end for xatuke/handoff."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import sys
import time
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango
from . import backend as B
from .models import MODELS, BY_KEY, identify
from .verses import daily_verse
from .about import About
from . import releases as R
from . import __version__

ASSETS = B.ROOT / 'assets'
CSS = b'''
window { }
.hero-title { font-size: 26px; font-weight: 800; letter-spacing: -0.7px; }
.hero-subtitle { font-size: 14px; }
.status-pill { border-radius: 99px; padding: 8px 15px; font-size: 13px; font-weight: 650; }
.status-pill.active { background: alpha(@success_color, 0.12); color: @success_color; }
.status-pill.waiting { background: alpha(@warning_color, 0.12); color: @warning_color; }
.status-pill.error { background: alpha(@error_color, 0.12); color: @error_color; }
.status-pill.idle { background: alpha(@window_fg_color, 0.07); color: alpha(@window_fg_color, 0.68); }
.status-pill.switching { background: alpha(@accent_color, 0.13); color: @accent_color; }
.primary { padding: 12px 26px; border-radius: 99px; font-weight: 700; }
.caption { font-size: 12px; }
.section-label { font-size: 10px; letter-spacing: 1.8px; font-weight: 800; }
.product-stage { border-radius: 40px; background: alpha(@accent_color, 0.045); }
.connected-foot { color: @success_color; }
.setup-step { font-size: 11px; font-weight: 700; letter-spacing: 1.3px; color: @accent_color; }
.logview { font-size: 11px; padding: 14px; }
.device-choice { margin: 5px 0; }
.noise-track { background: alpha(@window_fg_color, 0.07); border-radius: 999px; padding: 4px; }
button.noise-mode { min-width: 44px; min-height: 44px; padding: 0; border-radius: 999px; background: transparent; box-shadow: none; border: none; }
button.noise-mode:hover { background: alpha(@window_fg_color, 0.08); }
button.noise-mode.suggested-action { background: @accent_bg_color; color: @accent_fg_color; }
.noise-caption { font-size: 11px; }
.noise-caption.selected { font-weight: 700; color: @window_fg_color; }
.release-card { padding: 16px; }
.release-badge { border-radius: 999px; padding: 3px 9px; font-size: 11px; font-weight: 700; }
.release-badge.stable { color: @success_color; background: alpha(@success_color, 0.14); }
.release-badge.beta { color: @warning_color; background: alpha(@warning_color, 0.14); }
.release-badge.experimental { color: white; background: #813d9c; }
'''


def label(text='', css=None, wrap=True):
    widget = Gtk.Label(label=text, wrap=wrap, justify=Gtk.Justification.CENTER)
    widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if css:
        for c in css.split():
            widget.add_css_class(c)
    return widget


def button(text, callback, css=None):
    widget = Gtk.Button(label=text)
    widget.connect('clicked', callback)
    if css:
        for c in css.split():
            widget.add_css_class(c)
    return widget


def margins(widget, n=22):
    for edge in ('top', 'bottom', 'start', 'end'):
        getattr(widget, 'set_margin_' + edge)(n)
    return widget


def row(title, subtitle='', suffix=None):
    r = Adw.ActionRow(title=title, subtitle=subtitle)
    r.set_subtitle_lines(3)
    if suffix:
        suffix.set_valign(Gtk.Align.CENTER)
        r.add_suffix(suffix)
    return r


def switch_row(title, subtitle, active, callback):
    switch = Gtk.Switch(active=active, valign=Gtk.Align.CENTER)
    switch.connect('notify::active', lambda s, _: callback(s.get_active()))
    r = row(title, subtitle, switch)
    r.set_activatable_widget(switch)
    return r, switch


class Handoff(Adw.Application):
    def __init__(self, args):
        super().__init__(application_id='io.github.asensato.Handoff', flags=Gio.ApplicationFlags.NON_UNIQUE if args.demo else Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.args = args
        self.demo = args.demo
        self.config = {'devices': [], 'selected': None} if self.demo else B.load_config()
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.pending = False
        self.poll_pending = False
        self.current_service = {}
        self.current_connected = False
        self.blue = None
        self.setup = None
        self.logs_window = None
        self.started = set()
        self.migrating = False
        if self.demo and args.screen != 'welcome':
            d = {'mac': 'AA:BB:CC:DD:EE:FF', 'model': args.model, 'name': BY_KEY[args.model].name}
            self.config.update(devices=[d], selected=d['mac'])
        self.connect('activate', self.activate_app)

    @property
    def device(self):
        return next((d for d in self.config['devices'] if d['mac'] == self.config.get('selected')), None)

    def store(self):
        if not self.demo:
            B.save_config(self.config)

    def job(self, work, done=None, error=None):
        def finished(future):
            def deliver():
                try:
                    result = future.result()
                    if done:
                        done(result)
                except Exception as exc:
                    (error or self.error)(str(exc))
                return GLib.SOURCE_REMOVE
            GLib.idle_add(deliver)
        self.pool.submit(work).add_done_callback(finished)

    def activate_app(self, *_):
        if hasattr(self, 'window'):
            self.window.present()
            return
        self.set_accels_for_action('app.logs', ['<Primary>l'])
        self.set_accels_for_action('app.quit', ['<Primary>q'])
        for name, fn in [('preferences', self.preferences), ('logs', self.logs), ('about', self.about), ('whats-new', self.show_whats_new), ('quit', lambda *_: self.window.close())]:
            act = Gio.SimpleAction.new(name, None)
            act.connect('activate', fn)
            self.add_action(act)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.apply_theme(self.args.theme or self.config.get('theme', 'system'))
        self.window = Adw.ApplicationWindow(application=self, title='Handoff Vibe', default_width=390, default_height=760)
        self.window.set_size_request(350, 580)
        self.window.connect('close-request', self.close_main)
        self.overlay = Adw.ToastOverlay()
        self.window.set_content(self.overlay)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.overlay.set_child(root)
        self.pages = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        head = Adw.HeaderBar()
        head.set_decoration_layout(':close')
        head.set_title_widget(Adw.WindowTitle(title='Handoff Vibe'))
        menu = Gio.Menu()
        menu.append('Preferences', 'app.preferences')
        menu.append("What's new?", 'app.whats-new')
        menu.append('Advanced logs', 'app.logs')
        menu.append('About Handoff Vibe', 'app.about')
        menu.append('Quit', 'app.quit')
        head.pack_end(Gtk.MenuButton(icon_name='open-menu-symbolic', menu_model=menu))
        root.append(head)
        self.banner = Adw.Banner(title='', revealed=False)
        self.banner.set_button_label('Details')
        self.banner.connect('button-clicked', lambda *_: self.error(self.last_error))
        root.append(self.banner)
        self.update_banner = Adw.Banner(title='', revealed=False)
        self.update_banner.set_button_label("What's new?")
        self.update_banner.connect('button-clicked', self.show_whats_new)
        root.append(self.update_banner)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        root.append(self.pages)
        self.pages.add_titled(scroll, 'headset', 'Headset')
        release_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        release_box = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16), 20)
        release_scroll.set_child(release_box)
        self.releases_status = label('Release notes from Asensado/Handoff-Vibe', 'dim-label')
        release_box.append(self.releases_status)
        release_box.append(button('Check for updates', lambda *_: self.check_updates()))
        self.install_update_button = button('Install update', lambda *_: self.install_update())
        self.install_update_button.set_visible(False)
        release_box.append(self.install_update_button)
        release_box.append(Gtk.LinkButton(uri=R.REPOSITORY + '/releases', label='Open GitHub releases'))
        self.release_entries = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        release_box.append(self.release_entries)
        self.releases_window = Adw.Window(transient_for=self.window, title="What's new?", default_width=480, default_height=620)
        release_root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        release_root.append(Adw.HeaderBar())
        release_root.append(release_scroll)
        release_scroll.set_vexpand(True)
        self.releases_window.set_content(release_root)
        self.releases_window.set_hide_on_close(True)
        body = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), 20)
        scroll.set_child(body)
        if self.demo:
            body.append(label('DESIGN PREVIEW · NO BLUETOOTH CHANGES', 'caption dim-label'))
        top_spacer = Gtk.Box(vexpand=True)
        top_spacer.set_size_request(-1, 8)
        body.append(top_spacer)
        self.stage = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER)
        self.stage.add_css_class('product-stage')
        self.picture = Gtk.Picture(width_request=176, height_request=176, can_shrink=True)
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.picture.set_alternative_text('Original headset illustration')
        self.stage.append(self.picture)
        body.append(self.stage)
        self.name = label('', 'hero-title')
        body.append(self.name)
        self.pill = label('', 'status-pill idle')
        self.pill.set_halign(Gtk.Align.CENTER)
        body.append(self.pill)
        self.subtitle = label('', 'hero-subtitle dim-label')
        body.append(self.subtitle)
        self.primary = button('Set up a headset', self.primary_clicked, 'suggested-action primary')
        self.primary.set_halign(Gtk.Align.CENTER)
        self.primary.set_margin_top(14)
        body.append(self.primary)
        self.manage = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, halign=Gtk.Align.CENTER)
        self.manage.append(button('Reconfigure', lambda *_: self.open_setup(reconfigure=True), 'flat'))
        self.manage.append(button('Remove', self.remove_device, 'flat'))
        body.append(self.manage)
        self.multi = Gtk.DropDown.new_from_strings([''])
        self.multi.connect('notify::selected', self.select_profile)
        body.append(self.multi)
        self.controls_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.controls_box.set_margin_top(0)
        self.controls_box.append(label('NOISE CONTROL', 'section-label dim-label'))
        choices = Gtk.Box(homogeneous=True, spacing=0)
        choices.add_css_class('noise-track')
        captions = Gtk.Box(homogeneous=True, spacing=0)
        self.noise_buttons = {}
        self.noise_captions = {}
        icon_folder = (Path('/usr/share/gnome-shell/extensions') / B.EXTENSION_UUID if B.INSTALLED else B.ROOT / 'gnome-extension') / 'icons'
        for mode, title in [('anc', 'Noise cancellation'), ('off', 'Off'), ('transparency', 'Transparency')]:
            holder = Gtk.Box(halign=Gtk.Align.FILL, hexpand=True)
            choice = Gtk.Button(halign=Gtk.Align.CENTER, hexpand=True, tooltip_text=title)
            choice.add_css_class('noise-mode')
            image = Gtk.Image.new_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(str(icon_folder / f'handoff-noise-{mode}-symbolic.svg'))))
            image.set_pixel_size(24)
            choice.set_child(image)
            choice.update_property([Gtk.AccessibleProperty.LABEL], [title])
            choice.connect('clicked', lambda _, selected=mode: self.change_noise_control(selected))
            self.noise_buttons[mode] = choice
            holder.append(choice)
            choices.append(holder)
            caption = label(title, 'noise-caption dim-label')
            self.noise_captions[mode] = caption
            captions.append(caption)
        self.controls_box.append(choices)
        self.controls_box.append(captions)
        self.controls_note = label('Waiting for headset controls', 'caption dim-label')
        self.controls_box.append(self.controls_note)
        self.battery_label = label('', 'caption dim-label')
        self.battery_label.set_visible(False)
        body.append(self.battery_label)
        self.listening_label = label('', 'caption dim-label')
        self.listening_label.set_visible(False)
        body.append(self.listening_label)
        self.controls_box.set_visible(False)
        body.append(self.controls_box)
        bottom_spacer = Gtk.Box(vexpand=True)
        bottom_spacer.set_size_request(-1, 6)
        body.append(bottom_spacer)
        self.info = label('', 'caption dim-label')
        body.append(self.info)
        self.background = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER, spacing=10)
        self.background.append(label('Run in background', 'caption'))
        self.background_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.background_switch.connect('notify::active', self.background_changed)
        self.background.append(self.background_switch)
        body.append(self.background)
        self.footer = label('', 'caption dim-label')
        self.footer.set_visible(False)
        self.verse = label('', 'caption dim-label')
        self.verse.set_opacity(0.75)
        self.verse.set_margin_top(10)
        self.verse.set_tooltip_text('Daily verse · World English Bible · Public domain')
        body.append(self.verse)
        self.refresh_verse()
        GLib.timeout_add_seconds(60, self.refresh_verse)
        self.error_message = ''
        self.render()
        self.window.present()
        if not self.demo:
            self.bootstrap()
            if self.config.get('check_updates', True):
                self.check_updates()
            GLib.timeout_add_seconds(3, self.poll)
            if self.args.screen == 'logs': GLib.idle_add(self.logs)
        else:
            self.set_status(self.args.state)
            self.current_service = {'ActiveState': 'active' if self.args.state in ('active', 'switching', 'connected') else 'inactive'}
            self.primary.set_label('Pause Handoff Vibe' if self.current_service['ActiveState'] == 'active' else 'Start Handoff Vibe')
            self.syncing_switch = True
            self.background_switch.set_active(True)
            self.syncing_switch = False
            self.info.set_label('Audio: this laptop · Other connections unknown')
            self.update_controls(dict(updated=time.time(), controls_ready=True, noise_control='transparency',
                battery_left=78, battery_right=77, battery_case=-1, listening_minutes=-1))
            if self.args.screen == 'setup':
                GLib.idle_add(lambda: self.open_setup())
            elif self.args.screen == 'logs':
                GLib.idle_add(lambda: self.logs())
        if self.args.quit_after:
            GLib.timeout_add_seconds(self.args.quit_after, lambda: self.quit() or False)

    def refresh_verse(self):
        verse = daily_verse()
        self.verse.set_label(verse['text'] + '\n' + verse['reference'] + ' · WEB')
        return GLib.SOURCE_CONTINUE

    def apply_theme(self, mode):
        self.get_style_manager().set_color_scheme({'system': Adw.ColorScheme.DEFAULT, 'light': Adw.ColorScheme.FORCE_LIGHT, 'dark': Adw.ColorScheme.FORCE_DARK}[mode])

    def toast(self, text):
        self.overlay.add_toast(Adw.Toast(title=text, timeout=5))

    def error(self, message):
        self.last_error = message
        self.banner.set_title('Something needs attention')
        self.banner.set_revealed(True)
        dialog = Adw.MessageDialog(transient_for=self.window, heading='Couldn’t complete that', body=message)
        dialog.add_response('close', 'Close')
        dialog.present()

    def set_status(self, state, details=None):
        names = {
            'cli': ('●  CLI mode', 'idle', 'Managed by the command-line version.'),
            'handoff': ('●  Handoff', 'switching', 'Audio is playing on another device.'),
            'active': ('●  Active', 'active', 'Ready to follow your audio.'),
            'switching': ('●  Switching audio', 'switching', 'Moving your sound between devices.'),
            'connected': ('●  Connected', 'active', 'Your headset is connected to this laptop.'),
            'waiting': ('●  Waiting for headset', 'waiting', 'Wear your headset and keep it nearby.'),
            'starting': ('●  Starting', 'switching', 'Connecting the audio switching engine.'),
            'paused': ('●  Paused', 'idle', 'Audio switching is paused.'),
            'disconnected': ('●  Disconnected', 'idle', 'Your headset is not connected to this laptop.'),
            'error': ('●  Error', 'error', 'Open Advanced logs for more information.'),
            'setup': ('●  Not set up', 'idle', 'Connect your Apple and Linux listening worlds.'),
        }
        text, style, subtitle = names.get(state, names['waiting'])
        for cls in ('active', 'switching', 'idle', 'error', 'waiting'):
            self.pill.remove_css_class(cls)
        self.pill.add_css_class(style)
        self.pill.set_label(text)
        self.subtitle.set_label(details or subtitle)

    def render(self):
        d = self.device
        self.name.set_label(d['name'] if d else 'Meet Handoff Vibe')
        image = ASSETS / BY_KEY[d['model']].image if d else ASSETS / 'welcome.svg'
        self.picture.set_filename(str(image))
        self.picture.set_alternative_text(BY_KEY[d['model']].name if d else 'Handoff audio switching illustration')
        self.manage.set_visible(bool(d))
        self.background.set_visible(bool(d))
        self.primary.set_label('Start Handoff Vibe' if d else 'Set up a headset')
        self.info.set_label('Bluetooth connection to this laptop' if d else 'AirPods and compatible Beats · No terminal needed')
        self.set_status('starting' if d else 'setup')
        self.multi.set_visible(bool(d and self.config.get('experimental') and len(self.config['devices']) > 1))
        self.updating_profile = True
        self.multi.set_model(Gtk.StringList.new([x['name'] for x in self.config['devices']]))
        if d:
            self.multi.set_selected(self.config['devices'].index(d))
        self.updating_profile = False
        if self.config.get('cli_mode'): self.render_cli()

    def bootstrap(self):
        if self.config.get("cli_mode"):
            self.render_cli()
            return
        legacy = B.legacy_device()
        if legacy and not legacy['model']:
            self.toast('Existing service found. Confirm your headset model to import it.')
            self.open_setup()
        elif legacy:
            self.migrating = True
            self.banner.set_title('Bringing your existing setup into Handoff…')
            self.banner.set_revealed(True)
            self.banner.set_button_label('')
            def migrated(device):
                self.migrating = False
                self.banner.set_revealed(False)
                self.banner.set_button_label('Details')
                self.render()
                self.toast('Existing setup imported. Original service backed up.')
                self.poll()
            def failed(message):
                self.migrating = False
                self.banner.set_button_label('Details')
                self.error(message)
            self.job(lambda: B.migrate_legacy(self.config), migrated, failed)
        else:
            self.poll()

    def poll(self):
        if self.config.get("cli_mode"):
            return GLib.SOURCE_CONTINUE
        if self.demo or not self.device or self.poll_pending or self.migrating:
            return GLib.SOURCE_CONTINUE
        self.poll_pending = True
        d = dict(self.device)
        def work():
            if self.blue is None:
                self.blue = B.BlueZ()
            devices, _ = self.blue.devices()
            match = next((x for x in devices if x['mac'] == d['mac']), None)
            return match, B.service_state(d), B.protocol_state(d)
        def done(result):
            self.poll_pending = False
            if self.config.get('cli_mode') or not self.device or self.device['mac'] != d['mac']:
                return
            device, service, protocol = result
            self.update_controls(protocol)
            self.current_service = service
            self.current_connected = bool(device and device['connected'])
            running = service.get('ActiveState') in ('active', 'activating')
            self.syncing_switch = True
            self.background_switch.set_active(service.get('UnitFileState') == 'enabled')
            self.syncing_switch = False
            self.primary.set_label('Pause Handoff Vibe' if running else 'Start Handoff Vibe')
            fresh = time.time() - protocol.get('updated', 0) < 20
            if service.get('ActiveState') == 'failed':
                self.set_status('error')
            elif not running:
                self.set_status('paused')
            elif not self.current_connected:
                self.set_status('disconnected')
            elif fresh and protocol.get('ready'):
                self.set_status('switching' if protocol.get('switching') else 'handoff' if protocol.get('owner') == 'other' else 'active')
            elif fresh and protocol.get('error'):
                self.set_status('error', protocol['error'])
            else:
                self.set_status('starting', 'Connected over Bluetooth. Waiting for the switching handshake.')
            owner = protocol.get('owner', '') if fresh else ''
            self.info.set_label({'linux': 'Audio playing on this laptop', 'other': 'Audio playing on another device', 'none': 'No device is playing audio'}.get(owner, 'Connected to this laptop' if self.current_connected else 'Not connected to this laptop'))
            self.footer.set_label('Starts at sign-in and keeps running after you close.' if service.get('UnitFileState') == 'enabled' else 'Turn on background mode to keep switching after closing.')
        def fail(message):
            self.poll_pending = False
            self.set_status('error', 'Bluetooth or the background service is unavailable.')
            self.last_error = message
            self.banner.set_title('Bluetooth or session services unavailable')
            self.banner.set_revealed(True)
        self.job(work, done, fail)
        return GLib.SOURCE_CONTINUE

    def primary_clicked(self, *_):
        if self.config.get('cli_mode'):
            if self.demo:
                self.config['cli_mode'] = False
                self.render()
                return
            self.migrating = True
            def moved(_):
                self.migrating = False
                self.render()
                self.poll()
            def failed(message):
                self.migrating = False
                self.error(message)
            self.job(lambda: B.migrate_legacy(self.config), moved, failed)
            return
        if not self.device:
            self.open_setup()
        else:
            self.service('stop' if self.current_service.get('ActiveState') in ('active', 'activating') else 'start')

    def service(self, action):
        if self.demo:
            self.current_service = {'ActiveState': 'inactive' if action == 'stop' else 'active'}
            self.primary.set_label('Start Handoff Vibe' if action == 'stop' else 'Pause Handoff Vibe')
            self.set_status('paused' if action == 'stop' else 'active')
            self.toast('Preview only. No service was changed.')
            return
        d = dict(self.device)
        self.primary.set_sensitive(False)
        def done(_):
            self.primary.set_sensitive(True)
            if action == 'start':
                self.started.add(d['mac'])
            self.poll()
        def fail(message):
            self.primary.set_sensitive(True)
            self.error(message)
        self.job(lambda: B.service_action(d, action), done, fail)

    def background_changed(self, switch, *_):
        if getattr(self, 'syncing_switch', False) or not self.device:
            return
        if self.demo:
            self.toast('Preview only. No startup setting was changed.')
            return
        desired = switch.get_active()
        d = dict(self.device)
        switch.set_sensitive(False)
        def done(_):
            switch.set_sensitive(True)
            self.toast('Handoff will start when you sign in.' if desired else 'Automatic startup is off.')
            self.poll()
        def failed(message):
            switch.set_sensitive(True)
            self.syncing_switch = True
            switch.set_active(not desired)
            self.syncing_switch = False
            self.error(message)
        self.job(lambda: B.service_action(d, 'enable' if desired else 'disable'), done, failed)

    def open_setup(self, *_, reconfigure=False):
        if self.migrating:
            return
        if self.setup:
            self.setup.present()
            return
        self.setup = Setup(self, reconfigure)
        self.setup.present()

    def remove_device(self, *_):
        d = dict(self.device)
        dialog = Adw.MessageDialog(transient_for=self.window, heading='Remove this headset?', body=f"Handoff will stop managing {d['name']} and turn off its background service. Your Bluetooth pairing will stay available.")
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('remove', 'Remove')
        dialog.set_response_appearance('remove', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        def response(_, answer):
            if answer != 'remove':
                return
            def work():
                if not self.demo:
                    B.service_action(d, 'stop')
                    B.service_action(d, 'disable')
            def done(_):
                self.config['devices'] = [x for x in self.config['devices'] if x['mac'] != d['mac']]
                self.config['selected'] = self.config['devices'][0]['mac'] if self.config['devices'] else None
                self.store()
                self.render()
                self.toast('Headset removed from Handoff.')
                self.poll()
            self.job(work, done)
        dialog.connect('response', response)
        dialog.present()

    def update_controls(self, protocol):
        device = self.device
        allowed = device and device.get('model') in ('powerbeatsfit', 'beatsfitpro', 'powerbeatspro2', 'solopro', 'airpodspro', 'airpodspro2', 'airpodsmax', 'airpods4')
        self.controls_box.set_visible(bool(allowed or protocol.get('controls_ready')))
        import time
        fresh = time.time() - protocol.get('updated', 0) < 15
        ready = fresh and protocol.get('controls_ready', False)
        pending = protocol.get('noise_pending', '')
        for mode, choice in self.noise_buttons.items():
            choice.set_sensitive(bool(ready and not pending))
            if ready and protocol.get('noise_control') == mode:
                choice.add_css_class('suggested-action')
                self.noise_captions[mode].add_css_class('selected')
            else:
                choice.remove_css_class('suggested-action')
                self.noise_captions[mode].remove_css_class('selected')
        self.controls_note.set_label(protocol.get('control_error') or
            ('Waiting for headset confirmation…' if pending else
             'Controls stay available while another device plays audio.' if ready else
             'Waiting for the headset to announce noise-control support.'))
        self.controls_note.set_visible(bool(not ready or pending or protocol.get('control_error')))
        levels = []
        for key, name in [('left', 'Left'), ('right', 'Right'), ('case', 'Case')]:
            level = protocol.get('battery_' + key, -1) if fresh else -1
            if 0 <= level <= 100:
                levels.append(f'{name} {level}%' + (' ⚡' if protocol.get('charging_' + key) else ''))
        self.battery_label.set_label(' · '.join(levels))
        self.battery_label.set_visible(bool(levels))
        minutes = protocol.get('listening_minutes', -1)
        self.listening_label.set_label(f'About {minutes // 60}:{minutes % 60:02d} of listening left' if fresh and minutes >= 0 else '')
        self.listening_label.set_visible(bool(fresh and minutes >= 0))

    def change_noise_control(self, mode):
        if not self.device or self.demo:
            return
        device = dict(self.device)
        for choice in self.noise_buttons.values():
            choice.set_sensitive(False)
        self.controls_note.set_label('Sending headset command…')
        self.controls_note.set_visible(True)
        def done(protocol):
            if self.device and self.device['mac'] == device['mac']:
                protocol['updated'] = time.time()
                self.update_controls(protocol)
        self.job(lambda: B.set_noise_control(device, mode), done, self.error)

    def change_engine_setting(self, key, value):
        self.config[key] = value
        self.store()
        if not self.demo:
            self.job(lambda: B.engine_setting(key, value), None,
                     lambda _: self.toast('Setting saved. Start Handoff to apply it.'))

    def change_update_checks(self, enabled):
        self.config['check_updates'] = enabled
        self.store()
        if enabled:
            self.check_updates()

    def change_automatic_updates(self, enabled, switch):
        if getattr(self, '_syncing_updates', False):
            return
        switch.set_sensitive(False)
        def done(_):
            switch.set_sensitive(True)
            self.toast('Automatic updates enabled after APT refresh.' if enabled else 'Automatic updates disabled.')
        def failed(message):
            self._syncing_updates = True
            switch.set_active(not enabled)
            self._syncing_updates = False
            switch.set_sensitive(True)
            self.error(message)
        self.job(lambda: B.run(['pkexec', '/usr/libexec/handoff/update-handoff', 'enable' if enabled else 'disable'], timeout=120), done, failed)

    def show_whats_new(self, *_):
        self.releases_window.present()
        if not self.demo:
            self.check_updates()

    def check_updates(self):
        if self.demo or getattr(self, '_checking_updates', False):
            return
        self._checking_updates = True
        self.releases_status.set_label('Checking GitHub releases…')
        def done(releases):
            self.show_releases(releases)
        def failed(message):
            self._checking_updates = False
            self.releases_status.set_label('Could not check GitHub releases. Check your connection or open the releases page.')
        self.job(lambda: R.fetch_releases(include_prereleases=True), done, failed)

    def show_releases(self, releases):
        self._checking_updates = False
        self.releases_status.set_label(f'Installed build: {__version__}')
        child = self.release_entries.get_first_child()
        while child:
            self.release_entries.remove(child)
            child = self.release_entries.get_first_child()
        for release in releases:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            card.add_css_class('card')
            card.add_css_class('release-card')
            heading = Gtk.Box(spacing=8)
            title = label(release['title'], 'heading')
            title.set_xalign(0)
            title.set_hexpand(True)
            heading.append(title)
            channel = release.get('channel', 'stable')
            badge = label({'stable': 'Stable', 'beta': 'Beta', 'experimental': 'Experimental'}[channel], f'release-badge {channel}')
            badge.set_valign(Gtk.Align.CENTER)
            heading.append(badge)
            card.append(heading)
            date = label(' · '.join(part for part in [release['tag'], release['date']] if part), 'caption dim-label')
            date.set_xalign(0)
            card.append(date)
            description = label(release['body'])
            description.set_xalign(0)
            description.set_justify(Gtk.Justification.LEFT)
            description.set_selectable(True)
            card.append(description)
            self.release_entries.append(card)
        stable = next((release for release in releases if release.get('channel') == 'stable'), None)
        newer = bool(stable and R.version_tuple(stable['version']) > R.version_tuple(__version__))
        self.update_banner.set_title('Handoff ' + stable['version'] + ' is available' if newer else '')
        self.update_banner.set_revealed(newer)
        self.install_update_button.set_visible(newer)
        if not releases:
            self.releases_status.set_label('No release notes have been published yet.')

    def install_update(self):
        self.install_update_button.set_sensitive(False)
        self.releases_status.set_label('Downloading and installing the latest stable build…')
        def done(message):
            self.install_update_button.set_sensitive(True)
            self.releases_status.set_label(message)
        def failed(message):
            self.install_update_button.set_sensitive(True)
            self.releases_status.set_label(message)
        self.job(lambda: B.run(['pkexec', '/usr/libexec/handoff/update-handoff', 'run'], timeout=900), done, failed)

    def preferences(self, *_):
        win = Adw.PreferencesWindow(transient_for=self.window, modal=True, title='Preferences', default_width=400, default_height=580)
        page = Adw.PreferencesPage()
        win.add(page)
        connection = Adw.PreferencesGroup(title='Headset connection')
        page.add(connection)
        for key, title, description in [
            ('auto_connect', 'Automatic connection', 'Connect when worn or when computer playback starts. Do not take audio from another device playing music or in a call.'),
        ]:
            item, _ = switch_row(title, description, self.config.get(key, False),
                                  lambda active, setting=key: self.change_engine_setting(setting, active))
            connection.add(item)
        try:
            proximity_enabled = B.proximity_enabled()
        except Exception:
            proximity_enabled = True
        item, _ = switch_row('Proximity card', 'Show nearby case batteries and a Connect button. Requires the GNOME companion and a previously connected supported headset.',
                             proximity_enabled, lambda enabled: None if self.demo else self.job(lambda: B.set_proximity_enabled(enabled)))
        connection.add(item)
        ear = Adw.ComboRow(title='Pause when taking earbuds out', model=Gtk.StringList.new(['Never', 'Either earbud', 'Both earbuds']))
        ear.set_selected(self.config.get('ear_pause_mode', 1))
        ear.connect('notify::selected', lambda choice, _: self.change_engine_setting('ear_pause_mode', choice.get_selected()))
        connection.add(ear)
        updates = Adw.PreferencesGroup(title='Updates', description='Stable, beta and experimental release notes from GitHub. Automatic installation uses stable builds only.')
        page.add(updates)
        item, _ = switch_row('Check for updates on launch', 'Show a banner when a newer stable build is available.', self.config.get('check_updates', True), self.change_update_checks)
        updates.add(item)
        item, automatic_switch = switch_row('Update after APT refresh', 'Install newer verified GitHub release packages after sudo apt update. Enabling this requires administrator authentication.', Path('/etc/handoff/automatic-updates').exists(), lambda enabled: self.change_automatic_updates(enabled, automatic_switch))
        automatic_switch.set_sensitive(not self.demo)
        updates.add(item)
        appearance = Adw.PreferencesGroup(title='Appearance')
        page.add(appearance)
        theme = Adw.ComboRow(title='Theme', model=Gtk.StringList.new(['Follow system', 'Light', 'Dark']))
        keys = ['system', 'light', 'dark']
        theme.set_selected(keys.index(self.config.get('theme', 'system')))
        def changed(w, _):
            mode = keys[w.get_selected()]
            self.config['theme'] = mode
            self.apply_theme(mode)
            self.store()
        theme.connect('notify::selected', changed)
        appearance.add(theme)
        advanced = Adw.PreferencesGroup(title='Advanced')
        page.add(advanced)
        advanced.add(row('Diagnostic logs', 'Live output from your headset’s background service.', button('Open', lambda *_: self.logs())))
        advanced.add(row('Bluetooth settings', 'Pair, unpair, or turn Bluetooth on.', button('Open', self.bluetooth_settings)))
        exp = Adw.PreferencesGroup(title='Experimental', description='Optional features that may need extra care.')
        page.add(exp)
        er, _ = switch_row('Multiple headset profiles', 'Save more than one headset and switch between them. Only the selected headset is managed at a time.', self.config.get('experimental', False), self.experimental_changed)
        exp.add(er)
        exp.add(row('Add another headset', 'Requires multiple headset profiles.', button('Add', lambda *_: self.add_another(win))))
        if self.config.get('migration_backup') and not self.config.get('cli_mode'):
            group = Adw.PreferencesGroup(title='Previous setup')
            group.add(row('Restore CLI version', 'Switch back to your original command-line service and startup settings.', button('Restore', lambda *_: self.restore_cli(win))))
            page.add(group)
        if not self.config.get('migration_backup') and self.device and not self.config.get('cli_mode'):
            group = Adw.PreferencesGroup(title='Command-line version')
            group.add(row('Transition to CLI version', 'Use the packaged command-line engine without GUI management.', button('Switch', lambda *_: self.restore_cli(win))))
            page.add(group)
        integration = Adw.PreferencesGroup(title='GNOME integration')
        page.add(integration)
        ir, self.extension_switch = switch_row('Top-bar status', 'GNOME Shell 48 companion indicator. After the first install, sign out and back in once.', False, self.toggle_extension)
        integration.add(ir)
        integration.add(row('Refresh extension status', 'Check whether GNOME has discovered the companion extension.', button('Check', self.check_extension)))
        if not self.demo:
            self.check_extension(quiet=True)
        win.present()
        return win

    def open_backup(self):
        try:
            Gio.AppInfo.launch_default_for_uri(Path(self.config['migration_backup']).as_uri(), None)
        except Exception as exc:
            self.error(str(exc))

    def experimental_changed(self, active):
        self.config['experimental'] = active
        self.store()
        self.render()
        self.poll()

    def add_another(self, win):
        if not self.config.get('experimental'):
            self.toast('Enable multiple headset profiles first.')
            return
        win.close()
        self.open_setup()

    def select_profile(self, dropdown, *_):
        if getattr(self, 'updating_profile', False):
            return
        index = dropdown.get_selected()
        if index >= len(self.config['devices']):
            return
        new = self.config['devices'][index]
        old = self.device
        if old and old['mac'] == new['mac']:
            return
        was_background = self.background_switch.get_active()
        was_running = self.current_service.get('ActiveState') in ('active', 'activating')
        def work():
            if self.demo:
                return
            # Single active engine avoids two headsets both trying to take audio.
            if old:
                B.service_action(old, 'stop')
                B.service_action(old, 'disable')
            try:
                B.service_action(new, 'enable' if was_background else 'start')
                if not was_background:
                    B.service_action(new, 'disable')
            except Exception:
                if old:
                    if was_background:
                        B.service_action(old, 'enable')
                    elif was_running:
                        B.service_action(old, 'start')
                raise
        def done(_):
            self.config['selected'] = new['mac']
            self.started.add(new['mac'])
            self.store()
            self.render()
            self.poll()
        self.job(work, done, lambda message: (self.render(), self.error(message)))

    def logs(self, *_):
        if self.logs_window:
            self.logs_window.present()
            return
        win = Adw.Window(transient_for=self.window, title='Advanced logs', default_width=500, default_height=620)
        self.logs_window = win
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        win.set_content(root)
        head = Adw.HeaderBar()
        head.set_title_widget(label('Advanced logs', 'heading'))
        copy = button('Copy', lambda *_: (Gdk.Display.get_default().get_clipboard().set(self.logbuffer.get_text(self.logbuffer.get_start_iter(), self.logbuffer.get_end_iter(), False)), self.toast('Logs copied. They can include Bluetooth addresses.')))
        head.pack_end(copy)
        root.append(head)
        root.append(margins(label('Live background-service output. Logs may include device names and Bluetooth addresses.', 'caption dim-label'), 14))
        refresh = button('Refresh logs', lambda *_: self.refresh_logs())
        root.append(margins(refresh, 8))
        scroller = Gtk.ScrolledWindow(vexpand=True)
        root.append(scroller)
        text = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        text.add_css_class('logview')
        self.logbuffer = text.get_buffer()
        scroller.set_child(text)
        self.logbuffer.set_text('Choose and set up a headset to see its service logs.')
        win.connect('close-request', lambda *_: setattr(self, 'logs_window', None) or False)
        self.refresh_logs()
        GLib.timeout_add_seconds(3, self.refresh_logs)
        win.present()

    def refresh_logs(self):
        if not self.logs_window:
            return GLib.SOURCE_REMOVE
        if self.demo:
            self.logbuffer.set_text('DESIGN PREVIEW\n\n[10:42:03] Connected to headset\n[10:42:03] Switching handshake complete\n[10:42:16] Playback started on laptop\n[10:42:16] Claiming audio ownership\n[10:42:17] Audio source: this laptop\n\nThese are sample logs, not live device output.')
        elif self.device:
            self.job(lambda: B.read_logs(dict(self.device, legacy=True) if self.config.get('cli_mode') else self.device), lambda text: self.logbuffer.set_text(text or 'No service logs yet.'), lambda message: self.logbuffer.set_text(message) if self.logs_window else None)
        return GLib.SOURCE_CONTINUE

    def bluetooth_settings(self, *_):
        if self.demo:
            self.toast('Preview only. Bluetooth settings were not opened.')
            return
        import shutil
        for executable, args in [('gnome-control-center', ['bluetooth']), ('blueman-manager', []), ('systemsettings', ['kcm_bluetooth'])]:
            if shutil.which(executable):
                try:
                    Gio.Subprocess.new([executable] + args, Gio.SubprocessFlags.NONE)
                except Exception as exc:
                    self.error(str(exc))
                return
        self.error('Open your desktop’s Bluetooth settings from the system menu, then return to Handoff.')

    def about(self, *_):
        self.about_window = About(self.window)
        self.about_window.present()
        return self.about_window

    def render_cli(self):
        self.set_status('cli')
        self.primary.set_label('Move back to GUI')
        self.manage.set_visible(False)
        self.background.set_visible(False)
        self.multi.set_visible(False)
        self.info.set_label('Your command-line service manages audio switching.')

    def restore_cli(self, preferences=None):
        dialog = Adw.MessageDialog(transient_for=preferences or self.window, heading='Switch to the CLI version?', body='Handoff Vibe will stop its GUI-managed services and restore your original service and startup settings when a backup exists. Otherwise it will create a CLI service using the packaged engine, which requires keeping this package installed. You can move back to the GUI later.')
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('restore', 'Switch to CLI')
        dialog.set_default_response('cancel')
        def response(_, answer):
            if answer != 'restore': return
            if preferences: preferences.close()
            if self.demo:
                self.config['cli_mode'] = True
                self.render_cli()
                self.toast('Preview only. No services were changed.')
                return
            self.migrating = True
            self.window.set_sensitive(False)
            def done(_):
                self.migrating = False
                self.window.set_sensitive(True)
                self.render_cli()
                self.toast('CLI service restored. Automatic GUI migration is paused.')
            def failed(message):
                self.migrating = False
                self.window.set_sensitive(True)
                self.error(message)
            self.job(lambda: B.restore_cli(self.config), done, failed)
        dialog.connect('response', response)
        dialog.present()
        return dialog

    def check_extension(self, *_, quiet=False):
        if self.demo:
            self.toast('Preview only. The GNOME extension was not changed.')
            return
        def done(enabled):
            self.syncing_extension = True
            self.extension_switch.set_active(enabled)
            self.syncing_extension = False
            if not quiet: self.toast('Top-bar status is on.' if enabled else 'Top-bar status is off.')
        self.job(B.extension_enabled, done, (lambda _: None) if quiet else self.error)

    def toggle_extension(self, enabled):
        if getattr(self, 'syncing_extension', False): return
        if self.demo:
            self.toast('Preview only. The GNOME extension was not changed.')
            return
        self.extension_switch.set_sensitive(False)
        def done(_):
            self.extension_switch.set_sensitive(True)
            self.toast('Top-bar status enabled.' if enabled else 'Top-bar status disabled.')
        def failed(message):
            self.extension_switch.set_sensitive(True)
            self.syncing_extension = True
            self.extension_switch.set_active(not enabled)
            self.syncing_extension = False
            self.error(message)
        self.job(lambda: B.set_extension_enabled(enabled), done, failed)

    def close_main(self, *_):
        if self.setup:
            self.setup.close()
        if self.demo or self.config.get('cli_mode') or not self.config['devices']:
            return False
        # Keep autostart-enabled engines alive. Stop sessions started by this UI.
        def work():
            for d in list(self.config['devices']):
                if B.service_state(d).get('UnitFileState') != 'enabled':
                    B.service_action(d, 'stop')
        self.window.set_sensitive(False)
        self.job(work, lambda *_: self.quit(), lambda message: (self.window.set_sensitive(True), self.error(message)))
        return True


class Setup(Adw.Window):
    def __init__(self, app, reconfigure):
        super().__init__(transient_for=app.window, modal=True, title='Set up Handoff Vibe', default_width=400, default_height=690)
        self.app = app
        self.reconfigure = reconfigure
        self.stage_index = 0
        self.selected = None
        self.selected_model = None
        self.scanning = False
        self.busy = False
        self.closed = False
        self.devices = []
        self.previous = dict(app.device) if reconfigure and app.device else None
        self.connect('close-request', self.on_close)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)
        header = Adw.HeaderBar()
        self.back = button('Back', self.go_back, 'flat')
        header.pack_start(self.back)
        root.append(header)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        root.append(scroll)
        self.body = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16), 24)
        scroll.set_child(self.body)
        self.bottom = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), 20)
        root.append(self.bottom)
        self.next = button('Continue', self.advance, 'suggested-action primary')
        self.bottom.append(self.next)
        self.help = label('', 'caption dim-label')
        self.bottom.append(self.help)
        self.show_stage()

    def clear(self):
        while self.body.get_first_child():
            self.body.remove(self.body.get_first_child())

    def show_stage(self):
        self.clear()
        self.back.set_visible(self.stage_index > 0)
        self.back.set_sensitive(not self.busy)
        self.next.set_sensitive(True)
        self.help.set_label('')
        self.body.append(label(f'STEP {self.stage_index + 1} OF 3', 'setup-step'))
        if self.stage_index == 0:
            picture = Gtk.Picture.new_for_filename(str(ASSETS / 'welcome.svg'))
            picture.set_size_request(160, 160)
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            self.body.append(picture)
            self.body.append(label('A little setup.\nA lot less switching.', 'hero-title'))
            self.body.append(label('Play on your laptop. Pick up your phone. Let your headset follow along.', 'dim-label'))
            group = Adw.PreferencesGroup()
            self.body.append(group)
            ready = self.app.demo or B.bluetooth_ready()
            group.add(row('Prepare Bluetooth', 'Already configured.' if ready else 'A one-time compatibility setting lets your headset recognize this laptop.'))
            group.add(row('Choose your headset', 'AirPods 2 or later, AirPods Pro, AirPods Max, and compatible H1/H2 Beats. Some models remain untested.'))
            group.add(row('Keep listening', 'Try switching between your phone and laptop. No terminal needed.'))
            if not ready:
                self.body.append(label('Preparing Bluetooth needs administrator approval, restarts Bluetooth, and temporarily disconnects Bluetooth devices. Previously paired headsets may need to be removed and paired again.', 'caption dim-label'))
            self.next.set_label('Continue' if ready else 'Prepare Bluetooth')
        elif self.stage_index == 1:
            self.body.append(label('Find your headset', 'hero-title'))
            self.body.append(label('Put your earbuds or headphones in pairing mode and keep them nearby. You can also choose an already paired headset.', 'dim-label'))
            controls = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
            self.scan_button = button('Scan nearby', self.scan)
            controls.append(self.scan_button)
            controls.append(button('Bluetooth settings', self.app.bluetooth_settings, 'flat'))
            self.body.append(controls)
            self.listgroup = Adw.PreferencesGroup(title='Available devices')
            self.body.append(self.listgroup)
            self.device_rows = []
            self.next.set_label('Continue')
            self.next.set_sensitive(False)
            if self.app.demo:
                self.populate_demo()
            else:
                self.refresh_devices()
            self.body.append(label('Not supported: Studio Buds/+, Studio Pro, W1 Beats, and AirPods 1. Unknown models need identification.', 'caption dim-label'))
        else:
            model = BY_KEY[self.selected_model]
            image = Gtk.Picture.new_for_filename(str(ASSETS / model.image))
            image.set_size_request(190, 190)
            image.set_content_fit(Gtk.ContentFit.CONTAIN)
            self.body.append(image)
            self.body.append(label(self.selected['name'], 'hero-title'))
            self.body.append(label(model.name + ' · ' + model.chip, 'dim-label'))
            self.body.append(label('Keep your headset paired with your phone too. Start some media on each device to test switching.', 'dim-label'))
            self.confirm = Gtk.CheckButton(label='I confirm this is the model shown above.')
            self.confirm.set_active(self.selected.get('verdict') == 'detected')
            self.confirm.connect('toggled', lambda w: self.next.set_sensitive(w.get_active()))
            self.body.append(self.confirm)
            self.auto = Gtk.CheckButton(label='Run in background and start when I sign in')
            self.auto.set_active(True)
            self.body.append(self.auto)
            self.body.append(label('Model eligibility does not guarantee Linux switching support. The device page will show whether the switching handshake succeeds.', 'caption dim-label'))
            self.next.set_label('Finish setup')
            self.next.set_sensitive(self.confirm.get_active())

    def populate_demo(self):
        self.update_devices([
            dict(mac='AA:BB:CC:DD:EE:FF', path='/demo/fit', name='Powerbeats Fit', model='powerbeatsfit', verdict='confirm', paired=True, connected=True),
            dict(mac='AA:BB:CC:DD:EE:01', path='/demo/pro', name='AirPods Pro 2', model='airpodspro2', verdict='detected', paired=False, connected=False),
            dict(mac='AA:BB:CC:DD:EE:02', path='/demo/studio', name='Beats Studio Buds', model=None, verdict='unsupported', paired=True, connected=False),
        ])

    def refresh_devices(self):
        def work():
            if self.app.blue is None:
                self.app.blue = B.BlueZ()
            return self.app.blue.devices()[0]
        def failed(message):
            if not self.closed and self.stage_index == 1:
                self.help.set_label(message)
        self.app.job(work, lambda ds: self.update_devices(ds) if not self.closed and self.stage_index == 1 else None, failed)

    def update_devices(self, devices):
        self.devices = devices
        old_mac = self.selected.get('mac') if self.selected else None
        for r in self.device_rows:
            self.listgroup.remove(r)
        self.device_rows.clear()
        self.selected = None
        self.next.set_sensitive(False)
        for d in sorted(devices, key=lambda x: (x['verdict'] == 'unsupported', not bool(x['model']), x['name'].lower())):
            subtitle = ('Paired' if d['paired'] else 'Nearby')
            if d['verdict'] == 'unsupported':
                subtitle += ' · Not compatible with Handoff'
            elif d['model']:
                subtitle += ' · ' + BY_KEY[d['model']].name
            else:
                subtitle += ' · Model could not be identified'
            r = row(d['name'], subtitle)
            r.add_css_class('device-choice')
            if d['model']:
                thumb = Gtk.Picture.new_for_filename(str(ASSETS / BY_KEY[d['model']].image))
                thumb.set_size_request(44, 44)
                thumb.set_content_fit(Gtk.ContentFit.CONTAIN)
                r.add_prefix(thumb)
            else:
                r.add_prefix(Gtk.Image.new_from_icon_name('audio-headphones-symbolic'))
            compatible = bool(d['model']) and d['verdict'] != 'unsupported'
            r.set_activatable(compatible)
            r.set_sensitive(compatible)
            r.connect('activated', lambda _, device=d, widget=r: self.choose(device, widget))
            self.listgroup.add(r)
            self.device_rows.append(r)
            if compatible and d['mac'] == old_mac:
                self.choose(d, r)
        if not devices:
            r = row('No headsets found yet', 'Put your headset in pairing mode, then scan nearby.')
            self.listgroup.add(r)
            self.device_rows.append(r)
        # Renamed devices without model metadata can be identified explicitly.
        unknowns = [d for d in devices if d['verdict'] == 'unknown']
        if unknowns:
            r = row('Is your headset renamed?', 'Identify its model using the name on its packaging.', button('Identify', lambda *_: self.identify_unknown(unknowns)))
            self.listgroup.add(r)
            self.device_rows.append(r)

    def identify_unknown(self, devices):
        win = Adw.Window(transient_for=self, modal=True, title='Identify headset', default_width=360, default_height=390)
        box = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16))
        win.set_content(box)
        box.append(Adw.HeaderBar())
        box.append(label('Choose the exact model', 'title-2'))
        box.append(label('Bluetooth names can be changed. Check the model on your packaging before continuing.', 'dim-label'))
        dd = Gtk.DropDown.new_from_strings([d['name'] for d in devices])
        md = Gtk.DropDown.new_from_strings([m.name for m in MODELS])
        box.append(dd)
        box.append(md)
        check = Gtk.CheckButton(label='I checked the physical model.')
        box.append(check)
        def identify_clicked(*_):
            d = dict(devices[dd.get_selected()])
            d['model'] = MODELS[md.get_selected()].key
            d['verdict'] = 'confirm'
            self.selected = d
            self.selected_model = d['model']
            self.next.set_sensitive(True)
            self.help.set_label(d['name'] + ' · Model manually confirmed')
            win.close()
        confirm = button('Use this model', identify_clicked, 'suggested-action')
        confirm.set_sensitive(False)
        check.connect('toggled', lambda w: confirm.set_sensitive(w.get_active()))
        box.append(confirm)
        win.present()

    def choose(self, device, widget):
        for r in self.device_rows:
            r.remove_css_class('accent')
        widget.add_css_class('accent')
        self.selected = dict(device)
        self.selected_model = device['model']
        self.help.set_label(device['name'] + ' selected')
        self.next.set_sensitive(True)

    def scan(self, *_):
        if self.app.demo:
            self.populate_demo()
            self.help.set_label('Preview: example devices shown.')
            return
        self.scan_button.set_sensitive(False)
        self.help.set_label('Looking for nearby headsets…')
        def work():
            if self.app.blue is None:
                self.app.blue = B.BlueZ()
            self.app.blue.discover(True)
        def done(_):
            self.scanning = True
            self.refresh_devices()
            GLib.timeout_add_seconds(2, self.scan_refresh)
            GLib.timeout_add_seconds(25, self.stop_scan)
        def failed(message):
            self.scan_button.set_sensitive(True)
            self.help.set_label(message)
        self.app.job(work, done, failed)

    def scan_refresh(self):
        if self.closed or self.stage_index != 1 or not self.scanning:
            return GLib.SOURCE_REMOVE
        self.refresh_devices()
        return GLib.SOURCE_CONTINUE

    def stop_scan(self):
        if self.scanning and self.app.blue:
            self.scanning = False
            self.app.job(lambda: self.app.blue.discover(False), error=lambda _: None)
        if not self.closed and hasattr(self, 'scan_button'):
            self.scan_button.set_sensitive(True)
        return GLib.SOURCE_REMOVE

    def advance(self, *_):
        if self.busy:
            return
        if self.stage_index == 0:
            if self.app.demo or B.bluetooth_ready():
                self.stage_index = 1
                self.show_stage()
                return
            self.busy = True
            self.next.set_sensitive(False)
            self.help.set_label('Waiting for administrator approval…')
            def done(_):
                self.busy = False
                self.stage_index = 1
                self.show_stage()
                self.help.set_label('Bluetooth is ready. If your headset was paired before, remove and pair it again in Bluetooth settings.')
            def failed(message):
                self.busy = False
                self.next.set_sensitive(True)
                self.help.set_label('Setup was not completed. ' + message)
            if not Path(B.HELPER).exists():
                failed('Install the Debian package to enable guided Bluetooth preparation.')
            else:
                self.app.job(lambda: B.run(['pkexec', B.HELPER], timeout=120), done, failed)
        elif self.stage_index == 1:
            if not self.selected:
                return
            self.stop_scan()
            self.stage_index = 2
            self.show_stage()
        else:
            self.finish()

    def finish(self):
        self.busy = True
        self.next.set_sensitive(False)
        self.back.set_sensitive(False)
        self.help.set_label('Connecting your headset and setting up Handoff…')
        d = {'mac': self.selected['mac'], 'name': self.selected['name'], 'model': self.selected_model}
        auto = self.auto.get_active()
        def work():
            if self.app.demo:
                return
            self.app.blue.connect(self.selected)
            actual = next((x for x in self.app.blue.devices()[0] if x['mac'] == d['mac']), None)
            if actual and (actual['verdict'] == 'unsupported' or (actual['verdict'] == 'detected' and actual['model'] != d['model'])):
                raise RuntimeError('The detected headset model is incompatible or differs from the model you selected. Setup was stopped.')
            legacy = B.legacy_device()
            if legacy and legacy['mac'] == d['mac']:
                B.migrate_legacy(self.app.config, model_override=d['model'])
            if self.previous and self.previous['mac'] != d['mac']:
                B.service_action(self.previous, 'stop')
                B.service_action(self.previous, 'disable')
            try:
                B.service_action(d, 'enable' if auto else 'start')
                if not auto:
                    B.service_action(d, 'disable')
            except Exception:
                if self.previous and self.previous['mac'] != d['mac']:
                    B.service_action(self.previous, 'enable')
                raise
        def done(_):
            config = self.app.config
            config['devices'] = [x for x in config['devices'] if x['mac'] != d['mac'] and (not self.previous or x['mac'] != self.previous['mac'])]
            config['devices'].append(d)
            config['selected'] = d['mac']
            self.app.store()
            self.app.started.add(d['mac'])
            self.app.render()
            self.app.poll()
            self.busy = False
            self.close()
            self.app.toast('Headset added. Play audio on your phone and laptop to test switching.')
        def failed(message):
            self.busy = False
            self.next.set_sensitive(True)
            self.back.set_sensitive(True)
            self.help.set_label('Couldn’t finish: ' + message + ' You can pair in Bluetooth settings and retry.')
        self.app.job(work, done, failed)

    def go_back(self, *_):
        if self.busy:
            return
        self.stop_scan()
        self.stage_index = max(0, self.stage_index - 1)
        self.show_stage()

    def on_close(self, *_):
        if self.busy:
            return True
        self.closed = True
        self.stop_scan()
        self.app.setup = None
        return False


def main():
    parser = argparse.ArgumentParser(description='Handoff graphical setup and status')
    parser.add_argument('--demo', action='store_true', help='Preview without Bluetooth, service, or configuration changes')
    parser.add_argument('--screen', choices=['welcome', 'device', 'setup', 'logs'], default='device')
    parser.add_argument('--state', choices=['active', 'connected', 'switching', 'disconnected', 'error', 'paused', 'waiting'], default='active')
    parser.add_argument('--model', choices=list(BY_KEY), default='powerbeatsfit')
    parser.add_argument('--theme', choices=['system', 'light', 'dark'])
    parser.add_argument('--quit-after', type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = Handoff(args)
    return app.run([sys.argv[0]])

if __name__ == '__main__':
    raise SystemExit(main())
