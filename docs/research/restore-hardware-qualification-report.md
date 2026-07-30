# Persistent-Data Restore Hardware Qualification Report

**Date:** 2026-07-30

**Hardware:** Raspberry Pi 5 Model B Rev 1.1, 16 GB RAM, 128 GB storage,
installed release `0.1.0-preview.12`

**Status:** `sovereign-update restore` and `discard-restore` qualified against
real Pi-hole state on Raspberry Pi 5. Not yet part of a signed release; the
updater binary under test was deployed manually for this campaign (see
Method).

## Purpose

`sovereign-update restore` was implemented and unit-tested (see
`tests/test_update_restore.py`) but, per
[BACKUP_AND_JOURNAL.md](../../update/BACKUP_AND_JOURNAL.md), had not been
qualified against real Pi-hole state on real hardware. This campaign closes
that gap: it exercises the full extract-validate-swap-verify contract against
the device's actual gravity database, Sovereign configuration, and Pi-hole
administrator secret, including both the successful-recovery and
forced-rollback paths.

## Method

The device's flashed `/usr/sbin/sovereign-update` (part of the base image,
not the versioned release payload — see
[Versioned Appliance Release Design](../design/versioned-appliance-release.md))
predates the `restore` command. Since this campaign only needed to qualify
the updater logic itself — not build and flash a new base image — the
locally modified script was deployed directly to the device for the duration
of the test, after preserving the original file at
`/root/sovereign-update.orig-preview.12`. An ephemeral, private-key-free
qualification trust key (`restore-qual-local`) was used to sign a minimal
manifest so `prepare`/`backup` could reach `backed_up` and produce a real
backup. At the end of the campaign the device's `/usr/sbin/sovereign-update`
was reverted to the original preview.12 binary (checksums verified equal),
the fabricated transaction and its status record were removed, and the
qualification trust files and kit were deleted. The device's real
`update-status.json` was restored to reflect its true `committed` state on
`0.1.0-preview.12`. Getting this command onto real devices through the
normal signed-release pipeline is separate follow-up work.

Before making any live-data change, an independent, out-of-band safety copy
of the three live directories was taken with a plain `tar` command outside
the updater, and reference SHA-256 checksums of the live gravity database and
administrator secret were recorded.

## Real Backup Creation

`sovereign-update prepare` and `backup` (unmodified code paths, already
qualified in the preview.7-to-preview.8 and preview.11-to-preview.12
campaigns) produced a genuine quiesced backup: a 3.87 MB `pihole-state.tar.zst`
plus configuration, secrets, and release-pointer archives, each with a
recorded size and SHA-256 in `backup-manifest.json`. Pi-hole was briefly
stopped and restarted health-gated, matching the documented consistency
method.

## Scenario 1 — Successful Restore

Live `gravity.db` and the Pi-hole administrator secret were overwritten with
marker content (confirmed by differing checksums). `sovereign-update restore
<backup-id>` was run with no overrides:

- the restore transaction progressed `available -> extracting -> extracted ->
  restoring -> verifying -> committed`;
- `gravity.db` and the administrator secret matched their original SHA-256
  checksums exactly after restore;
- `/data/sovereign/secrets` was `0700` and the secret file `0600`, both
  `root:root`, matching the contract's secrets-handling requirement;
- no `.pre-restore.*` or `.rollback-failed.*` directories remained after
  commit;
- `sovereign-pihole.service` was active and
  `verify-update-health` passed (exit 0).

## Scenario 2 — Forced Health-Failure Rollback

Live data was corrupted again and restore was run with
`SOVEREIGN_UPDATE_QUALIFICATION=1 SOVEREIGN_UPDATE_QUALIFICATION_FAIL_HEALTH=1`,
reusing the same interrupt/override mechanism already qualified for update
transactions:

- the restore correctly failed at the post-restore health gate and rolled
  back automatically;
- **a bug was found and fixed during this run:** the shared
  `qualification_health_failure()` helper hard-coded the update-transaction
  failure code `POSTUPDATE_HEALTH_FAILED`, so a qualification-forced restore
  failure was misreported under the wrong code. Fixed by parameterizing the
  code (`qualification_health_failure(code=...)`); restore now correctly
  reports `POSTRESTORE_HEALTH_FAILED`. A regression test
  (`test_qualification_forced_failure_uses_restore_specific_code`) was added.
  This was a diagnostic/audit-trail defect only — the rollback safety
  mechanism itself was unaffected in either version;
- after rollback, live data matched the *pre-restore* (corrupted) checksums
  exactly — confirming rollback correctly undoes the swap rather than
  reapplying the backup;
- no leftover `.rollback-failed.*` directories remained after the rollback
  committed;
- the transaction ended `rolled_back` with `recovery_action: none`;
- Pi-hole remained active and healthy throughout.

The fix was redeployed to the device and the scenario was re-run end to end,
confirming the corrected failure code with the same successful rollback
behavior.

## Cleanup and Exit Evidence

- The device's `/usr/sbin/sovereign-update` was reverted to the original
  preview.12 binary (SHA-256 verified identical to the pre-campaign backup).
- The fabricated qualification transaction and its stale
  `update-status.json` record were removed; `update-status.json` was
  restored to reflect the device's true `committed` state on `0.1.0-preview.12`.
- The qualification trust files
  (`/etc/sovereign/update-trust.d/restore-qual-local.{pem,json}`), the
  qualification kit, the out-of-band safety copy, and temporary scripts were
  all removed from the device.
- The real backup created during this campaign
  (`backup-20260730t123816z-06d5aa00`) was left in place as a genuine,
  valid recovery point — it was not deleted.
- The restore transaction journals under
  `/data/sovereign/update-state/restores/` were retained as evidence,
  consistent with how update-transaction journals are retained.
- No credentials, private keys, or household data are recorded in this
  report. The one handling lapse worth noting: an initial `scp -r` of the
  qualification kit briefly copied the ephemeral private key to the device
  before it was caught and deleted within the same operation; the key was
  a disposable qualification-only key, never used for any production
  signing, and was destroyed afterward.

## Conclusion

`sovereign-update restore` correctly recovers real Pi-hole state, Sovereign
configuration, and secrets from a real signed backup on Raspberry Pi 5
hardware, with byte-exact data recovery, correct secrets permissions, and a
verified automatic-rollback path when the post-restore health gate fails.
One diagnostic-only bug (wrong failure code under forced-failure
qualification) was found and fixed as part of this campaign. Getting this
command shipped in a real signed release (rather than manually deployed for
qualification) and wiring it into the automatic update-rollback path for
future data migrations remain separate follow-up work, as does backup
retention policy and production signing-key custody.
