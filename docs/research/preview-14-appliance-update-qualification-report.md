# Preview.14 Appliance Update Qualification Report

**Date:** 2026-07-31

**Hardware:** Raspberry Pi 5 Model B Rev 1.1, 16 GB RAM, 128 GB storage

**Base image:** Sovereign OS `0.1.0-preview.13`

**Update target:** Sovereign OS `0.1.0-preview.14`

**Source revision:** `865a787` (main, at the time of the build workflow runs)

**Status:** First update transaction qualified with restore, prune, and
rotate-trust actually shipped in the base image (not manually deployed).

## Purpose

Unlike every prior qualification this session, `sovereign-update` on the
device under test was not manually patched — `0.1.0-preview.13` was built
from `main` and flashed fresh, so its `/usr/sbin/sovereign-update` matches
the committed source exactly (SHA-256 verified equal before testing began).
This campaign re-runs the standard update-transaction procedure
(`docs/operations/versioned-appliance-update-qualification.md`) against a
real signed `preview.13`-to-`preview.14` candidate to confirm nothing about
shipping restore/prune/rotate-trust regressed the ordinary appliance-update
path.

## Baseline

- `/opt/sovereign/current` resolved to `0.1.0-preview.13`; Console served
  `Release 0.1.0-preview.13`; `/api/v1/health` reported healthy across
  storage, DNS, update, Pi-hole, and local-access checks.
- `sovereign-update --help` listed `restore`, `discard-restore`, `prune`,
  and `rotate-trust` natively — confirming the shipped binary, not a
  manually deployed one.
- On-device `/usr/sbin/sovereign-update` SHA-256 matched the committed
  source on `main` exactly.

## Interrupted Validation Recovery

- Prepared, backed up, and staged a transaction targeting `0.1.0-preview.14`
  with a fresh ephemeral `preview-local` qualification key.
- `activate` with `SOVEREIGN_UPDATE_QUALIFICATION_INTERRUPT=validating`
  exited `75`.
- After reboot, boot recovery restored `0.1.0-preview.13` before normal
  services started; `verify-update-health` passed once Pi-hole finished its
  own post-boot readiness window (the retry loop from `b3ec10d` absorbed
  this correctly — a raw `curl` issued at `uptime 0m` failed as expected,
  but the health script's own retry loop did not).
- Transaction discarded successfully.

## Forced Health Rollback

- Fresh transaction prepared, backed up, and staged.
- `activate` with `SOVEREIGN_UPDATE_QUALIFICATION_FAIL_HEALTH=1` rolled back
  automatically; pointer and Console reverted to `0.1.0-preview.13`;
  `verify-update-health` passed after rollback.
- Transaction discarded successfully.

## Successful Activation and Reboot

- Fresh transaction prepared, backed up, staged, and activated with no
  overrides. Transaction ended `committed` at `0.1.0-preview.14`.
- Pointer, Console marker, health, and the on-device credential-continuity
  checksum all confirmed correct both before and after a reboot.
- After reboot: `sovereign-update status` reported `installed_version:
  0.1.0-preview.14`, `update_state: committed`; `findmnt` confirmed `/data`
  still mounted from its dedicated partition; zero failed systemd units.

## Conclusion

The `0.1.0-preview.13`-to-`0.1.0-preview.14` update transaction is qualified
on Raspberry Pi 5 hardware, using a genuinely shipped base image rather than
a manually patched one. Shipping restore, prune, and rotate-trust in the
base image did not regress the interrupted-recovery, forced-rollback, or
successful-activation paths. The device now runs `0.1.0-preview.14` as its
committed, real installed release.
