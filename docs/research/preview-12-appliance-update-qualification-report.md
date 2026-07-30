# Preview.12 Appliance Update Qualification Report

**Date:** 2026-07-30

**Hardware:** Raspberry Pi 5 Model B Rev 1.1, 16 GB RAM, 128 GB storage (root
`/dev/mmcblk0p2` ext4, firmware `/dev/mmcblk0p1` vfat, DATA `/dev/mmcblk0p3`
ext4)

**Base image:** Sovereign OS `0.1.0-preview.11`

**Update target:** Sovereign OS `0.1.0-preview.12`

**Source revision:** `581b1c8ac522df4232bc38fc463e876c15d23e01`

**Build workflow runs:**

- preview.11 flashable base (no update candidate):
  [run 30382942658](https://github.com/sovereignfs/sovereign-os/actions/runs/30382942658)
- preview.12 full image and update candidate (source minimum
  `0.1.0-preview.11`, source maximum exclusive `0.2.0`, key ID
  `preview-local`): [run 30382944945](https://github.com/sovereignfs/sovereign-os/actions/runs/30382944945)

**Status:** Preview.11-to-preview.12 versioned appliance update qualified.
This closes the qualification pair named in `ROADMAP.md`'s Milestone 01.1
position statement.

## Scope and Provenance

The device owner flashed `0.1.0-preview.11` and, in an earlier session,
prepared the private-key-free qualification kit for the signed
`0.1.0-preview.12` update candidate on the device (public trust files
installed under `/etc/sovereign/update-trust.d/`, kit staged under
`~/update-qualification-preview12/`) following
[docs/operations/versioned-appliance-update-qualification.md](../operations/versioned-appliance-update-qualification.md).
This report's evidence was gathered by an agent connected over SSH
(password authentication, later supplemented by an installed public key)
that performed the baseline checks, the `prepare`/`backup`/`stage`/
`activate`/`discard` transaction sequence, and the reboot verifications
below against that already-prepared kit. Signature generation and key
custody on the operator machine were not independently re-verified by this
session.

This campaign follows the current documented procedure, which exercises the
`validating` interruption boundary, a forced target-health failure, and a
successful activation. It does not repeat the `backing_up`/`activating`
interruption-hook sweep or the four-role backup-manifest inspection that the
preview.7-to-preview.8 campaign performed; those mechanisms were not changed
since preview.8 and are not the subject of the readiness fixes qualified
here.

## Preview.11 Baseline

- `/opt/sovereign/current` resolved to `0.1.0-preview.11`; `sovereign-update
  status` reported `idle` before staging.
- Console served `Release 0.1.0-preview.11`; `/api/v1/health` reported
  `"status":"healthy"` for storage, DNS, update, Pi-hole, and local-access
  checks.
- `verify-update-health` passed (exit 0).
- `/dns/admin/` returned an HTTP redirect as expected.
- The Pi-hole administrator credential was recorded as a root-readable
  on-device continuity reference before any transaction began.

## Interrupted Validation Recovery

- Reused the already-staged transaction `update-20260728t182715z-6be6a6f1`
  (target `0.1.0-preview.12`, prepared and staged in the earlier session).
- `sovereign-update activate` with `SOVEREIGN_UPDATE_QUALIFICATION_INTERRUPT=validating`
  exited `75`, confirming the interruption hook fired before commit.
- After `sudo reboot`, boot recovery restored `0.1.0-preview.11` before
  normal services started: the release pointer, Console marker
  (`Release 0.1.0-preview.11`), and `verify-update-health` (exit 0) all
  confirmed the prior release was active again with no manual intervention.
- `sovereign-update discard` on the transaction succeeded, confirming
  recovery had already moved it out of `staged` into a discardable terminal
  state.

This directly qualifies the systemd ordering and service-readiness fixes
from `b3ec10d` (`fix: harden appliance activation readiness`): the health
endpoint retry loop in `verify-local-access` and the relaxed
`sovereign-credentials-console.service` / `sovereign-pihole.service`
dependency edges did not block or race the boot-recovery path.

## Forced Health Rollback

- A fresh transaction (`update-20260730t112719z-5a84b633`) was prepared,
  backed up (`backup-20260730t112742z-4d45ec2f`), and staged. The inactive
  target correctly rendered `Release 0.1.0-preview.12` while the served
  Console still showed `0.1.0-preview.11`.
- `sovereign-update activate` with
  `SOVEREIGN_UPDATE_QUALIFICATION_FAIL_HEALTH=1` transitioned the
  transaction through `rolling_back` to a final `rolled_back` state.
- After rollback, the release pointer, Console marker, and
  `verify-update-health` all confirmed `0.1.0-preview.11` was healthy again.
- `sovereign-update discard` on the transaction succeeded.

## Successful Activation and Reboot

- A fresh transaction (`update-20260730t113112z-96bac0df`) was prepared,
  backed up (`backup-20260730t113131z-77d5fe42`), staged, and activated with
  no qualification overrides. The transaction ended `committed` with
  `version: "0.1.0-preview.12"`.
- The release pointer and Console marker both confirmed
  `0.1.0-preview.12`; `verify-update-health` passed (exit 0); the on-device
  credential-continuity checksum matched.
- After `sudo reboot`, the device came back with the pointer and Console
  still on `0.1.0-preview.12`, `verify-update-health` passing, the
  credential-continuity checksum still matching, `/data` still mounted from
  its dedicated `mmcblk0p3` partition, `sovereign-update status` reporting
  `installed_version: 0.1.0-preview.12`, `update_state: committed`, and
  `systemctl --failed` listing zero failed units.

## Cleanup and Exit Evidence

- Removed `/etc/sovereign/update-trust.d/preview-local.pem` and
  `preview-local.json` (public trust files only; no private key was ever
  present on the device).
- Removed the on-device credential-continuity reference
  (`/data/sovereign/update-state/qualification-password.sha256`).
- Removed the qualification kit directory
  (`~/update-qualification-preview12/`) and its transaction-state scratch
  files from the device.
- No credentials, private keys, DNS queries, or other household data are
  recorded in this report.
- Outstanding: the device owner should confirm the ephemeral
  `preview-local` signing private key and its qualification kit were
  deleted from the operator machine that generated and signed the
  `0.1.0-preview.12` manifest; this session had no access to that machine.

## Conclusion

The `0.1.0-preview.11` to `0.1.0-preview.12` update transaction is qualified
on Raspberry Pi 5 hardware. The service-readiness and systemd dependency
fixes that the preview.9-to-preview.10 campaign motivated held under an
interrupted-at-`validating` recovery, a forced target-health rollback, and a
successful activation with reboot persistence, with no regression to
Console, Pi-hole, Nginx, DNS, SSH, DATA, or credential continuity. Persistent
restore automation, retention policy, and production signing operations
remain outstanding before the updater is release-ready for normal users.
