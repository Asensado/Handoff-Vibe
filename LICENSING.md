# Licensing

Starting with **0.2.0**, Asensado licenses Handoff Vibe's original application,
service integration, updater, packaging, tests and original artwork under
**GNU GPL version 3 or, at your option, any later version** (`GPL-3.0-or-later`).
The former noncommercial restriction is removed from these contributions.
The 0.2.0 release replaces the old manufacturer photos with original, logo-free
GPL-licensed device illustrations. Device names remain their owners’ trademarks.
Personal, commercial and educational use are permitted. GPL obligations apply
when covered software is conveyed, including preservation of notices and the
availability of complete corresponding source for covered binaries. See the
unmodified full license in [LICENSE](LICENSE).

## Component scope

| Files/material | Terms |
| --- | --- |
| Handoff GTK app, original integration, packaging and tests | GPL-3.0-or-later, copyright 2026 Asensado |
| Original xatuke/handoff code in `upstream/` | MIT; original rights and notices retained in `upstream/LICENSE` and `LICENSES/MIT-upstream.txt` |
| Asensado's additions/modifications to the original Qt engine | GPL-3.0-or-later; unchanged MIT code remains MIT |
| `earport/` backend and local modifications | GPL-3.0-or-later; upstream copyright headers, full source, build scripts and credits retained |
| Complete `gnome-extension/` companion | GPL-3.0-or-later; imported Earport components retain their original notices |
| Original device illustrations in `assets/` | GPL-3.0-or-later, copyright 2026 Asensado |
| World English Bible passages | Public domain; not restricted by the code license |

The original MIT code can be used under its own MIT terms independently.
GPL code is not relabelled as MIT or subjected to an additional noncommercial
restriction. The separate Earport executable communicates with Handoff over
D-Bus; its complete corresponding source is shipped with the source release,
and is also included in the Debian package documentation.

`earport/UPSTREAM.txt` identifies the vendored upstream commit and local changes;
`earport/CREDITS` preserves LibrePods protocol-research acknowledgments. The
release includes the source actually used to build its binaries, along with
build and installation scripts.

Earlier copies retain permissions already granted with those copies. This
license change does not retract previous MIT permissions or erase third-party
copyrights. The app's About page and the README state the current GPL license.

See [NOTICE](NOTICE), [THIRD_PARTY.md](THIRD_PARTY.md), [earport/LICENSE](earport/LICENSE)
and [gnome-extension/LICENSE](gnome-extension/LICENSE) for retained notices.
