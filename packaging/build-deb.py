#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Asensado
"""Build a local-architecture Debian package, with generated shared-library deps."""
from pathlib import Path
import shutil
import subprocess
import os

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'build'
DIST = ROOT / 'dist'
STAGE = BUILD / 'deb-stage'
ARCH = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
subprocess.run(['cmake', '-S', str(ROOT / 'upstream'), '-B', str(BUILD), '-DCMAKE_BUILD_TYPE=Release'], check=True)
subprocess.run(['cmake', '--build', str(BUILD), '-j2'], check=True)
EARPORT_BUILD = ROOT / 'earport/daemon/build'
if not (EARPORT_BUILD / 'build.ninja').exists():
    subprocess.run(['meson', 'setup', str(EARPORT_BUILD), str(ROOT / 'earport/daemon'), '--buildtype=release'], check=True)
subprocess.run(['ninja', '-C', str(EARPORT_BUILD), 'earport-daemon'], check=True)
subprocess.run(['glib-compile-schemas', str(ROOT / 'gnome-extension/schemas')], check=True)
if STAGE.exists():
    shutil.rmtree(STAGE)
for directory in ['DEBIAN', 'usr/bin', 'usr/libexec/handoff', 'usr/share/handoff', 'usr/share/applications', 'usr/share/icons/hicolor/scalable/apps', 'usr/share/polkit-1/actions', 'usr/share/doc/handoff-vibe']:
    (STAGE / directory).mkdir(parents=True, exist_ok=True)
shutil.copy2(ROOT / 'handoff', STAGE / 'usr/bin/handoff-vibe')
shutil.copy2(ROOT / 'handoff', STAGE / 'usr/bin/handoff')
shutil.copytree(ROOT / 'handoff_ui', STAGE / 'usr/share/handoff/handoff_ui', ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(ROOT / 'assets', STAGE / 'usr/share/handoff/assets')
shutil.copytree(ROOT / 'gnome-extension', STAGE / 'usr/share/gnome-shell/extensions/handoff-vibe@asensado.github.io')
shutil.copy2(BUILD / 'airpods-handoff', STAGE / 'usr/libexec/handoff/airpods-handoff-legacy')
shutil.copy2(ROOT / 'packaging/handoff-engine', STAGE / 'usr/libexec/handoff/airpods-handoff')
shutil.copy2(EARPORT_BUILD / 'earport-daemon', STAGE / 'usr/libexec/handoff/earport-daemon')
shutil.copy2(ROOT / 'packaging/update-handoff', STAGE / 'usr/libexec/handoff/update-handoff')
service_dir = STAGE / 'usr/lib/systemd/system'
service_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(ROOT / 'packaging/handoff-vibe-update.service', service_dir)
for folder in ['earport', 'native', 'LICENSES']:
    shutil.copytree(ROOT / folder, STAGE / 'usr/share/doc/handoff-vibe' / folder,
                    ignore=shutil.ignore_patterns('build', 'build-*', '__pycache__'))
shutil.copy2(ROOT / 'packaging/prepare-bluetooth', STAGE / 'usr/libexec/handoff/prepare-bluetooth')
shutil.copy2(ROOT / 'packaging/io.github.asensato.Handoff.policy', STAGE / 'usr/share/polkit-1/actions')
shutil.copy2(ROOT / 'packaging/io.github.asensato.Handoff.desktop', STAGE / 'usr/share/applications')
shutil.copy2(ROOT / 'assets/welcome.svg', STAGE / 'usr/share/icons/hicolor/scalable/apps/io.github.asensato.Handoff.svg')
if (ROOT / 'docs').exists():
    shutil.copytree(ROOT / 'docs', STAGE / 'usr/share/doc/handoff-vibe/docs', ignore=shutil.ignore_patterns('__pycache__'))
for name in ['README.md', 'LICENSE', 'THIRD_PARTY.md', 'LICENSING.md', 'NOTICE']:
    shutil.copy2(ROOT / name, STAGE / 'usr/share/doc/handoff-vibe' / name)
for name in ['usr/bin/handoff', 'usr/bin/handoff-vibe', 'usr/libexec/handoff/airpods-handoff', 'usr/libexec/handoff/airpods-handoff-legacy', 'usr/libexec/handoff/earport-daemon', 'usr/libexec/handoff/update-handoff', 'usr/libexec/handoff/prepare-bluetooth']:
    (STAGE / name).chmod(0o755)
shutil.copy2(ROOT / 'packaging/copyright', STAGE / 'usr/share/doc/handoff-vibe/copyright')
# dpkg-shlibdeps needs package metadata in its working directory.
WORK = BUILD / 'shlibdeps'
(WORK / 'debian').mkdir(parents=True, exist_ok=True)
(WORK / 'debian/control').write_text('Source: handoff\nSection: sound\nPriority: optional\nMaintainer: Asensado <asensado@users.noreply.github.com>\n\nPackage: handoff\nArchitecture: any\nDescription: Handoff GUI\n')
result = subprocess.check_output(['dpkg-shlibdeps', '-O', '-e' + str(BUILD / 'airpods-handoff'), '-e' + str(EARPORT_BUILD / 'earport-daemon')], cwd=WORK, text=True)
shared = next(line.split('=', 1)[1] for line in result.splitlines() if line.startswith('shlibs:Depends='))
deps = 'python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0 (>= 4.8), gir1.2-adw-1 (>= 1.3), bluez, systemd, pulseaudio-utils, pkexec, librsvg2-common, ' + shared
(STAGE / 'DEBIAN/control').write_text(f'''Package: handoff-vibe
Version: 0.2.0
Replaces: handoff (<< 0.3.0)
Breaks: handoff (<< 0.3.0)
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
(STAGE / 'DEBIAN/postinst').write_text('#!/bin/sh\nset -e\nsystemctl daemon-reload 2>/dev/null || true\n')
(STAGE / 'DEBIAN/postrm').write_text('#!/bin/sh\nset -e\nif [ "$1" = remove ] || [ "$1" = purge ]; then\n  rm -f /etc/apt/apt.conf.d/99handoff-vibe-updates /etc/handoff/automatic-updates\nfi\nsystemctl daemon-reload 2>/dev/null || true\n')
(STAGE / 'DEBIAN/postinst').chmod(0o755)
(STAGE / 'DEBIAN/postrm').chmod(0o755)
DIST.mkdir(exist_ok=True)
package = DIST / f'handoff-vibe_0.2.0_{ARCH}.deb'
subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(STAGE), str(package)], check=True)
print(package)
