# External Recovery Backup/Restore Round Trip — Hardware Qualification Report

**Date:** 2026-08-08/09

## Purpose

Hardware-qualify [ADR-0011](../adrs/0011-external-recovery-image-path.md)'s
decision: that a backup taken off-device before a total device failure can
be restored, using the existing, unmodified `sovereign-update
backup`/`restore` commands, onto a device that has since been completely
reflashed. This was explicitly deferred out of scope when that ADR was
accepted — this report closes it.

## Starting state

The qualification Raspberry Pi 5, running `0.1.0-dev` (a manually-built
appliance version from this project's own RFC-0016 hardware work), on the
A/B layout, base-OS state `committed` at `0.1.0-proof.2`.

## Method

1. **Produced a real "verified" transaction to back up from.** The
   device's installed version (`0.1.0-dev`) falls outside the
   `source_versions` bounds of every real published release, so
   `sovereign-update check` reported `UNSUPPORTED_SOURCE` — there was no
   real release to `prepare` against. Built a custom, correctly-signed
   appliance update candidate via CI
   (`build-image.yml`, `version=0.1.0-preview.26`,
   `build_update_candidate=true`, `update_source_minimum=0.1.0-dev`,
   `update_key_id=sovereign-production-1`), signed offline with the
   production key per ADR-0006, transferred to the device, and ran
   `sovereign-update prepare` — reaching `{"status": "verified",
   "transaction_id": "update-20260808t060722z-85c461aa"}`.
2. **Took a real backup:** `sudo sovereign-update backup
   update-20260808t060722z-85c461aa` → `{"backup_id":
   "backup-20260808t060742z-35225d70", "status": "backed_up"}`.
3. **Copied the backup off-device**, exactly as ADR-0011 describes: the
   backup directory (`/data/sovereign/backups/<id>/`, root-owned 0700)
   was copied to the operator's home directory with ownership changed to
   `sovereign` so it could be `scp`'d off, landing in a location entirely
   outside the device — this project's assistant tooling, not the device
   itself.
4. **Built a real flashable A/B image to reflash with.** No CI artifact
   previously existed for this (the workflow only ever extracted
   partition images for base-OS candidates, never uploaded the full disk
   image) — added a new `Upload flashable A/B image artifact` step to
   `build-image.yml` (uploaded raw, not through
   `create-release-bundle.py`, which hardcodes plain-image assumptions
   that don't hold for the A/B config's differently-named output), then
   built `0.1.0-proof.3` with it.
5. **Reflashed the device**, physically, via Raspberry Pi Imager, by the
   device operator — genuinely destructive, wiping root and `/data`
   entirely. Confirmed post-flash: `{"active_slot": "system_a",
   "installed_base_os_version": "0.1.0-proof.3", "installed_version":
   "0.1.0-proof.3", "base_os_update_state": "idle", "update_state":
   "idle"}` — a clean, fully idle fresh-flash baseline. Notably,
   `installed_base_os_version` now genuinely reflects the real build
   version, live confirmation of the Finding-4 fix from the
   [second base-OS update qualification report](second-base-os-update-hardware-qualification-report.md).
6. **SSH access needed re-establishing**: the reflash used password
   authentication rather than the previously-trusted key, so the
   operator ran `ssh-copy-id` (entering the password locally, never
   through the assistant) to restore key-based access before privileged
   commands could resume.
7. **Copied the backup back onto the fresh device**, into
   `/data/sovereign/backups/backup-20260808t060742z-35225d70/`, restoring
   root ownership (0700 directory, 0600 files) to match exactly what
   `create_backup` itself would have produced.
8. **Ran restore:** `sudo sovereign-update restore
   backup-20260808t060742z-35225d70 --force`. `--force` was required and
   expected — the backup's `source.appliance_version` (`0.1.0-dev`)
   doesn't match the freshly-flashed device's (`0.1.0-proof.3`), exactly
   the real-world shape a genuine "reflash then restore" scenario
   produces. Result: `{"status": "committed", "backup_id":
   "backup-20260808t060742z-35225d70", "restore_id":
   "restore-20260809t094013z-938b517f"}`.
9. **Independently verified the actual restored content**, not just the
   reported status — extracted the original backup archives locally and
   computed SHA-256 for every file, then compared against `sha256sum` run
   directly on the live, restored device.

## Result

**Every persisted file matched exactly**, computed independently on both
sides rather than trusted from the tool's own report:

- `pihole-state` (Pi-hole's full `etc-pihole/` tree — `gravity.db`,
  `pihole.toml`, `dnsmasq.conf`, `custom.list`, TLS certificates, list
  caches, config backups): every file's checksum identical between the
  original off-device backup and the live restored device. The only
  differences were `cli_pw`, `pihole-FTL.db-wal`, and `pihole-FTL.db-shm`
  — Pi-hole's own runtime-generated files created fresh after the
  service restarted, never part of the backup and not expected to be.
- `secrets` (the Pi-hole admin password): exact checksum match,
  `8eabc6deb90632576c01d05677ea4a957fdb8a3e34fc8679c6b3c7ea6b8174ba`,
  verified without ever printing the actual secret value.
- `sovereign-configuration`: empty on both sides (the original device
  had never written anything there) — a clean, consistent no-op match
  rather than an untested path.
- **The actual service, not just files:** `sovereign-pihole.service`
  reported `active`, and a live DNS query against `127.0.0.1` through it
  returned real, correct results — confirming the restore produced a
  genuinely working device, not merely byte-identical files.

**ADR-0011's decision is confirmed correct exactly as designed, with zero
code changes to `backup`/`restore` needed.** The ADR's claim — that these
commands' validation is purely content/checksum-based with no
device-identity binding — held up under a real reflash, a real version
mismatch requiring `--force`, and a real service restart, not just under
source-reading analysis.

## Findings

No defects in `backup`/`restore` themselves surfaced — the round trip
worked cleanly on the first real attempt. Two adjacent, real gaps this
pass did surface and already fixed along the way (not left as findings):

- No CI artifact existed for the actual flashable A/B disk image, only
  extracted partition images — fixed by adding the `Upload flashable A/B
  image artifact` step (see commit history), now a reusable capability
  for any future A/B qualification work, not just this one.
- A reflash can silently change which SSH authentication method the
  device accepts (this pass's reflash ended up using password auth
  instead of the previously-trusted key) — an operational trap worth a
  one-line callout in whatever operator-facing recovery documentation
  eventually gets written for this procedure, so a real operator isn't
  confused mid-recovery.

## Cleanup

Nothing to revert — unlike some earlier qualification passes on this
device, this one's end state (freshly reflashed, then genuinely restored)
is not a throwaway test artifact but a real, intended device state. The
device now runs `0.1.0-proof.3` with the original Pi-hole configuration
and secrets from before the reflash, fully restored and healthy.

## Recommendation

- Update [ADR-0011](../adrs/0011-external-recovery-image-path.md)'s
  Status from "Accepted, not yet qualified" to fully qualified, linking
  this report.
- The deferred convenience-wrapper alternative in ADR-0011 (a
  `sovereign-update export-backup`/`import-backup` pair, or similar,
  instead of manual `scp`/`chown`/`chmod`) is now worth reconsidering
  with the real procedure's exact steps known precisely — this pass is
  the concrete basis for designing it, not a vague idea anymore.
- Worth writing real operator-facing documentation for this procedure in
  [update-recovery-and-compatibility.md](../operations/update-recovery-and-compatibility.md),
  replacing its current honest-but-discouraging "no tested path" language
  with the now-qualified one, including the SSH-auth-method callout
  above.
