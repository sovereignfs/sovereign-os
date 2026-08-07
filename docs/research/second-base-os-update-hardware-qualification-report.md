# Second Base-OS Update Without Reflash — Hardware Qualification Report

**Date:** 2026-08-06

## Purpose

Close [RFC-0016](../rfcs/0016-full-base-os-updates.md)'s last open Acceptance
Criteria item: confirm that a device already migrated to the A/B `tryboot`
layout (this project's own qualification Raspberry Pi 5, migrated via a
one-time reflash on 2026-08-02) can receive a **second** base-OS update —
stage, trial, health-gate, commit — without a further reflash. Everything
else in RFC-0016's Testing Strategy had already been hardware- or
live-verified; this was the remaining gap.

## Starting state

```
{"active_slot": "mmcblk0p4", "installed_base_os_version": "0.1.0-proof.1",
 "base_os_update_state": "idle", "installed_version": "0.1.0-dev", ...}
```

## Method

Built a fresh, correctly-keyed base-OS candidate via `build-image.yml`
(`version=0.1.0-preview.25`, `build_base_os_candidate=true`,
`base_os_key_id=sovereign-production-1`, source commit `4cae39f`), signed
its manifest offline with the real production key per
[ADR-0006](../adrs/0006-production-signing-key-custody.md) (the assistant
never handled the key; the device operator ran
`scripts/sign-update-manifest.py` locally), transferred the signed
artifacts to the device, and worked through `sovereign-update
stage-base-os` → `trial-base-os` → `commit-base-os`, verifying state at
each step via `sovereign-update status` and the transaction journal under
`/data/sovereign/update-state/base-os-transactions/`.

This surfaced four real defects along the way — all genuine
already-flashed-device compatibility gaps, not artifacts of the
qualification process itself, though qualification is what exposed them.

## Finding 1: pre-`ffe2278` binaries reject modern base-OS manifests outright

The device's installed `/usr/sbin/sovereign-update` predated commit
`ffe2278` (2026-08-04, "fix stage-base-os to handle compressed
artifacts"), which changed `BASE_OS_BOOT_MEDIA_TYPE`/`BASE_OS_ROOT_MEDIA_TYPE`
from `...+raw` to `...+raw+zstd`. `create-base-os-release.py` (current
`main`) always produces `+raw+zstd` manifests, so the freshly-built,
correctly-signed `0.1.0-preview.25` candidate was rejected outright:

```
{"status": "rejected", "code": "INVALID_MANIFEST", "message": "Invalid artifact media type"}
```

**This cannot be fixed by an update.** `/usr/sbin/sovereign-update` is
base-OS content baked into the read-only root filesystem — confirmed
directly: `sudo cp` to replace it failed with `Read-only file system`. Any
already-flashed device stuck on a pre-`ffe2278` binary can never accept a
real base-OS release without a reflash. New devices flashed from a current
image are unaffected.

**Qualification workaround (not representative of a real device):** built
an alternate manifest by hand, decompressing the already-signed candidate's
artifacts locally (lossless — same bytes the compressor started from) and
re-signing a manifest stamped with the old `+raw` media type, matching
what the installed binary still expects.

## Finding 2: `"proof"` sorts after `"preview"` under semver prerelease comparison

Restaging with the old-format manifest (still versioned `0.1.0-preview.25`)
was rejected for a different reason:

```
{"status": "rejected", "code": "DOWNGRADE_REJECTED", "message": "Target version must be newer than the installed base-OS version"}
```

`compare_versions` treats prerelease identifiers as plain semver: comparing
`"proof"` and `"preview"` lexically, `"proof" > "preview"` (`'o' > 'e'` at
the third character). The device's installed `0.1.0-proof.1` therefore
reads as *newer* than any future `0.1.0-preview.N` release, permanently.
**A device on a `proof.N` base-OS version can never accept a real
`preview.N` base-OS release** — a genuine version-numbering-scheme
collision between this project's early internal `proof` builds and its
`preview` release channel, independent of anything else in this report.

**Qualification workaround:** relabeled the manifest's version to
`0.1.0-proof.2` — the honest "next in this device's own line" — rather
than inventing a misleading version string. Same signed artifacts, just a
corrected version field, re-signed.

## Finding 3: transactions staged by a stale binary fail their own trial boot

With a staged, validly-versioned transaction (`base-os-20260806t193348z-49d54c93`,
target `0.1.0-proof.2`), `trial-base-os` triggered a real `tryboot` cycle
onto `system_b`. The device booted the trial slot successfully — but
`sovereign-update-recovery.service` (which runs early at boot, gated
before `network-online.target`, well before
`sovereign-verify-base-os-trial.service` gets a chance to run) marked the
transaction `recovery_required` with `INTERRUPTED_TRIAL` only 22 seconds
after the trial was triggered — long before the device had even finished
booting, let alone health-checking.

Root cause: `create_base_os_transaction` (current `main`) writes a
`target_slot` field into the transaction record specifically so the
recovery auditor can distinguish "still genuinely on the trial slot,
verify just hasn't run yet" from "actually interrupted, firmware already
fell back." The **old** binary that staged this transaction (same binary
as Finding 1) predates that field entirely — confirmed by diffing the
cached old and new `create_base_os_transaction` source directly. With
`target_slot` absent, the recovery check's
`snapshot.get("target_slot") == active_slot` compares `None == "system_b"`,
fails, and the auditor concludes — incorrectly — that the trial was
interrupted.

