# Independent pre-release code review, 2026-11-26

One independent, read-only review covered the tree at `a139b02`, including
`handoff_ui/`, privilege/update scripts, packaging/workflows, GNOME, native
lifecycle/routing and the inherited C/C++ backend code. The implementation agent
then reproduced/verified findings and applied fixes. This is not a penetration
test or a guarantee that no vulnerabilities remain. No second independent review
is represented by the subsequent implementation checks.

## Findings and disposition

| Priority | Finding | Tracking | Remediation |
| --- | --- | --- | --- |
| P1 trust design | Root updater installs release packages using a digest supplied by the same GitHub API; no independently pinned publisher authentication | [#9](https://github.com/Asensado/Handoff-Vibe/issues/9) | Privileged installation and automatic-update enablement fail closed. No privileged network/APT execution remains in the helper. Upgrade removes old hooks; release browsing stays unprivileged. |
| P2 hardening | Elevated updater lacks Python `-I` and resolves subprocesses through its environment | [#9](https://github.com/Asensado/Handoff-Vibe/issues/9) | Isolated Python entry points; updater no longer launches installers; regular GUI/backend entry points reject root. This was not a demonstrated unprivileged pkexec bypass: pkexec normally sanitizes the environment. |
| P1/P2 reliability | Unbounded shell/audio repair can strand streams in a null sink or outlive its backend | [#7](https://github.com/Asensado/Handoff-Vibe/issues/7) | Replace shell/null-sink shuffling with Handoff-owned native repair: fixed pactl executable, explicit argv, per-command deadlines, leaf-child parent-death protection, cancellation and bounded resume cleanup. No temporary sinks, stream moves or profile changes. Physical recovery effectiveness still needs testing. |
| P2 | Wrong-shaped JSON or runtime I/O exceptions can abandon GLib supervision | [#10](https://github.com/Asensado/Handoff-Vibe/issues/10) | Typed/ranged preference normalization and callback exception handling that exits/reaps for bounded service recovery; stderr diagnostics survive unwritable status paths. |
| P2 | A stale profile/status can send commands to a replacement headset | [#11](https://github.com/Asensado/Handoff-Vibe/issues/11) | Verify live DeviceAddress and pin a unique D-Bus owner for GUI and GNOME commands. Reject stale selections/owners; selected disconnected profiles retain a fixed identity for Connect. |

The independent review found no confirmed remote memory-corruption issue or root
escalation through the normal sanitized Polkit path. That is a statement about
what this review found, not proof of absence.

## Applicable additional report

The user supplied a separate Gemini report. Verified items are tracked in
[#12](https://github.com/Asensado/Handoff-Vibe/issues/12): separate slow setup from
live control/read work, own/remove log timers and bound in-flight requests,
discard stale Preferences callbacks, stop closing through busy setup, tolerate
missing inactive units on exit, compare prerelease versions safely, destroy fading
proximity actors, avoid redundant Bluetooth preparation and create backup parents
privately. These are implementation checks following the one independent review.

APT lock contention and non-atomic updater writes no longer apply because that
privileged updater path has been retired. The reported noexec CLI-export fixture
failures do not justify weakening executable checks: CLI export itself is retired
at the user's request in [#13](https://github.com/Asensado/Handoff-Vibe/issues/13).
Original service backups and safe import remain; no CLI service is created.
Hardcoded release naming is left under the release configuration process; no
0.2.1 version bump or publication is part of this change. Existing Bluetooth
configuration backups are deliberately not erased by a package purge.

## Verification and release gates

Regression coverage exercises rejected privileged install actions, hostile
PYTHONPATH startup, root rejection, malformed settings, unwritable runtime,
verified device/owner command dispatch, prerelease comparison, retired CLI export,
bounded/cancelled/failed native repair and UI timer/setup/worker lifetimes.
Clean Debian CI builds the package and runs Python, indicator, complete native,
Qt fallback and native GTK smoke checks. Consult the associated pull request for
the final CI result; no release is implied by this document.

Before 0.2.1: merge the checked fixes, then validate Powerbeats Fit/iPhone ownership,
phone calls, local playback, alerts, reconnect recovery and service crash/stop on
physical hardware. #7 remains open until that evidence exists. Signed unattended
updates need a separately established signing trust and protected/offline signing
process before re-enabling installation; no private signing key was generated or
stored in the repository.

Already-installed 0.2.0 clients do not receive these changes until upgraded. Keep
their automatic updater disabled; the README supplies an isolated helper command
to remove the old hook. The existing published release was not silently replaced.
