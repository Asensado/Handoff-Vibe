# Handoff reliability work

Tracked in [#7](https://github.com/Asensado/Handoff-Vibe/issues/7), with incidental
sound-triggered switching tracked separately in [#5](https://github.com/Asensado/Handoff-Vibe/issues/5).

## First implementation

Handoff now owns process lifecycle in `handoff_ui/lifecycle.py` and
`native/process_guard.c`, independently of the protocol implementation:

- A global supervisor lease complements the existing per-headset lease. Both
  remain held by the backend until it exits. Duplicate starts cannot race through
  the D-Bus preflight, including different configured headset instances.
- The native backend acquires a session-wide lock before touching Bluetooth,
  including when started directly. The packaged Qt fallback uses the same native
  guard rather than a conflicting QLockFile. It exits if its configured supervisor is gone
  and is killed by the kernel if that supervisor dies unexpectedly.
- Normal shutdown terminates the owned process group, including audio helpers,
  with bounded TERM/KILL escalation. It never kills processes by name.
- The supervisor checks the D-Bus owner's actual PID, addresses calls to that
  unique owner, and exits after 20 seconds without a usable backend response so
  the existing systemd restart policy can recover it. This deadline concerns
  backend responsiveness, not lack of Bluetooth packets or remote playback.
- Automatic audio repair retries only live streams. It cannot escalate to
  restarting an idle output; manual takeover retains that explicit ability.
- An initial remote owner followed by idle is not a request to return to Linux.
  A newer manual takeover cancels an older pause timer, and remote call escalation
  cancels automatic takeover timers and blocks automatic Tipi playback claims.
- Repaired control channels invalidate old ownership telemetry until a new
  source report arrives. Repeated BlueZ connection signals cannot reset or bypass
  the reconnect budget. Successful battery telemetry replenishes that budget. After an exhausted
  burst, a 60-second cooldown permits another control-channel probe while BlueZ
  remains connected; it does not disconnect/reconnect the whole headset or claim
  audio. BlueZ disconnection cancels the probe.

These changes harden the current transport. They do **not** claim to solve every
multi-host contention or stale audio route scenario, and do not implement the
system-sounds filtering preference in #5.

## Upstream review, 2026-11-26

These are upstream reports and proposals, not hardware verification on our setup.

| Source | Finding and use here |
| --- | --- |
| [Earport #8](https://github.com/Anoryth/earport/issues/8) | Notification subscriptions can be ignored with another Apple host connected. The existing feature-ack retry and bounded link reopen are already in our vendored code. Retain these rather than adding a competing connection. |
| [Earport #12](https://github.com/Anoryth/earport/issues/12), [920b0b6](https://github.com/Anoryth/earport/commit/920b0b650a48eaa6ed7a395c231c85bd88f708e5) | First pairing can report Connected before UUIDs. The late-UUID fix and test are already present in Handoff. A Bluetooth connection alone does not confirm a usable control channel. |
| [LibrePods #795](https://github.com/librepods-org/librepods/issues/795) | A one-time audio-card lookup can miss a late card and leave the profile off. Future routing must rediscover cards rather than cache absence. No confirmed merged fix was identified in this issue. |
| [LibrePods #798](https://github.com/librepods-org/librepods/issues/798) | The reporter proposes avoiding profile-off on ear removal because WirePlumber persists it. Preserve the current approach of media pause rather than introducing profile-off as recovery. |
| [Handoff #3](https://github.com/xatuke/handoff/issues/3) | Multiple Linux hosts can repeatedly steal ownership; the reviewed discussion has no implemented fix, only a maintainer follow-up. A lock on one computer cannot arbitrate across computers. |

No upstream code was copied for this change. Existing modified Earport files keep
their GPL notices; Handoff's new lifecycle code is GPL-3.0-or-later.

## Moving beyond the Earport backend

This is an incremental migration, not a renamed independent backend. The current
daemon still supplies protocol parsing, Bluetooth transport, Tipi and D-Bus.
Handoff-owned lifecycle code is the first extracted responsibility.

Next, isolate transport events behind a Handoff adapter and move ownership policy
out of the protocol daemon. The policy needs explicit local playback/manual
intent, remote media/call telemetry, a generation for each request, confirmation
deadlines and bounded repair. A stale callback or repair subprocess must not
override a newer remote owner. The reviewed native audio repair now uses cancellable, deadline-bound pactl
operations and fresh sink discovery, with no temporary sinks, stream moves or
profile cycling. Its effectiveness on each physical headset still needs testing.
Further routing policy must avoid restarting Bluetooth globally. Preserve battery/ANC controls while remote playback owns audio.

Only then replace the adapter's Earport implementation module by module. Keep
corresponding source, attribution and GPL obligations for reused protocol code.
Do not run a new protocol implementation alongside the old one.

## Verification remaining on physical devices

Test Powerbeats Fit and AirPods with iPhone playback and calls, Linux playback,
rapid opposing playback requests, two Linux hosts, ear removal, suspend/resume,
charger/browser alert sounds, reconnect failure and service crash/restart. Compare
actual audible output with the reported owner. Capture sanitized timestamped
ownership and audio-route events when they disagree. No live headset or Apple
device is available in the development environment, so #7 stays open.
