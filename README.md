# Handoff Vibe

A compact GTK 4/libadwaita home for [xatuke/handoff](https://github.com/xatuke/handoff).
Made with ❤️ by Asensado with ChatGPT 6.1-Sol Medium Work.

Open **Handoff Vibe** from your app launcher. The GUI prepares Bluetooth with an
administrator authorization dialog, discovers headsets, guides pairing and
model confirmation, and configures your background service. A desktop
Bluetooth agent is required for pairing. Bluetooth settings can be opened
from setup if pairing needs help.

The device page shows a real product photograph, device name, colored status,
last reported audio owner, background/startup control, Reconfigure, and Remove.
**Advanced logs** is available from the menu. Preferences offers system, light,
and dark appearance. Experimental multiple headset profiles manage one
selected headset at a time, preventing competing audio-ownership requests.
A connected-device count is not guessed; the upstream protocol does not
currently provide it to this application.

## Existing command-line installations

On launch, the GUI detects the conventional user unit
`~/.config/systemd/user/airpods-handoff.service`, validates its headset address,
and identifies the model from its description. It backs up the unit and its
startup/activity state, removes the old unit, creates the GUI-managed unit,
and preserves whether the service was enabled and running. Failure triggers
rollback. **Restore CLI version** is available from Preferences. Custom symlink units,
unknown models, system-wide units, and custom filenames are not silently
migrated. Unknown models can be selected explicitly in setup.

Removing a headset disables and stops its Handoff service and removes its
GUI profile. It leaves the Bluetooth pairing intact. Closing the app keeps
startup-enabled engines running; temporary sessions started in the GUI are
stopped. Background startup means **at user sign-in**, not before login.

## Requirements and compatibility

The package built here targets Debian 13 (amd64). Its dependency metadata
records the actual system library minimums. Older Debian/Ubuntu systems may
need a source rebuild against their own Qt libraries. GTK 4.8+ and
libadwaita 1.2+ are used. PulseAudio or PipeWire's PulseAudio compatibility
service is required, along with BlueZ, systemd user services, and PolicyKit.

AirPods 2/3/4, AirPods Pro/Pro 2, AirPods Max, Beats Fit Pro, Powerbeats Fit,
Powerbeats Pro/Pro 2, and Solo Pro are model candidates. Actual switching
support depends on headset firmware and the original daemon. This build
has **not** been verified by switching live audio on each model. AirPods 1,
Studio Buds/+, Studio Pro, Solo Buds, and W1-only models are blocked.
Unknown models are blocked unless the user confirms an exact catalog model;
known incompatible IDs cannot be overridden. Bluetooth identity is not
cryptographic attestation of authentic hardware.

The main status distinguishes Bluetooth connection, daemon running, and
switching-protocol handshake. “Active” requires recent live engine telemetry
and a completed handshake. “Switching audio” is a brief pending-claim state,
not confirmation that audio has moved. Audio ownership comes from headset
notifications. No Apple Account credentials are collected.

Bluetooth preparation backs up `/etc/bluetooth/main.conf`, changes only the
General DeviceID setting, and restarts Bluetooth. Re-pair existing headphones
after this change because they cache the computer's Bluetooth identity.

## Build and developer preview

Build dependencies: cmake, g++, qt6-base-dev, qt6-connectivity-dev, dpkg-dev, patch.

```sh
python3 packaging/build-deb.py
```

Install the resulting `dist/handoff-vibe_0.1.0_amd64.deb` with your graphical package
installer, then open Handoff Vibe. If a graphical installer is not present, the
usual alternative is `sudo apt install ./dist/handoff-vibe_0.1.0_amd64.deb`.

Preview without changing services or Bluetooth:

```sh
./handoff-vibe --demo --screen welcome
./handoff-vibe --demo --theme dark
```

`--demo` is explicitly marked and does not write application configuration,
start/stop services, migrate the old unit, or change Bluetooth.

Run validation:

```sh
python3 -m unittest discover -s tests -v
xvfb-run -a python3 tests/ui_smoke.py
```

See `THIRD_PARTY.md` for original developer credits and product image sources.

## Version 0.1.0

The package name and launcher command are **`handoff-vibe`**, and this iteration
is version **`0.1.0`**. The Debian output is
`handoff-vibe_0.1.0_amd64.deb`. This intentionally resets the version under a new
package identity. The package declares `Conflicts: handoff` and `Replaces:
handoff`, allowing APT to replace the previous package rather than install two
copies. Install through a graphical package installer that resolves package
conflicts or use APT; a raw file copy is not a package transition.

Close the old GUI before installing the new package. The desktop application
ID, settings folder, original service names, and engine location remain stable
for compatibility. A `/usr/bin/handoff` symlink remains as a legacy command
alias, while the desktop launcher runs `handoff-vibe`.

Preferences now offers **Restore CLI version** when an original service backup
exists, or **Transition to CLI version** otherwise. Original service bytes and
startup/activity settings are restored after validating that its executable
still exists. On failure, GUI service states are restored. CLI mode prevents
automatic migration on later launches. Use **Move back to GUI** to opt back in.
Without a prior backup, the CLI service uses the packaged engine, so keep the
package installed. Bluetooth configuration and pairings are retained.

The Asensado credit links to https://github.com/Asensado/. On the main About
page, **A Message for You** sits directly below **Details** and opens its own
page with Asensado's message.

A discreet daily verse is selected from 31 offline World English Bible (WEB)
verses. The local calendar date controls selection, including month/year
boundaries, and an open window refreshes within 60 seconds of a date change.
The World English Bible is public domain.

The package includes a GNOME Shell 48 extension. After the first installation,
sign out and back in once to let GNOME discover it. Then enable **Preferences →
GNOME integration → Top-bar status**. It shows a headphone icon, colored dot,
status, and a menu shortcut to the application. It reads config and engine
telemetry asynchronously and checks systemd without requiring the GUI window
to stay open. The extension's pure status logic is tested; live GNOME loading
and real Bluetooth switching still need validation on a desktop/headset.

## License

Asensado's additions are **PolyForm Noncommercial 1.0.0**, with separate written
permission required for commercial uses outside its terms. The original
Handoff engine stays **MIT**. The unmodified MIT engine and the integration
patch are kept separately. This is a source-available project, not an
OSI-approved open-source license. Earlier MIT grants are not revoked.

See `LICENSE`, `NOTICE`, `LICENSING.md`, `LICENSES/`, and `THIRD_PARTY.md` for
scope, original attribution, and assets not covered by the project license.
