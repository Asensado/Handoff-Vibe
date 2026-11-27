# Maintaining Handoff Vibe

## Main branch rules

Three active rulesets target refs/heads/main. Snapshots in .github/rulesets record the settings; GitHub's live settings are authoritative.

| Rule | Enforcement |
| --- | --- |
| main-history | No branch deletion or force pushes, with no bypass actors |
| main-checks | GitHub Actions debian check must pass against current main; no bypass actors |
| main-review | Pull requests, one approval, code-owner review, stale-approval dismissal, latest-push approval and resolved review conversations |

Repository administrators have a pull-request-only exception to the review rules so the sole owner can merge their own work. This does not bypass the separate CI or history rules. Contributors with Write or Maintain access have no bypass. Granting another person Admin would also grant that review exception, so keep administration limited.

CODEOWNERS names Asensado for all files. It becomes effective after that file lands on main. Until then, one approving review is still required for other contributors. Prefer merge commits for a clear PR-to-revert relationship. Signed commits are not required until contributors and release automation have a verified signing setup.

## Releasing

1. Test the exact installed candidate on hardware. Record the outcome in docs/0.2.1-READINESS.md and the PR. Fix failures and retest affected cases.
2. Confirm security regressions, native tests, UI smoke checks and packaging pass on the final source. Require the debian check from GitHub Actions.
3. Only after the hardware gate passes, prepare the final version: app __version__, package version/filename, installer paths/messages and RELEASE.json must agree on 0.2.1; tag v0.2.1, prerelease false. Update the README download link and replace its candidate notice.
4. Merge through a pull request after CI. Do not push directly to main or weaken its protections to release.
5. The release workflow runs only on main. It builds/tests as an unprivileged user and renders screenshots into the source archive. It does not commit/push screenshots to main. Publication uses the workflow token only in its final publishing step.
6. Verify the published tag points at the tested commit, source/package/installer/checksum assets exist, package metadata is correct and the What's new? card is Stable.

Release publication is authorized after all gates pass, not merely after CI succeeds. Checksum files are integrity metadata, not independent release signatures; privileged updating stays disabled.

## Rollback

Preserve history. Create a rollback branch from current main and revert the specific offending commit, or use git revert -m 1 <merge-commit> for a complete merged PR. Review the diff, run CI, retest the affected device behavior, and merge a rollback PR. Never reset or force-push main, retarget an existing release tag, or replace published assets silently.

Preserve the security hardening when reverting a functional change. Prefer a corrected follow-up package with a new version to returning users to the unsigned automatic updater in 0.2.0. Close the app and stop its managed user service before deliberately installing a replacement package. Keep profiles and migration backups, and sign out/back in for GNOME code changes.
