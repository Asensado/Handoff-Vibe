# Handoff Vibe 0.2.1

Security and everyday reliability improvements for compatible AirPods and Beats on Linux.

## Security

- Disabled unsigned automatic and in-app administrator installation. Release checks remain read-only; review and install downloads manually. GitHub checksums are integrity checks, not independent publisher signatures.
- Isolated Python launchers and root rejection for the ordinary app and engine. Bluetooth preparation still uses a narrowly scoped administrator helper.
- Headset commands verify the selected Bluetooth address and pin the live D-Bus owner.
- Validated saved preferences, bounded audio-repair commands and supervised child cleanup. Private runtime logs retain diagnostics when the system journal is unavailable.

These fixes are implemented in the candidate source and covered by regression tests. They do not guarantee the absence of vulnerabilities or retrofit already-installed 0.2.0 builds.

## Quality of life

- Fixed the partially blank installed app window and missing GNOME preference helpers.
- Ctrl+, opens Preferences; Ctrl+L opens Advanced logs.
- What's new? distinguishes stable releases, release candidates, betas and experimental builds with coloured badges.
- Separate workers keep setup and release checks from blocking live controls. Log refresh timers and stale window callbacks are cleaned up.
- CLI export/restore is retired. Existing import support and migration backups remain.

## Headset controls

- Noise cancellation, Transparency and Off remain available in the app and GNOME menu, including during iPhone audio on the tested Powerbeats Fit.
- GNOME reports Active, Switching, Handoff and Disconnected states. Volume and audio output selection remain in GNOME's sound menu.
- Battery readings and learned listening estimates appear when available. Ear-removal pause preferences control Linux media players; iPhone playback follows its own setting.

## Unavailable features

Automatic connection and proximity cards are inactive and greyed out. Automatic connection needs hardware validation (#17); the card is being replaced with a battery notification and Connect action (#1). Spatial audio and broader model validation remain future work. Other headset models, firmware and Bluetooth adapters may behave differently.

## Known issue carried into 0.2.1

Charger, browser alert and notification sounds can still trigger unwanted switching to Linux (#5). This remains open and is deferred to 0.2.2. Ear-pause on Linux and suspend recovery were confirmed working on the test system; other hardware and edge cases may differ.

## Install or upgrade

Targets Debian 13 amd64. Download handoff-vibe_0.2.1_amd64.deb from this release and install it with APT. Close the older app first, then sign out and back in after upgrading to reload the GNOME companion. Profiles remain in place.

sudo apt install ./handoff-vibe_0.2.1_amd64.deb

The included INSTALL-UPDATE.sh can stop and restart the selected managed service during an upgrade. Automatic package installation is unavailable until an independently authenticated signing channel exists.

## Free software and credits

Handoff Vibe is GPLv3-or-later. Personal, commercial and educational use is permitted under the license; preserve notices and supply corresponding source when distributing covered software. Original Qt Handoff code retains its MIT license; Earport code retains its GPL notices. Complete corresponding source and build instructions are included.
