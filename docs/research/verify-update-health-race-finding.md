# Finding: `verify-update-health` Raced Pi-hole's Startup on a Long-Lived Device

**Date:** 2026-08-01

## Summary

Hardware-qualifying the first Console-triggered install (ADR-0009,
`v0.1.0-preview.19`) failed at the `backing_up` state:
`PREUPDATE_HEALTH_FAILED — "Pi-hole did not recover after backup"`. The
transaction correctly entered `recovery_required` and no data was lost —
this is the safety mechanism working as designed. But investigation found
a real, previously-latent bug in what it was gating on, not a fluke.

## Root Cause

`verify-update-health` (used at every health-gated boundary in the update
system: pre-update backup, post-activation, rollback, post-restore) was a
**single-shot check with no retry or wait**. It runs immediately after
`systemctl start sovereign-pihole.service` returns. Pi-hole's own Docker
healthcheck, and the rest of the checklist, don't necessarily pass in that
exact instant — FTL has to import the on-disk query database before it
reports healthy, and that import takes measurably longer as a device's
real query history grows.

This device has been in continuous real use across this entire session
(hardware-qualifying every prior update, restore, and Console feature) and
had accumulated 10,133 real queries by this point — confirmed via
`docker logs pihole`, which showed `Imported 10133 queries from the
on-disk database` as part of the exact restart this backup triggered.
Running `verify-update-health` manually moments later, once Pi-hole had
finished settling, passed cleanly with no changes — proving the checks
themselves were correct, just raced.

This never surfaced in any prior qualification this session because every
earlier campaign either used a freshly-flashed device with little to no
accumulated query history, or happened to have Pi-hole recover fast enough
by chance. It is exactly the kind of bug that only long-running real
hardware use, not a fresh qualification device or any unit test, would
ever find.

## Fix

`verify-update-health` now retries the full check set (all of it, not
just the Docker healthcheck) every 2 seconds for up to 30 attempts (60s),
comfortably inside the 120s subprocess timeout `run_checked` already
enforces around it. On final failure, it re-runs the checks one more time
outside the loop so the caller sees the actual failing assertion, not a
generic timeout.

## Recovery Performed

The stuck transaction (`update-20260801t102008z-30058fc5`) was cleanly
`discard`ed — the only valid transition from `recovery_required`. The
device returned to `installed_version: 0.1.0-preview.18`, `discarded`,
with no failed units and Pi-hole confirmed healthy throughout. No backup
or persistent data was at risk at any point; the failure happened before
any file replacement or service switch.

## Consequence for This Session's Qualification Plan

The already-built and published `v0.1.0-preview.19` (signed with a
disposable qualification key for this test) was built *before* this fix,
so its own bundled copy of `verify-update-health` still has the race.
Rather than patch a running device's active release out-of-band and leave
a mismatched, unrebuilt release published, a fresh version was rebuilt
and re-signed with the fix included, and the original `.19` throwaway
release was deleted. See the follow-up Console-triggered install
qualification report for that campaign's result.
