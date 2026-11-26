## Version 0.2.0

- Earport backend integrated into Handoff for compatible AirPods and Beats, with exact Powerbeats Fit recognition.
- ANC, Transparency and Off controls in the app and Handoff top-bar menu. Powerbeats Fit controls were verified while iPhone audio kept playing.
- Individual battery levels, learned listening-time estimates, ear-detection pause/resume and optional proximity cards.
- Optional automatic connection, with activity checks to avoid taking audio from another device during playback or calls.
- Updated GNOME-themed noise selector and live Active / Switching / Handoff / Disconnected status.
- What's new? moved to the dotted menu, with Stable, Beta and Experimental release cards. Optional automatic installation remains stable-only.
- Private diagnostic logs, preserved profiles and existing CLI migration/background support.
- Simpler README with illustrated setup steps and development details at the bottom.
- Handoff Vibe is now GPLv3 or later, permitting personal, commercial and educational use with GPL source/notice obligations. Original MIT/GPL licenses and notices are retained; the complete corresponding source and build instructions are included.

### Install

Download `handoff-vibe_0.2.0_amd64.deb` and run:

```sh
sudo apt install ./handoff-vibe_0.2.0_amd64.deb
```

Close the older GUI first. Sign out and back in once to reload the GNOME extension, then enable Top-bar status in Preferences.

This prerelease targets Debian 13 amd64. Hardware-dependent features still need testing across the model catalog and firmware versions. See `VALIDATION.txt` for the checks completed and remaining live verification.
