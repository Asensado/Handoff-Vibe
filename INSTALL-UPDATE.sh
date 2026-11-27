#!/bin/bash
set -euo pipefail
folder=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
package="$folder/handoff-vibe_0.2.1_amd64.deb"
if [ ! -f "$package" ]; then
    package="$folder/dist/handoff-vibe_0.2.1_amd64.deb"
fi
test -f "$package" || { echo 'Keep this installer beside the Handoff .deb package.'; exit 1; }
if [ "$(id -u)" -eq 0 ]; then
    echo 'Run this as your regular desktop user, without sudo; it requests sudo for package installation.'
    exit 1
fi
compact=$(python3 - <<'PY'
import json, os, re
from pathlib import Path
path = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'handoff/gui.json'
try:
    mac = json.loads(path.read_text()).get('selected', '')
except (OSError, ValueError):
    mac = ''
if re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', mac):
    print(mac.replace(':', '').upper())
PY
)
unit="handoff@${compact}.service"
restart=0
if [ -n "$compact" ] && systemctl --user is-active --quiet "$unit"; then
    restart=1
fi
# Ask the previous GUI to exit gracefully before replacing its files.
gapplication action io.github.asensato.Handoff quit 2>/dev/null || true
if [ -n "$compact" ]; then
    systemctl --user stop "$unit" 2>/dev/null || true
fi
if systemctl --user is-active --quiet earport-daemon.service; then
    echo 'Stopping the separate Earport service so Handoff can own the headset control channel.'
    systemctl --user stop earport-daemon.service
fi
if ! sudo apt install --reinstall "$package"; then
    if [ "$restart" -eq 1 ]; then systemctl --user start "$unit" || true; fi
    exit 1
fi
systemctl --user daemon-reload
if [ "$restart" -eq 1 ]; then
    systemctl --user restart "$unit"
fi
echo 'Installed Handoff Vibe 0.2.1. Device profiles and service settings were preserved.'
echo 'Sign out and back in once to reload the upgraded GNOME companion.'
echo 'Start/Pause Handoff controls switching. Automatic connection and ear detection are in Preferences.'
echo 'If needed, open Advanced logs in the Handoff menu for connection diagnostics.'