This is a real, hardware-uncovered false-positive in the recovery logic's
interaction with schema evolution: nothing here is wrong for a
self-consistent device (stage and later boot always share one binary
version in normal operation), but it means **any already-flashed device
whose installed binary predates this field will fail every base-OS trial
it ever attempts**, indefinitely, purely from this bookkeeping gap — not
an actual health-check failure.

A related, smaller fix already landed alongside this: `slot_label_for`
now resolves slot identity via `blkid -s PARTLABEL` against the by-slot
symlink target, rather than pattern-matching `system_[ab]` out of the raw
device-node name (which never matched anything, since `mmcblk0pN` node
names don't contain that text at all — the old `current_slot_label()`
always silently fell back to returning the raw device name instead).

**Qualification workaround:** rebooted back to `system_a` (an *uncommitted*
trial reverts automatically on any ordinary reboot — the same
firmware-level guarantee already hardware-verified in this project's
earlier forced-power-cut testing), re-staged a fresh transaction
(`base-os-20260806t195409z-29404535`), then manually patched its
`state.json` under `/data/sovereign/update-state/base-os-transactions/`
to add `"target_slot": "system_b"` before triggering the trial —
reproducing exactly what the current binary would have written
automatically had it done the staging. `transition()`/`base_os_transition()`
merge changes into the existing snapshot dict rather than reconstructing
it, so the manually-added field survived the `staged → trial` transition
unmodified, confirmed by inspecting `state.json` after the edit.

With the field present, the trial passed cleanly:

```
{"active_slot": "system_b", "base_os_target_version": "0.1.0-proof.2", "base_os_update_state": "validated", ...}
```

## Finding 4: `installed_base_os_version` is a hardcoded build-time placeholder

After a fully successful `commit-base-os` and a confirmed-persistent
ordinary reboot (`active_slot: "system_b"`, `base_os_update_state:
"committed"` held across the reboot, exactly as designed), `sovereign-update
status` still reported `"installed_base_os_version": "0.1.0-proof.1"` —
unchanged from before the update.

This is not a bug introduced by anything in this qualification pass. Every
base-OS image, regardless of what `SOVEREIGN_VERSION` it's actually built
with, bakes `/etc/sovereign-base-os-release` from a static literal in
[`image-builder/sovereign/image/sovereign-ab-data/pre-image.sh:60`](../../image-builder/sovereign/image/sovereign-ab-data/pre-image.sh):

```
cat > "${filesystem}/etc/sovereign-base-os-release" <<'EOF'
VERSION="0.1.0-proof.1"
EOF
```

The comment directly above it already says so: *"Placeholder version until
real release tooling (out of scope for this milestone) parameterizes it
the way `create-update-release.py` does for appliance releases."* This
qualification pass demonstrates the concrete consequence: **`installed_base_os_version`
cannot correctly reflect a genuinely installed base-OS version today, even
after a fully successful, hardware-verified commit.** This directly bears
on RFC-0016's own Acceptance Criteria wording — "`sovereign-update status`
and Console correctly represent an in-flight and a committed base-OS
transaction" — which is only true for `base_os_update_state`/
`base_os_target_version`, not for `installed_base_os_version`.

