# Finding: The Appliance File Set Cannot Grow Through a Normal Update

**Date:** 2026-08-01

## Summary

Attempting a real, production-signed update from `0.1.0-preview.17` to
`0.1.0-preview.18` — the first release to add a new file
(`appliance/bin/console-auth`) to the appliance's canonical set since that
set was established — was rejected at `stage` with `INCOMPLETE_RELEASE`
("Release payload has missing or unknown files"). This is not a bug in
`.18`, and not specific to Console auth: it is a structural ceiling in the
versioned-release update design, exercised for real for the first time by
this attempt.

## Root Cause

The installed `/usr/sbin/sovereign-update` enforces a hardcoded
`RELEASE_FILES`/`APPLIANCE_FILES` allowlist of exactly which files an
appliance release may contain (`validate_release_payload` /
`validate_target_configuration`). Per
[docs/design/versioned-appliance-release.md](../design/versioned-appliance-release.md):

> The stable units and updater are deliberately not self-updated in this
> slice. Changing that recovery substrate requires a separate
> bootstrap/self-update design.

Every real update qualified before this one (preview.9→10, preview.11→12,
preview.13→14, preview.14→17) changed *content* inside already-known files,
or added new updater *subcommands* (`restore`, `prune`, `rotate-trust`,
`check`) — none of which touch the appliance file allowlist, since
subcommands live in the updater binary itself, not in a release payload.
`console-auth` is the first new *appliance* file ever shipped in a release.
Because the updater that validates a release's file set is never itself
replaced by an update, its allowlist is permanently frozen at whatever it
was when the device was last flashed (or manually patched) — it cannot be
taught about a new file by the very release that introduces that file.

**Consequence:** no release can add or remove a file from the appliance's
canonical set on an already-flashed device, ever, through the normal
`prepare`/`backup`/`stage`/`activate` path. This is true for every device
flashed to date, not only the qualification Pi.

## What Was Verified, and What Wasn't Touched

- `prepare` and `backup` both succeeded normally — the signed manifest
  verified correctly, and the pre-activation backup was created and
  restarted Pi-hole cleanly. This confirms the production key, `.18`'s
  signature, and the backup path all still work correctly; the rejection
  is specific to `stage`'s file-set check, not the signing/trust chain.
- `stage` failed *before* any extraction reached the live filesystem
  (`stage_release`'s exception path removes its own temporary candidate
  directory and re-raises without touching `/opt/sovereign/current`) — the
  device never stopped serving DNS or Console, and remained on
  `0.1.0-preview.17` throughout.
- The resulting transaction (`update-20260801t072255z-bd4a4874`) is stuck
  at `backed_up`: retrying `stage` will fail identically every time, and
  `discard` refuses it (`INVALID_TRANSACTION_STATE` — only
  `rolled_back`/`recovery_required` transactions are discardable). Per the
  project owner's direction, this was left in place rather than forced
  into some other state; it has no effect on the device's actual running
  services and is a candidate for `prune`'s retention policy to eventually
  reclaim on its own schedule.
- No manual file deployment was involved in reaching this finding — this
  was a genuine, unmodified `prepare`/`backup`/`stage` attempt against a
  real signed release, which is exactly why the result is trustworthy.

## Why This Wasn't Caught Earlier

Every qualification campaign this session (and before it) exercised
updates that only changed file *contents* or added updater *subcommands*.
Nothing in the unit test suite constructs a scenario where a staged
release's file set differs from `RELEASE_FILES`/`APPLIANCE_FILES` as
computed by an *older* copy of the validation code versus the one used to
build the release — `tests/test_update_client.py` and
`tests/test_update_release.py` both validate against the *same* checked-out
source on both sides, which can never reproduce this mismatch. This is a
second data point (after the `sovereign-proof.service`/`prune` interaction
found during the `.17` install) that this project's file-set and
boot/update interactions are only fully exercised by real, sequenced
hardware use — not by unit tests, which necessarily test one version of
the source against itself.

## Open Question, Not Resolved Here

This finding surfaces the exact gap `docs/design/versioned-appliance-release.md`
already named as future work ("a separate bootstrap/self-update design"),
but does not resolve it. Realistic directions, none chosen:

- **A genuine self-update mechanism** for `/usr/sbin/sovereign-update`
  itself, delivered and activated through its own careful, health-gated
  process — the most complete fix, and the most design and engineering
  effort by far.
- **Never add appliance files after the base image ships** — treat the
  appliance file set as fixed at flash time, and require any future
  addition (like this one) to wait for the next full image / reflash
  cycle rather than an in-place update. Cheapest, but means Console auth
  (and anything like it) cannot reach already-flashed devices without a
  reflash, which is a real capability regression from what update
  installation was assumed to be able to do.
- **A narrower "additive-only" relaxation**: change the validation to
  reject only *missing* required files and *wrong* modes, not *extra*
  files beyond the allowlist it knows about. This would have let `.18`
  install today, but weakens the "closed bundle manifest" integrity
  property this project has otherwise been careful about (`validate_release_payload`'s
  docstring-level intent is a fully closed, enumerated file set, not an
  open one) — worth scrutiny before treating it as a quick fix.

This needs the project owner's judgment, the same way ADR-0006 and
ADR-0007 required a deliberate choice among real trade-offs rather than a
default.
