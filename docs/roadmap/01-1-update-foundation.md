# Milestone 01.1 - Appliance Update Foundation

**Status:** Versioned appliance transaction implemented; Raspberry Pi qualification and restore automation pending
**Priority:** Immediate next priority after Phase 01 release  
**Depends on:** [Phase 01 Flashable Pi-hole Image POC](01-preview-poc.md)  
**Owner:** Project creator  
**Related decision:** [ADR-0002](../adrs/0002-install-images-and-update-artifacts.md)

## 1. Objective

Allow an installed Sovereign Pi-hole appliance to receive authenticated Pi-hole and appliance updates without reflashing or erasing its persistent data.

The downloadable disk image remains the clean-install and recovery artifact. Existing devices receive a separate signed update artifact.

## 2. User Promise

```text
Check for update
    -> review version and release notes
    -> install signed update
    -> preserve Pi-hole data and credentials
    -> verify DNS and web health
    -> continue on the new release
```

If validation fails, the updater restores the previous appliance version automatically or gives the user a documented recovery path without silently deleting data.

## 3. Scope

- Versioned appliance releases
- Signed release manifest and update artifact
- Hardware and current-version compatibility checks
- Pi-hole container update by immutable digest
- Versioned Compose, Nginx, systemd, and appliance configuration
- Persistent Pi-hole data outside replaceable release directories
- Pre-update backup and restore
- Staged installation rather than in-place file mutation
- DNS and HTTP health checks
- Automatic application-level rollback
- Update journal and diagnostic status
- Manual command-line update flow
- Stable and preview channel data model, with one channel sufficient initially
- Documentation for update, rollback, recovery, and data compatibility

## 4. Non-Scope

- Unattended automatic installation of updates
- Fleet management or remote device control
- Mandatory accounts or cloud service
- Delta binary patches
- General plugin update marketplace
- Full A/B root-filesystem update implementation
- Guaranteed rollback across incompatible Pi-hole data migrations
- Automatic major Raspberry Pi OS distribution upgrades
- Public update UI in the Sovereign dashboard

## 5. Update Domains

The project must version and update three domains independently:

| Domain | Examples | Initial mechanism |
| --- | --- | --- |
| Application | Pi-hole container | Pinned OCI image plus persistent data |
| Appliance | Compose, Nginx, systemd, updater, diagnostics | Signed versioned release bundle |
| Base OS | Kernel, firmware, Debian packages, Docker | Controlled documented system update; A/B later |

A release image may contain newer versions of all three domains. That does not mean an existing installation must rewrite its storage with that image.

## 6. Required Phase 01 Groundwork

Phase 01 must establish these foundations even though it does not implement the updater:

- A dedicated persistent data partition mounted at `/data`.
- All Pi-hole data and device secrets under `/data/sovereign/`.
- Replaceable appliance files kept outside persistent data.
- Component and image version metadata readable on the device.
- Pi-hole container pinned by digest.
- Health checks usable by both release testing and the future updater.
- No dependency on mutable container tags.

This is necessary because separating data after users have installed the POC would require a riskier migration.

## 7. Proposed Persistent Layout

```text
/data/sovereign/
├── apps/
│   └── pihole/
│       └── etc-pihole/
├── secrets/
│   └── pihole-admin-password
├── backups/
├── configuration/
└── update-state/

/opt/sovereign/
├── releases/
│   ├── 0.1.0/
│   └── 0.2.0/
└── current -> releases/0.2.0
```

Docker runtime state is replaceable and is not the authoritative backup for Pi-hole data.

## 8. Update Artifact

A release intended for installed devices should contain:

```text
sovereign-update-<version>/
├── manifest.json
├── manifest.sig
├── appliance/
│   ├── compose.yaml
│   ├── nginx.conf
│   ├── systemd/
│   └── scripts/
├── images/
│   └── pihole-arm64.oci
├── migrations/
├── health-checks/
└── release-notes.md
```

The exact packaging format remains subject to RFC review. The manifest must identify compatibility, versions, digests, required storage, migrations, reboot requirements, and rollback limitations.

The packaging question is now resolved by update bundle v1: a deterministic
Zstandard-compressed tar with one `sovereign-update-v1/` root, a closed inner
file manifest, regular files only, normalized modes, and per-file SHA-256
digests. The signed outer manifest still authenticates the complete compressed
artifact.

## 9. Update Transaction

```text
Discover release
    -> download to staging
    -> verify signature and checksums
    -> validate hardware/version compatibility
    -> verify free storage
    -> create backup
    -> install new versioned release directory
    -> import and verify container image
    -> validate Compose and Nginx configuration
    -> stop affected services
    -> switch current release
    -> start services
    -> test DNS and /dns/admin/
       ├── healthy: commit and retain bounded rollback assets
       └── unhealthy: restore previous release and data when required
```

Every step must be journaled so interruption can be distinguished from a completed or rolled-back update.

## 10. Initial User Interface

The first supported interface may be command-line only:

```text
sovereign-update status
sovereign-update check
sovereign-update install <version>
sovereign-update rollback
sovereign-update history
```

Commands that mutate state require appropriate administrator privilege. The updater must present the version, channel, required reboot, backup status, and known rollback limitations before installation.

## 11. Milestones

### U1 - Update Format and Trust

- Manifest schema defined: v1 JSON Schema and example committed
- Signing and verification format defined: detached Ed25519 over exact bytes;
  production key custody remains pending
- Compatibility and version rules defined
- Test signing key workflow established without exposing production keys

The backup manifest and durable transaction-state schemas are also defined.
Implementation and real-device restore validation remain part of U2-U5.