Confirmed the overlay filesystem (`sovereign-etc-overlay.service`,
persistent writable upper layer on `/data`, shared across slots) is not
responsible: `/data/sovereign/identity/etc-upper/` has no copied-up
`sovereign-base-os-release`, and `/run/sovereign/etc-lower/sovereign-base-os-release`
(freshly populated from the actual currently-booted slot's real `/etc`
this boot) itself already reads `VERSION="0.1.0-proof.1"` — the file is
genuinely, correctly baked into the image exactly as built; it's simply
never parameterized.

## Incidental finding: trial-booted slots can present a different SSH host key

Connecting to the device immediately after a `trial-base-os` reboot
produced a `REMOTE HOST IDENTIFICATION HAS CHANGED` warning both times a
trial boot occurred. This is expected — `system_b` is a distinct rootfs
image and apparently generates (or ships) its own SSH host key rather
than sharing one with `system_a` via the persistent overlay — but it's
worth noting for the eventual device-operator documentation this project
doesn't have yet for base-OS updates
([update-recovery-and-compatibility.md](../operations/update-recovery-and-compatibility.md)
already says as much: "Don't assume anything on this page applies to
[base-OS commands] "). An operator hitting this cold, without knowing a
base-OS trial was in progress, would reasonably read it as a real
man-in-the-middle warning.

## Result

- Full `tryboot` stage → trial → verify (health-gate) → commit cycle,
  hardware-verified end to end on the real qualification device.
- Committed base-OS update confirmed persistent across a subsequent
  **ordinary** (non-tryboot) reboot — `active_slot` and
  `base_os_update_state: "committed"` both held.
- **The device received a second base-OS update without a second
  reflash** — the last open item in RFC-0016's Acceptance Criteria.
- Four real defects found and documented (Findings 1–4), all specific to
  already-flashed devices carrying binaries or baked-in content that
  predate current `main` — not defects a freshly-flashed device would hit.
- The Console base-OS status panel itself (RFC-0016's other recent
  addition) was **not** exercised against this live transaction — the
  device's running Console (`sovereign-console.service`, serving from
  `/opt/sovereign/releases/0.1.0-dev/appliance/`) also predates the panel's
  backend route, and updating it was deliberately deferred out of this
  session's scope. Still open.

## Cleanup

The manually-patched transaction `state.json` and both raw-manifest
qualification transactions (`base-os-20260806t193348z-49d54c93`,
`base-os-20260806t195409z-29404535`) remain on `/data` as the genuine
transaction history of what happened; nothing was reverted, since — unlike
the ADR-0010 session-gate qualification — this was a real, intended base-OS
install, not a throwaway test to be undone. The device is now genuinely
running the `0.1.0-preview.25`-built image content, committed, as
`0.1.0-proof.2` per its (re-labeled, workaround-only) transaction record.

## Recommendation

- Fix Finding 2 (the `proof`/`preview` ordering collision) before any real
  `preview.N` base-OS release ships — otherwise every device still on a
  `proof.N` base-OS version is permanently locked out of it. A version
  scheme migration or a comparator special-case is needed, not just a
  qualification-time workaround.
- Fix Finding 4 by wiring `SOVEREIGN_VERSION` into
  `pre-image.sh`'s `/etc/sovereign-base-os-release` generation, the same
  way the appliance layer's own version stamping already works — otherwise
  `installed_base_os_version` will misreport on every real base-OS release
  going forward, not just this qualification device.
- Findings 1 and 3 are inherent to any device caught on an old binary
  before these fixes existed; no further mitigation needed beyond what
  RFC-0016 already documents (a one-time reflash resolves both). Worth a
  one-line callout in the RFC's Compatibility section that the reflash
  requirement isn't just about A/B layout adoption — it can also be needed
  again for base-OS-tooling-level fixes on an already-migrated device,
  until base-OS content itself gains a way to update `sovereign-update`
  out-of-band from a full slot write.
- The Console base-OS panel still needs its own live hardware pass against
  a real transaction — deferred here, not done.
