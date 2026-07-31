# Production-Signed Restore Qualification Report

**Date:** 2026-07-31

## Purpose

Close another gap flagged in the
[install qualification report](first-production-signed-release-install-qualification-report.md):
`restore` had never been exercised against a backup created as part of an
actual production-signed release install. The `v0.1.0-preview.17`
install (see that report) created a real pre-activation backup
(`backup-20260731t210635z-c3b3426e`) as a side effect of the transaction
itself — this campaign restores from it for real, without inventing new
product content just to justify the test.

## Method

Starting state: device on `0.1.0-preview.17`, `committed`, healthy.

1. Recorded baseline SHA-256 fingerprints of the live Pi-hole persistent
   state: `gravity.db`, `cli_pw`, `pihole.toml`, `hosts/custom.list`.
2. Injected a detectable canary: appended `restore-canary.invalid` to
   `hosts/custom.list`, confirmed the file's hash changed.
3. Ran `sovereign-update restore backup-20260731t210635z-c3b3426e`.
   Correctly **rejected** with `RESTORE_VERSION_MISMATCH`: the backup's
   recorded source version (`0.1.0-preview.14`, taken pre-activation) no
   longer matches the installed release (`0.1.0-preview.17`) — this
   backup was created for the update transaction's own rollback use, not
   as a same-version operator restore target, and the safety check
   correctly refused to apply it silently.
4. Re-ran with the documented `--force` override (this is a deliberate,
   explicit operator decision the CLI supports, not a bypass of a bug)
   to exercise the restore path anyway. Committed:
   `restore-20260731t212853z-15a506cb`.

## Result

- `hosts/custom.list` hash reverted to the pre-canary original — the
  canary was genuinely removed, not left in place.
- `gravity.db` and `pihole.toml` (the actual admin credential storage)
  matched their pre-canary baselines exactly.
- `cli_pw` differed from baseline, as expected — it's Pi-hole's ephemeral
  per-container-start CLI session token, regenerated on every restart,
  not the persisted admin secret. Docker logs confirmed the real
  password was loaded from the restored configuration
  (`FTLCONF_webserver_api_password is used`).
- No failed systemd units, Pi-hole container `healthy`, Console
  responding, DNS resolving.
- `sovereign-update status` remained `installed_version:
  0.1.0-preview.17`, `committed` throughout — `restore` recovers
  persistent data without changing which release is active, as designed.

## Recommendation

`prune` and `rotate-trust` still have not been exercised as part of an
actual signed-release install cycle. Unlike `restore` here, there isn't
an equivalent "already exists as a side effect" shortcut for either:
qualifying them meaningfully needs either a second real release (to give
`prune` genuine multi-release retention decisions to make) or a real
rotation of the production key itself (a much bigger, deliberate
decision that shouldn't be manufactured just to check a box). Leave both
open until there's real cause to exercise them, rather than staging an
artificial scenario.