**Implementation status:** The installed `sovereign-update inspect` verifier
now enforces exact-byte Ed25519 signatures, local key/channel/revocation trust,
manifest structure, compatibility, downgrade, free-space, and bundle digest
rules without mutating the appliance. Production preview-key provisioning is
still blocked on the documented key-custody decision.

Authenticated local inputs can also be durably prepared under an exclusive
lock. The updater records atomic, fsynced transaction snapshots and append-only
events through the `verified` state, while deliberately performing no archive
extraction or service mutation yet.

The quiesced pre-update backup is now implemented. Four root-only archive roles
are generated and validated, Pi-hole downtime is bounded to archive creation,
and local DNS/HTTP health must recover before the transaction can become
`backed_up`.

Pi-hole-only versioned activation was implemented first: safe bundle extraction,
immutable release metadata, pinned OCI import, atomic active-release switching,
local DNS/HTTP validation, health-gated commit, and automatic release-pointer
rollback. Data migrations remain rejected, and real-device backup/rollback
qualification passed for preview.7 to preview.8. Persistent-data restore,
retention cleanup, and production signing operations are still pending.

The accepted
[versioned appliance release design](../design/versioned-appliance-release.md)
is now implemented. Full-image and update packaging share a closed canonical
tree for Console, Nginx, Compose, lifecycle, and health files. Stable services
dispatch through the atomic active-release pointer. Staging rejects missing,
extra, unsafe-mode, malformed, externally hosted, or invalid Compose/Nginx
payloads before service interruption. Activation and rollback coordinate
Pi-hole, Console, Nginx, and local-access verification as one release.

The immediate qualification boundary is a clean preview.9 base and preview.10
update built from the same revision. The target must visibly change the
build-rendered Console release marker, survive reboot, retain credentials and
DATA, and restore preview.9 after an injected target-health failure and an
interruption at `validating`. After that evidence is recorded, the next bounded
implementation slice is persistent-data restore and backup retention policy.

Repeatable hardware qualification tooling is also implemented: exact-byte
offline kit preparation, explicitly armed interruption hooks at the durable
`backing_up`, `activating`, and `validating` boundaries, and safe cleanup of
inactive failed targets without deleting their journals or referenced backups.
These paths passed Raspberry Pi 5 qualification in the preview.7 to preview.8
campaign.

Because the initial slice rejects all data migrations, automatic rollback does
not restore persistent data that the updater never modifies. The pre-update
backup remains the recovery boundary, but a general data-restore command is not
enabled until archive and restore behavior are qualified against real Pi-hole
state on the Raspberry Pi.

### U2 - Persistent Data and Versioned Releases

- Pi-hole state confirmed under `/data`
- Appliance files installed in versioned directories
- `current` activation mechanism implemented atomically
- Installed component versions are queryable

### U3 - Pi-hole Application Update

- New pinned Pi-hole artifact imports successfully
- Pre-update backup completes
- Container is recreated against persistent data
- DNS and HTTP health checks gate success
- Previous application version can be restored when data compatibility permits

### U4 - Appliance Update

- Compose, Nginx, systemd, scripts, and health checks update as one staged release
- Invalid configuration is rejected before activation
- Interrupted update resumes or rolls back safely
- Update journal and diagnostics are usable

### U5 - Recovery and Release Readiness

- Update and rollback checklist passes on real hardware
- Failure injection tests pass
- Recovery instructions are verified
- A release image and update artifact built from the same source describe consistent component versions

## 12. Acceptance Criteria

- A Phase 01 installation upgrades without reflashing storage.
- Pi-hole configuration, password, and relevant data remain intact.
- The update artifact and manifest are authenticated before mutation.
- Incompatible device, version, or artifact is rejected safely.
- Insufficient disk space is detected before installation.
- A usable pre-update backup is created.
- New files are staged outside the active release.
- Pi-hole image digest is verified before activation.
- Compose and Nginx validation runs before service interruption.
- TCP/UDP DNS and `/dns/admin/` health checks gate commit.
- A failed health check returns to the previous appliance release automatically.
- Interrupted updates produce a recoverable, diagnosable state.
- Update history identifies installed, failed, committed, and rolled-back versions.
- Update documentation clearly separates application, appliance, base-OS, and full-image updates.

## 13. Later A/B OS Update Direction

Full operating-system updates should eventually use redundant root filesystems and persistent data:

```text
boot
root A
root B
data
```

The inactive root is written and verified, selected for a trial boot, and committed only after health checks. Failure selects the previous root. RAUC, Mender, Raspberry Pi `tryboot`, and equivalent approaches require research before selection.

This milestone designs the application/appliance updater so it does not prevent that future architecture. It does not implement A/B updates.

## 14. Open Questions

- Exact update artifact format
- Signing-key custody, rotation, and revocation publication
- Release distribution host
- Stable and preview channel semantics
- Backup format and retention
- Pi-hole migration compatibility rules
- Rollback behavior after irreversible data migrations
- Maximum retained release count
- Whether application artifacts are embedded or separately addressed by digest
- Base-OS security update policy
- A/B framework and Raspberry Pi boot integration

## 15. Immediate Actions After Phase 01

1. Validate the persistent partition and backup behavior on the released image.
2. Approve the update RFC and manifest schema.
3. Implement signed manifest verification before download/install automation.
4. Deliver a Pi-hole-only update transaction.
5. Qualify versioned appliance-file activation and rollback on Raspberry Pi.
6. Implement and qualify persistent-data restore and bounded backup retention.
