# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Asensado
"""Stable, native About navigation with a personal message on its own page."""
import gi
gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk

AUTHOR_URL = 'https://github.com/Asensado/'
MESSAGE = "Hi there! At the time of writing, I'm still a first-year university student taking Computing Science. This was just a curiosity project and I'm surprised this worked great on a trial of ChatGPT Plus Work. I know vibe-coded stuff is ew, and I do plan on actually not relying on AI to code my ideas. This was just a QoL to a project I use daily, and I hope it's useful to you too. Thanks for taking the time to read this. God bless!"

class About(Adw.Window):
    def __init__(self, parent):
        super().__init__(transient_for=parent, modal=True, title='About Handoff Vibe', default_width=410, default_height=620)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)
        self.header = Adw.HeaderBar()
        self.back = Gtk.Button(icon_name='go-previous-symbolic', tooltip_text='Back to About')
        self.back.add_css_class('flat')
        self.back.connect('clicked', lambda *_: self.navigate('main'))
        self.header.pack_start(self.back)
        root.append(self.header)
        self.stack = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        root.append(self.stack)
        home = self.page('main')
        icon = Gtk.Image.new_from_icon_name('io.github.asensato.Handoff')
        icon.set_pixel_size(90)
        home.append(icon)
        home.append(self.text('Handoff Vibe', 'title-1'))
        home.append(self.text('0.2.0', 'dim-label'))
        self.license_text = self.text('GPLv3 or later · Free software', 'caption dim-label')
        home.append(self.license_text)
        home.append(self.text('Made with ❤️ by', 'dim-label'))
        home.append(Gtk.LinkButton(uri=AUTHOR_URL, label='Asensado', halign=Gtk.Align.CENTER))
        home.append(self.text('with ChatGPT 6.1-Sol Medium Work', 'caption dim-label'))
        navigation = Adw.PreferencesGroup()
        home.append(navigation)
        self.details_row = Adw.ActionRow(title='Details', subtitle='Credits, project links, and license', activatable=True)
        self.message_row = Adw.ActionRow(title='A Message for You', subtitle='A note from Asensado', activatable=True)
        for key, item in [('details', self.details_row), ('message', self.message_row)]:
            item.add_suffix(Gtk.Image.new_from_icon_name('go-next-symbolic'))
            item.connect('activated', lambda _, page=key: self.navigate(page))
            navigation.add(item)
        details = self.page('details')
        details.append(self.text('Details', 'title-1'))
        for heading, body, uri in [
            ('Bluetooth backend and GNOME components', 'EarPort Contributors (Anoryth/earport), GPL-3.0-or-later; original notices and source retained.', 'https://github.com/Anoryth/earport'),
            ('Original audio switching engine', 'Aayushman Choudhary (xatuke) and Handoff contributors', 'https://github.com/xatuke/handoff'),
            ('Design inspiration', 'Packet by nozwock, Dominik Baran, and contributors', 'https://github.com/nozwock/packet'),
            ('Device identification research', 'LibrePods and CAPod contributors', 'https://github.com/kavishdevar/librepods'),
            ('License', 'GNU GPL version 3 or later. Personal, commercial and educational use is allowed. Preserve license and attribution notices, and provide corresponding source when distributing covered binaries or modifications. Original MIT components retain their MIT terms.', 'https://www.gnu.org/licenses/gpl-3.0.html'),
            ('Daily verses', 'World English Bible (WEB), public domain. A 31-verse offline rotation changes with your local calendar date.', 'https://worldenglish.bible/'),
        ]:
            details.append(self.text(heading, 'heading'))
            details.append(self.text(body, 'dim-label'))
            if uri:
                details.append(Gtk.LinkButton(uri=uri, label='Visit project', halign=Gtk.Align.CENTER))
        message = self.page('message')
        message.append(self.text('A Message for You', 'title-1'))
        self.message_text = self.text(MESSAGE)
        self.message_text.set_justify(Gtk.Justification.LEFT)
        self.message_text.set_xalign(0)
        self.message_text.set_selectable(True)
        message.append(self.message_text)
        self.navigate('main')

    def text(self, text, classes=''):
        widget = Gtk.Label(label=text, wrap=True, justify=Gtk.Justification.CENTER)
        for c in classes.split(): widget.add_css_class(c)
        return widget

    def page(self, name):
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for edge in ('top','bottom','start','end'): getattr(box, 'set_margin_'+edge)(28)
        scroll.set_child(box)
        self.stack.add_named(scroll, name)
        return box

    def navigate(self, page):
        self.stack.set_visible_child_name(page)
        self.back.set_visible(page != 'main')
        self.set_title({'main':'About Handoff Vibe','details':'Details','message':'A Message for You'}[page])
        if page != 'main':
            self.back.grab_focus()
            self.message_text.select_region(0, 0)
