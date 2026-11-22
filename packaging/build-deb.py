#!/usr/bin/python3
"""Build a local-architecture Debian package, with generated shared-library deps."""
from pathlib import Path
import shutil
import subprocess
import os

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'build'
DIST = ROOT / 'dist'
STAGE = BUILD / 'deb-stage'
ENGINE = BUILD / 'engine-source'
if ENGINE.exists():
    shutil.rmtree(ENGINE)
shutil.copytree(ROOT / 'upstream', ENGINE)
subprocess.run(['patch', '-p1', '--batch', '--forward', '-i', str(ROOT / 'patches/0001-gui-integration.patch')], cwd=ENGINE, check=True)
ARCH = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
ENGINE_BUILD = BUILD / 'engine-build'
subprocess.run(['cmake', '-S', str(ENGINE), '-B', str(ENGINE_BUILD), '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_RUNTIME_OUTPUT_DIRECTORY=' + str(BUILD)], check=True)
subprocess.run(['cmake', '--build', str(ENGINE_BUILD), '-j2'], check=True)
if STAGE.exists():
    shutil.rmtree(STAGE)
for directory in ['DEBIAN', 'usr/bin', 'usr/libexec/handoff', 'usr/share/handoff', 'usr/share/applications', 'usr/share/icons/hicolor/scalable/apps', 'usr/share/polkit-1/actions', 'usr/share/doc/handoff-vibe']:
    (STAGE / directory).mkdir(parents=True, exist_ok=True)
shutil.copy2(ROOT / 'handoff-vibe', STAGE / 'usr/bin/handoff-vibe')
(STAGE / 'usr/bin/handoff').symlink_to('handoff-vibe')
shutil.copytree(ROOT / 'handoff_ui', STAGE / 'usr/share/handoff/handoff_ui', ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(ROOT / 'assets', STAGE / 'usr/share/handoff/assets')
shutil.copytree(ROOT / 'gnome-extension', STAGE / 'usr/share/gnome-shell/extensions/handoff-vibe@asensado.github.io')
shutil.copy2(BUILD / 'airpods-handoff', STAGE / 'usr/libexec/handoff/airpods-handoff')
shutil.copy2(ROOT / 'packaging/prepare-bluetooth', STAGE / 'usr/libexec/handoff/prepare-bluetooth')
shutil.copy2(ROOT / 'packaging/io.github.asensato.Handoff.policy', STAGE / 'usr/share/polkit-1/actions')
shutil.copy2(ROOT / 'packaging/io.github.asensato.Handoff.desktop', STAGE / 'usr/share/applications')
shutil.copy2(ROOT / 'assets/welcome.svg', STAGE / 'usr/share/icons/hicolor/scalable/apps/io.github.asensato.Handoff.svg')
for name in ['README.md', 'LICENSE', 'NOTICE', 'LICENSING.md', 'THIRD_PARTY.md']:
    shutil.copy2(ROOT / name, STAGE / 'usr/share/doc/handoff-vibe' / name)
shutil.copytree(ROOT / 'LICENSES', STAGE / 'usr/share/doc/handoff-vibe/LICENSES')
for name in ['usr/bin/handoff-vibe', 'usr/libexec/handoff/airpods-handoff', 'usr/libexec/handoff/prepare-bluetooth']:
    (STAGE / name).chmod(0o755)
# dpkg-shlibdeps needs package metadata in its working directory.
WORK = BUILD / 'shlibdeps'
(WORK / 'debian').mkdir(parents=True, exist_ok=True)
(WORK / 'debian/control').write_text('Source: handoff-vibe\nSection: sound\nPriority: optional\nMaintainer: Asensado <asensado@users.noreply.github.com>\n\nPackage: handoff-vibe\nArchitecture: any\nDescription: Handoff GUI\n')
result = subprocess.check_output(['dpkg-shlibdeps', '-O', '-e' + str(BUILD / 'airpods-handoff')], cwd=WORK, text=True)
shared = next(line.split('=', 1)[1] for line in result.splitlines() if line.startswith('shlibs:Depends='))
deps = 'python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0 (>= 4.8), gir1.2-adw-1 (>= 1.2), bluez, systemd, pulseaudio-utils, pkexec, ' + shared
(STAGE / 'DEBIAN/control').write_text(f'''Package: handoff-vibe
Version: 0.1.0
Conflicts: handoff
Replaces: handoff
Architecture: {ARCH}
Maintainer: Asensado <asensado@users.noreply.github.com>
Section: sound
Priority: optional
Depends: {deps}
Recommends: gnome-control-center | blueman, pipewire-pulse | pulseaudio
Installed-Size: {sum(p.stat().st_size for p in STAGE.rglob('*') if p.is_file()) // 1024}
Description: Handoff Vibe graphical setup and status for AirPods and Beats
 Guided Bluetooth setup, automatic migration of the upstream user service,
 audio switching status, background service controls, and diagnostic logs.
 Based on xatuke/handoff. Compatible hardware is required.
''')
DIST.mkdir(exist_ok=True)
package = DIST / f'handoff-vibe_0.1.0_{ARCH}.deb'
subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(STAGE), str(package)], check=True)
print(package)
