# Licensing and scope

Handoff Vibe is source-available under **PolyForm Noncommercial 1.0.0** for
Asensado's contributions. It is not presented as OSI-approved open-source
software. The restriction covers commercial uses generally, not only resale;
read the complete license for its permitted-purpose provisions and exceptions.
Commercial permission outside those terms requires a separate written license
from Asensado: https://github.com/Asensado/.

## Which terms cover which files?

| Material | Applicable terms |
| --- | --- |
| `handoff_ui/`, `gnome-extension/`, `packaging/`, `tests/`, `handoff-vibe`, original documentation and original app artwork | PolyForm Noncommercial 1.0.0, to the extent licensable by Asensado |
| `patches/0001-gui-integration.patch` | PolyForm Noncommercial 1.0.0 for Asensado's original additions; unchanged context from upstream remains MIT |
| Original code in `upstream/` | MIT, with original attribution retained in `upstream/LICENSE` |
| `LICENSE` and texts in `LICENSES/` | Respective license texts; their inclusion does not relicense third-party code |
| Apple/Beats product photos under `assets/` | Third-party assets, not licensed for redistribution by Asensado; see `assets/sources.json` and `THIRD_PARTY.md` |
| World English Bible passages in `assets/verses.json` | Public domain translation; original selection/integration does not restrict the underlying text |

The build copies the pristine MIT engine into `build/engine-source/` and
applies the integration patch there. This keeps upstream code and project
additions distinguishable. A compiled engine containing both has the
corresponding MIT and PolyForm obligations for its respective portions.

MIT permits distribution of modifications and larger works under different
terms while requiring preservation of its notices. Nothing here removes the
original author's MIT permissions or prevents independent use, modification,
or sale of the original MIT engine. This project cannot impose restrictions
on other parties' code or assets.

## Previous MIT copies

This edition does not retract permissions already granted for earlier copies
distributed under MIT. In particular, changing this archive's license cannot
retroactively prevent recipients of a previous MIT-licensed copy from using
that copy under its existing terms.

## GitHub

Add the included `LICENSE`, `NOTICE`, `LICENSING.md`, `LICENSES/`, and upstream
notices to the repository. PolyForm is added as a license file manually; no
claim is made that it appears in GitHub's new-repository license picker or
will receive a particular automatic license badge. Keep third-party notices.
Review photo redistribution rights before publishing bundled product images.
