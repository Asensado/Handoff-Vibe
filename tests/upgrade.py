"""Check version/identity and overlay old/new package payloads in a temp tree.

This is a package-layout simulation, not a privileged dpkg installation.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

if len(sys.argv) != 3:
    raise SystemExit('usage: python3 tests/upgrade.py OLD.deb NEW.deb')
old, new = [Path(arg).resolve() for arg in sys.argv[1:]]
field = lambda package, key: subprocess.check_output(['dpkg-deb', '--field', str(package), key], text=True).strip()
assert field(old, 'Package') == 'handoff'
assert field(new, 'Package') == 'handoff-vibe'
assert field(new, 'Version') == '0.1.0'
assert 'handoff' in field(new, 'Conflicts').split(', ')
assert 'handoff' in field(new, 'Replaces').split(', ')
# Package identities differ, so resetting the new package version is not a downgrade.
root = Path(tempfile.mkdtemp(prefix='handoff-upgrade-layout-', dir='/tmp'))
config = root / 'home/test/.config/handoff/gui.json'
config.parent.mkdir(parents=True)
original = b'{"devices":[],"theme":"dark","migration_backup":"kept"}'
config.write_bytes(original)
for package in (old, new):
    subprocess.run(['dpkg-deb', '--extract', str(package), str(root)], check=True)
    print('Payload extracted:', package.name)
assert config.read_bytes() == original
launcher = root / 'usr/share/applications/io.github.asensato.Handoff.desktop'
assert 'Name=Handoff Vibe' in launcher.read_text()
assert 'Exec=handoff-vibe' in launcher.read_text()
assert (root / 'usr/bin/handoff-vibe').exists()
assert (root / 'usr/bin/handoff').is_symlink()
assert (root / 'usr/share/gnome-shell/extensions/handoff-vibe@asensado.github.io/extension.js').exists()
assert 'io.github.asensato.Handoff' in (root / 'usr/share/handoff/handoff_ui/app.py').read_text()
print('handoff → handoff-vibe 0.1.0 package-transition layout checks passed; config bytes and desktop identity preserved.')
print('Upgrade-layout test root:', root)
