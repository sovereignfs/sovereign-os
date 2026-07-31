# First Production-Signed Release Install Qualification Report

**Date:** 2026-07-31

## Purpose

Close the gap flagged in the
[first production-signed release qualification report](first-production-signed-release-qualification-report.md):
`v0.1.0-preview.17` had only ever been *discovered* by `sovereign-update
check`, never actually installed. This campaign runs the real
`prepare`/`backup`/`stage`/`activate` sequence against it on physical
Raspberry Pi 5 hardware — the first time any device has installed a
release signed with the production key
(`sovereign-production-1`, see
[ADR-0006](../adrs/0006-production-signing-key-custody.md)).

## Method

Starting state: device running the real, previously installed
`0.1.0-preview.14`, `update_state: committed`, empty trust store.

1. Downloaded the full `v0.1.0-preview.17` release (image bundle,
   `release-manifest.json`, `release-manifest.sig`, update bundle) and
   verified `SHA256SUMS` locally.
2. Transferred `release-manifest.json`, `release-manifest.sig`, the
   42.6 MB update bundle, and the `sovereign-production-1` public
   key/metadata to the device; verified the bundle's SHA-256 matched
   exactly after transfer.
3. Installed `sovereign-production-1.pem`/`.json` into
   `/etc/sovereign/update-trust.d/` **permanently** this time (not the
   temporary discovery-only install used in the prior report).
4. `sovereign-update prepare --manifest ... --signature ... --artifact
   ...` → `verified`, transaction `update-20260731t210626z-ac5a7163`.
5. `sovereign-update backup update-20260731t210626z-ac5a7163` → Pi-hole
   quiesced and restarted, health passed, `backed_up`, backup
   `backup-20260731t210635z-c3b3426e`.
6. `sovereign-update stage update-20260731t210626z-ac5a7163` → bundle
   extracted to `/opt/sovereign/releases/0.1.0-preview.17`, `staged`.
7. `sovereign-update activate update-20260731t210626z-ac5a7163` →
   atomic release-pointer switch, full local health gate,
   **`committed`**. `installed_version` and `target_version` both
   `0.1.0-preview.17`.
8. Verified: no failed systemd units, Console responding, Pi-hole
   container healthy, DNS resolving via `127.0.0.1`.
9. Rebooted to check persistence.

## A real regression found on reboot

After the reboot in step 9, `systemctl --failed` was **not** empty:
`sovereign-proof.service` had failed. Everything else — Pi-hole,
Console, DNS, `sovereign-update status` — was healthy; this was purely a
health-signal regression, not a functional outage, but a real one.

Root cause: `proof-init`
(`image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/usr/lib/sovereign/proof-init`)
unconditionally re-validated
`/opt/sovereign/releases/<version>/appliance/...` on *every* boot, where
`<version>` came from the **static, image-baked** `/etc/sovereign-release`
(still `0.1.0-preview.13` — the device's original flashed base image;
in-place updates never touch this file). That release directory had
been correctly deleted by the real `sovereign-update prune` hardware
qualification earlier in this session, since `0.1.0-preview.13` was
neither the active release nor referenced by any non-terminal
transaction. This reboot was the first one since that prune ran, so the
bug had been latent until now — exactly the kind of interaction between
two independently-correct features (retention policy; boot-time
validation) that only real, sequenced hardware use surfaces.

`sh -x` on the failing script confirmed the exact failure point:
`test -d /opt/sovereign/releases/0.1.0-preview.13/appliance` — directory
gone.

### Fix

The release-directory validation only ever needed to run once, at first
boot, before `/opt/sovereign/current` exists — it exists to catch a
malformed base image before bootstrapping the initial symlink. Once
`/opt/sovereign/current` is a real symlink (true for the rest of the
device's life, including after every subsequent in-place update), this
check has nothing left to protect and only creates a false dependency on
a release directory retention is explicitly designed to prune. Moved the
whole validation block inside the pre-existing `if [ ! -L
/opt/sovereign/current ]` bootstrap guard, so it no longer runs — or
depends on the base image's release directory still existing — after the
device has bootstrapped once.

Deployed the fix to the device (checksum-verified before/after), reset
and restarted the unit (`exit 0`, "Finished"), then **rebooted a second
time** to confirm the fix holds cold rather than only after a manual
restart. `systemctl --failed` was empty; `sovereign-proof.service` was
`active (exited)`.

## Result

- `v0.1.0-preview.17` is genuinely installed and committed on the real
  device — the first release signed with the production key to actually
  be installed, not merely discovered.
- A real, previously-unknown regression (`sovereign-proof.service`
  failing on any boot after a pruned base-image release) was found only
  because this was a real hardware sequence — build, install, prune
  (earlier in this session), then a genuine reboot — not something code
  review or the unit-test suite would have caught, since no test exercises
  boot-time systemd unit ordering against a post-prune filesystem state.
  Fixed and re-verified across a second, cold reboot.

## Recommendation

- `restore`, `prune`, and `rotate-trust` still have not been exercised
  as part of an actual signed-release *install* — this campaign only
  exercised `prepare`/`backup`/`stage`/`activate`, since
  `0.1.0-preview.17` shares its source revision with `0.1.0-preview.14`
  (no data migration, no retention pass, no trust rotation was part of
  this particular transaction). A future release that legitimately
  changes source content would be a better vehicle for qualifying those
  together with a real production-signed install.
- This is a second data point (after the `release-manifest.json`
  collision) that this project's boot/update/retention interactions
  benefit from being exercised as real sequences on real hardware, not
  just unit-tested in isolation.
