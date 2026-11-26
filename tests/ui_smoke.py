"""Exercise the actual native widgets in preview mode on a virtual display."""
from argparse import Namespace
from pathlib import Path
import os
import subprocess
import sys
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from handoff_ui.app import Handoff, Setup
from gi.repository import GLib

args = Namespace(demo=True, screen='device', model='powerbeatsfit', theme='light', state='active', quit_after=0)
app = Handoff(args)
failures = []
shots = Path(os.environ.get('HANDOFF_SCREENSHOTS', '/tmp/handoff-screenshots'))
shots.mkdir(parents=True, exist_ok=True)


def capture(window, name):
    if os.environ.get('HANDOFF_SKIP_SCREENSHOTS') == '1':
        return
    # X11 capture is only used in this developer smoke test, never by the app.
    subprocess.run(['import', '-window', str(window.get_surface().get_xid()), str(shots / name)], check=True, timeout=10)


def test_device():
    assert app.name.get_label() == 'Powerbeats Fit'
    assert app.window.get_title() == 'Handoff Vibe'
    assert ' · WEB' in app.verse.get_label()
    assert 'Active' in app.pill.get_label()
    assert app.pages.get_pages().get_n_items() == 1
    assert app.lookup_action('whats-new') is not None
    assert app.controls_box.get_margin_top() == 0
    assert not app.listening_label.get_visible()
    assert not app.controls_note.get_visible()
    assert list(app.noise_buttons) == ['anc', 'off', 'transparency']
    assert app.noise_buttons['transparency'].has_css_class('suggested-action')
    assert not app.noise_buttons['anc'].has_css_class('suggested-action')
    capture(app.window, 'device-light.png')
    app.apply_theme('dark')
    GLib.timeout_add(350, guarded(test_dark))


def test_dark():
    capture(app.window, 'device-dark.png')
    for state, text in [('switching', 'Switching audio'), ('disconnected', 'Disconnected'), ('error', 'Error'), ('paused', 'Paused')]:
        app.set_status(state)
        assert text in app.pill.get_label()
    app.set_status('active')
    app.logs()
    assert 'sample logs' in app.logbuffer.get_text(app.logbuffer.get_start_iter(), app.logbuffer.get_end_iter(), False)
    GLib.timeout_add(350, guarded(test_logs))


def test_logs():
    capture(app.logs_window, 'advanced-logs.png')
    app.logs_window.close()
    app.apply_theme('light')
    app.preferences()
    from handoff_ui import releases as R
    app.show_releases(R.parse_releases([
        dict(tag_name='v0.2.0', body='Stable release notes'),
        dict(tag_name='v0.3.0-beta.1', prerelease=True, body='Beta release notes'),
        dict(tag_name='v0.4.0-experimental', prerelease=True, body='Experimental notes'),
    ], include_prereleases=True))
    assert app.release_entries.get_first_child().has_css_class('release-card')
    app.show_whats_new()
    assert app.releases_window.get_visible()
    app.releases_window.close()
    assert not app.releases_window.get_visible()
    app.about()
    GLib.timeout_add(350, guarded(test_about))


def test_about():
    from handoff_ui.about import MESSAGE, AUTHOR_URL
    assert AUTHOR_URL == 'https://github.com/Asensado/'
    assert app.about_window.license_text.get_label() == 'GPLv3 or later · Free software'
    assert app.about_window.details_row.get_next_sibling() == app.about_window.message_row
    assert app.about_window.stack.get_visible_child_name() == 'main'
    assert app.about_window.message_text.get_label() == MESSAGE
    capture(app.about_window, 'about.png')
    app.about_window.navigate('message')
    GLib.timeout_add(350, guarded(test_message))


def test_message():
    capture(app.about_window, 'about-message.png')
    assert app.about_window.stack.get_visible_child_name() == 'message'
    # Check these windows constructed without API errors, then dismiss them.
    for win in list(app.get_windows()):
        if win != app.window:
            win.close()
    app.open_setup()
    GLib.timeout_add(350, guarded(test_setup_intro))


def test_setup_intro():
    capture(app.setup, 'setup-welcome.png')
    app.setup.advance()
    assert app.setup.stage_index == 1
    assert len(app.setup.devices) == 3
    assert not app.setup.device_rows[2].get_sensitive()
    chosen = app.setup.devices[0]
    app.setup.choose(chosen, next(r for r in app.setup.device_rows if r.get_title() == chosen['name']))
    assert app.setup.next.get_sensitive()
    GLib.timeout_add(350, guarded(test_device_list))


def test_device_list():
    capture(app.setup, 'setup-headsets.png')
    app.setup.advance()
    assert app.setup.stage_index == 2
    assert not app.setup.next.get_sensitive() # Name alone needs confirmation.
    app.setup.confirm.set_active(True)
    assert app.setup.next.get_sensitive()
    GLib.timeout_add(350, guarded(test_confirmation))


def test_confirmation():
    capture(app.setup, 'setup-confirm.png')
    app.setup.finish()
    GLib.timeout_add(500, guarded(test_finished))


def test_finished():
    assert app.setup is None
    assert app.device['model'] == 'powerbeatsfit'
    app.config['devices'].append(dict(mac='AA:BB:CC:DD:EE:01', model='airpodspro2', name='AirPods Pro 2'))
    app.experimental_changed(True)
    assert app.multi.get_visible()
    app.multi.set_selected(1)
    GLib.timeout_add(500, guarded(test_profiles))


def test_profiles():
    assert app.device['model'] == 'airpodspro2'
    app.config['cli_mode'] = True
    app.render_cli()
    assert 'CLI mode' in app.pill.get_label()
    assert not app.background.get_visible()
    app.primary_clicked()
    assert not app.config['cli_mode']
    app.config['devices'] = []
    app.config['selected'] = None
    app.render()
    assert app.name.get_label() == 'Meet Handoff Vibe'
    assert not app.manage.get_visible()
    GLib.timeout_add(350, guarded(test_empty))


def test_empty():
    capture(app.window, 'welcome.png')
    print('UI smoke tests passed: light/dark, statuses, logs, preferences, credits, all setup steps, unsupported-device rejection, profiles, empty state.')
    app.quit()


def guarded(fn):
    def wrapped():
        try:
            fn()
        except Exception:
            failures.append(traceback.format_exc())
            app.quit()
        return GLib.SOURCE_REMOVE
    return wrapped

GLib.timeout_add(800, guarded(test_device))
GLib.timeout_add_seconds(20, lambda: (failures.append('UI smoke test timed out'), app.quit(), False)[-1])
result = app.run([sys.argv[0]])
if failures:
    print('\n'.join(failures), file=sys.stderr)
    raise SystemExit(1)
raise SystemExit(result)
