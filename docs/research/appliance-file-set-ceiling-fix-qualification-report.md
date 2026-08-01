# Appliance File-Set Ceiling Fix — Hardware Qualification Report

**Date:** 2026-08-01

## Purpose

Verify the fix to the finding recorded in
[appliance-file-set-update-ceiling-finding.md](appliance-file-set-update-ceiling-finding.md)
against the exact real transaction it blocked, on physical Raspberry Pi 5
hardware — not a synthetic reproduction.

## The Fix

Two changes to
`image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/usr/sbin/sovereign-update`:

1. `validate_release_payload` now rejects only *missing* files the
   installed updater requires (`INCOMPLETE_RELEASE`), not files beyond
   what its static `RELEASE_FILES` allowlist recognizes. The mode check
   (`UNSAFE_RELEASE_MODE`) still applies to every file this updater does
   know about. This is safe because the inner, signed bundle manifest
   (`extract_bundle`) already independently verifies the digest of every
   file in the archive, known or not — the outer allowlist was a
   redundant appliance-semantic sanity check, not the integrity boundary.
2. `validate_appliance_configuration` now classifies each `appliance/bin/`
   script by its shebang line (`"python" in first_line` → compile-check,
   else → `sh -n`) instead of a hardcoded Python-script name set. A
   name-based allowlist has the identical self-update problem as (1): the
   installed updater can never have heard of a script a newer release
   introduces.

Both changes were driven by new tests in `tests/test_update_client.py`
(`test_stage_accepts_a_file_this_updater_does_not_recognize`,
`test_stage_classifies_an_unrecognized_python_script_by_shebang`, and
their negative counterparts confirming missing files and genuinely broken
scripts are still rejected).

## Method

1. Deployed the fixed `sovereign-update` script over the previously
   installed one (checksum recorded before/after: `f4f1f261...` →
   `27a4da7c...`). This is an intentional, permanent fix — left in place,
   not reverted, matching how the `proof-init` regression fix earlier
   this session was handled.
2. Retried `sovereign-update stage` against
   `update-20260801t072255z-bd4a4874` — the *exact* transaction that had
   been stuck at `backed_up` since the original `.18` install attempt
   documented in the finding, without redoing `prepare`/`backup`.
3. `stage` succeeded: `{"status": "staged", ...}`.
4. `activate` succeeded: `{"status": "committed", "version":
   "0.1.0-preview.18"}`.
5. Verified: no failed systemd units, `console-auth` genuinely present at
   `/opt/sovereign/current/appliance/bin/console-auth` (mode `0755`),
   Pi-hole container healthy, Console and health endpoints responding,
   DNS resolving.
6. Rebooted and re-verified all of the above held cold.

## Result

`v0.1.0-preview.18` — the first release ever to add a new appliance file
— is now genuinely installed via the real `prepare`/`backup`/`stage`/
`activate` path on physical hardware, confirmed persistent across a
reboot. The exact real stuck transaction from the original finding was
recovered, not abandoned.

## What This Does Not Fix

Console authentication is **still not runnable** on this device.
`systemctl status sovereign-console-auth.service` returns "Unit ... could
not be found" — confirmed both immediately after activation and again
after the reboot. This is expected and unchanged from the finding's
analysis: the systemd unit, the `sovereign-console` `sysusers.d` group
declaration, and the `/data/sovereign/console` bootstrap directory
creation are all base-image (rootfs overlay) content, not appliance-release
content — none of that is delivered by `sovereign-update` at all, by
design, regardless of the file-allowlist fix. Reaching a state where
Console auth actually works on an already-flashed device still requires
either a reflash or the "Full Base-OS Updates" milestone's still-undesigned
self-update mechanism (ROADMAP item 6) — this fix narrows one real gap
without touching that larger, already-tracked one.

## Recommendation

None further for this specific fix — it is validated and should be
considered closed. The base-image-content delivery gap remains exactly
where ROADMAP item 6 already placed it: an architecture decision pending,
not something this session should expand scope to solve.
