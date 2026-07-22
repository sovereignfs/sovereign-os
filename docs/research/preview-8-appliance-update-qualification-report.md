# Preview.8 Appliance Update Qualification Report

**Date:** 2026-07-23

**Hardware:** Raspberry Pi 5 Model B Rev 1.1, 16 GB RAM, 128 GB storage

**Base image:** Sovereign OS `0.1.0-preview.7`

**Update target:** Sovereign OS `0.1.0-preview.8`

**Source revision:** `00b96eace6f97b9cc74b1034d6974d8d2aadbf6a`

**Status:** Initial no-migration appliance update transaction qualified

## Candidate and Trust Verification

- Base and target workflow runs completed successfully from the same source
  revision.
- The preview.8 workflow ZIP passed archive integrity checks, and every clean
  image file matched its published `SHA256SUMS` entry.
- The update manifest correctly declared preview.7 as its minimum source,
  preview.8 as its target, Raspberry Pi 5 ARM64 compatibility, no migrations,
  rollback support, and the pinned Pi-hole digest.
- A temporary Ed25519 private key was generated only on the operator machine.
  The qualification-kit tool validated the update bundle, signed and verified
  the exact manifest bytes, and emitted only public trust files and signed
  inputs for transfer.
- Before public-key installation, the Pi rejected the signed candidate with
  `UNKNOWN_SIGNING_KEY`. After installation, non-mutating inspection returned
  `verified` with the expected source, target, channel, artifact, and rollback
  fields.
- The temporary public key and transferred kit were removed from the Pi after
  qualification. The temporary operator directory containing the private key
  was removed after evidence was recorded.

## Preview.7 Baseline

- `/opt/sovereign/current` resolved to preview.7 and the update state was idle.
- Console, health API, Pi-hole UI, TCP/UDP DNS, DATA storage, and local-access
  verification were healthy.
- Root, boot, and DATA mounted from their expected SD-card partitions.
- Nginx, Console, Pi-hole, local-access verification, and Docker were active;
  no systemd units were failed.
- Ports 22, 53, and 80 were reachable from the LAN. Ports 443, 8080, and 8090
  were not exposed.
- The Pi-hole administrator credential was recorded only as a root-readable,
  on-device continuity reference.

## Deterministic Reboot Recovery

Each interruption hook exited with status 75 only after its named state and
event were atomically persisted.

### `backing_up`

- The transaction stopped at journal sequence 3 with no backup ID and without
  switching the active release.
- On reboot, recovery marked the transaction `recovery_required`; preview.7,
  Pi-hole, Console, and TCP/UDP DNS recovered.
- Discard moved the transaction to `discarded` while retaining its journal and
  failure evidence.

### `activating`

- A quiesced backup completed, preview.8 staged, and activation stopped at
  journal sequence 6 before the service/pointer switch.
- On reboot, preview.7 remained active and the transaction became
  `recovery_required`.
- Pi-hole, Console, and TCP/UDP DNS recovered before the inactive preview.8
  payload was safely discarded.

### `validating`

- A fresh backup and stage completed. Preview.8 became the active pointer and
  Pi-hole started before activation stopped at journal sequence 7.
- The next boot restored preview.7 before Pi-hole readiness and marked the
  transaction `recovery_required`; recovery never inferred a commit.
- Console showed only the expected update-recovery degradation while storage,
  DNS, Pi-hole, and local access remained healthy.
- Safe discard removed the inactive preview.8 release and preserved the
  transaction and referenced backup.

## Forced Health Failure and Rollback

- A fresh preview.8 transaction completed backup and staging.
- The explicitly armed qualification hook failed only the target health
  decision with `POSTUPDATE_HEALTH_FAILED`.
- The updater stopped preview.8, restored preview.7, restarted Pi-hole, and ran
  the real rollback health checker.
- The transaction ended `rolled_back`, not `recovery_required`.
- Console reported `Latest update rolled back safely`; Pi-hole UI and TCP/UDP
  DNS were healthy.
- The inactive target was safely discarded before the final transaction.

## Successful Update and Reboot

- A final fresh transaction passed authenticated preparation, quiesced backup,
  safe staging, activation, and the complete local health gate.
- The transaction ended `committed` with no failure and
  `/opt/sovereign/current` pointing to preview.8.
- Its backup manifest contained the four required roles: Pi-hole state,
  Sovereign configuration, secrets, and release pointer. Each archive had a
  recorded size and SHA-256, and the manifest recorded a healthy quiesced
  restart.
- The Pi-hole administrator credential matched the on-device continuity
  reference both before and after the final reboot. The reference was then
  deleted.
- After reboot, the active appliance identity and updater reported preview.8
  and `committed`. `/etc/sovereign-release` remained preview.7, correctly
  identifying the underlying flashed image rather than the active appliance
  release.
- DATA remained mounted from `/dev/mmcblk0p3`; SSH-key access persisted.
- All core services settled at `active`, with no failed units.
- Console health reported preview.8 and all checks healthy. Root routing,
  `/dns/admin/`, reserved `/admin/` and `/api/`, TCP/UDP DNS, and LAN port
  isolation all passed.

## Observations and Remaining Work

- SSH and DNS become available before HTTP during boot. Console requests made
  during that window were refused and then recovered without intervention by
  approximately 50 seconds of uptime. Qualification tooling must wait for the
  application-readiness gate rather than treating network reachability as
  completion.
- A service snapshot taken before readiness showed Nginx/local-access inactive
  and Pi-hole activating even though the final settled state was fully active.
  This is expected ordering but should be made clearer to operators.
- On macOS, querying `@sovereign.local` may also attempt the advertised
  link-local IPv6 address and return a misleading nonzero exit after a valid
  IPv4 answer. Physical DNS qualification should use the explicit IPv4 address
  until IPv6 behavior is separately defined.
- Discard intentionally retains journals and referenced backups. Retention and
  cleanup policy still need a bounded implementation.
- This campaign qualified a Pi-hole-only, no-migration appliance update. It did
  not test persistent-data restore, an irreversible migration, base-OS package
  updates, or A/B root-filesystem updates.
- Production signing-key custody, rotation, and release-channel provisioning
  remain separate security decisions. No engineering trust key remains on the
  qualified Pi.

## Conclusion

The preview.7 to preview.8 campaign proves that Sovereign OS can authenticate,
back up, stage, activate, health-gate, roll back, recover after durable-boundary
interruptions, commit, and reboot an appliance update without reflashing or
changing Pi-hole credentials and persistent DATA. The initial no-migration
update transaction is qualified on Raspberry Pi 5 hardware. Restore automation,
retention policy, and production signing operations remain before declaring the
complete update foundation release-ready.
