# RFC-0014: Appliance Update System

**Status:** Draft  
**Author:** Project creator and Codex  
**Created:** 2026-07-19  
**Target:** Milestone 01.1  
**Related decision:** [ADR-0002](../adrs/0002-install-images-and-update-artifacts.md)

## Summary

Introduce a signed, user-triggered update mechanism for installed Sovereign appliances. It updates pinned application containers and versioned appliance files while preserving `/data/sovereign`, validating health, and restoring the previous release after failure where data compatibility permits.

## Problem

Publishing a new disk image does not provide a safe update path for an installed device. Rewriting the image erases the installation, while ad hoc `apt`, file-copy, or `docker pull latest` operations are neither reproducible nor safely reversible.

## Goals

- Preserve Pi-hole configuration, credentials, and data.
- Authenticate update metadata and payloads.
- Reject incompatible hardware and versions.
- Stage releases separately from the running version.
- Back up before mutation.
- Update a pinned Pi-hole container by digest.
- Update appliance configuration as one versioned unit.
- Gate commit on DNS and HTTP health checks.
- Roll back automatically when safe.
- Recover predictably after interruption.
- Maintain local update history without mandatory telemetry.

## Non-Goals

- A/B root filesystem implementation
- Fleet orchestration
- Silent unattended updates
- Binary delta generation
- Generic third-party plugin updates
- Cross-distribution package management
- Guaranteed rollback after irreversible migrations

## Release Model

One source release may produce:

```text
sovereign-os-<version>-rpi5-arm64.img.zst
                                        clean install and recovery
sovereign-update-<version>.tar.zst   installed device update
release-manifest.json                published release metadata
release-manifest.sig                 signature
SHA256SUMS                           transport integrity
release-notes.md                     human-readable changes
```

Image and update artifacts must be produced from the same component-version manifest.

## Component Version Model

The device records:

- appliance version;
- image/base version;
- Pi-hole version and digest;
- schema/migration version;
- device compatibility identifier;
- update channel;
- active and previous release;
- last update transaction state.

## Manifest Requirements

The normative v1 contract is the JSON Schema at
[`update/schema/sovereign-update-manifest-v1.schema.json`](../../update/schema/sovereign-update-manifest-v1.schema.json),
with a complete non-release fixture in
[`update/examples/update-manifest-v1.example.json`](../../update/examples/update-manifest-v1.example.json).

The signed manifest must include:

- release identifier and semantic/project version;
- publication time;
- channel;
- compatible device identifiers;
- minimum and maximum source versions where needed;
- artifact URLs, sizes, and cryptographic digests;
- component versions and OCI digests;
- required free storage;
- required reboot;
- migration identifiers;
- rollback limitations;
- release notes reference;
- signature/key identifier.

Signatures establish publisher authenticity. Per-file cryptographic digests establish payload integrity.

## Signature Format and Key Management

Manifest v1 uses Ed25519. The publisher signs the exact UTF-8 bytes of
`release-manifest.json`, including its final newline. There is no JSON
reserialization or canonicalization during verification. The detached
`release-manifest.sig` is the base64 encoding of the raw 64-byte signature.

The untrusted manifest's `signing.key_id` selects a public key from the
device's preinstalled trust store. Selection does not confer trust. The client
must reject an unknown, wrong-channel, expired, or revoked key before using any
manifest URL or compatibility claim.

- The device image contains only trusted public verification keys.
- Private release keys are stored outside source control and build images.
- CI should request signing from a restricted mechanism rather than receive a long-lived unrestricted key where practical.
- The format must support key rotation and revocation.
- Development/test keys must not be trusted by production-channel devices.

Production private-key custody and CI signing integration remain unresolved.

## Persistent and Replaceable State

Persistent:

```text
/data/sovereign/apps/
/data/sovereign/secrets/
/data/sovereign/configuration/
/data/sovereign/backups/
/data/sovereign/update-state/
```

Replaceable/versioned:

```text
/opt/sovereign/releases/<version>/
/opt/sovereign/current
```

Host-generated runtime state such as Docker layers is replaceable unless a specific recovery requirement says otherwise.

## Transaction State Machine

```text
available
  -> downloading
  -> verified
  -> backed_up
  -> staged
  -> activating
  -> validating
     ├── committed
     └── rolling_back -> rolled_back | recovery_required
```

Transitions are recorded durably. An interrupted updater examines the journal and continues, rolls back, or stops with an actionable recovery state. It must never infer success solely because a process exited.

The normative snapshot schema is
[`update/schema/transaction-state-v1.schema.json`](../../update/schema/transaction-state-v1.schema.json).
Each transition atomically replaces and fsyncs `state.json`, increments its
sequence, and appends a non-secret event to `events.jsonl`. The complete
durability and restart rules are defined in the
[backup and journal contract](../../update/BACKUP_AND_JOURNAL.md).

## Installation Sequence

1. Acquire a single update lock.
2. Refresh and verify signed release metadata.
3. Confirm channel, device, version, and migration compatibility.
4. Confirm disk space and system health.
5. Download payloads into a staging directory.
6. Verify all digests before privileged mutation.
7. Briefly quiesce Pi-hole, create and validate a pre-update backup, restart
   Pi-hole, and require DNS/HTTP health before continuing.
8. Install appliance files into a new version directory.
9. Import the pinned Pi-hole OCI image and verify its digest.
10. Validate Compose, Nginx, and systemd content offline.
11. Stop only affected services.
12. Apply reversible migrations.
13. Atomically switch the active-release reference.
14. Start services in dependency order.
15. Test TCP DNS, UDP DNS, `/dns/admin/`, and required API behavior.
16. Commit or roll back.
17. Retain bounded history and remove safe-to-delete staging data.

## Backup and Migration

Before activation, the updater backs up:

- Pi-hole persistent configuration and database required for restore;
- Sovereign configuration;
- update metadata;
- previous appliance release reference.

Backups must be validated enough to detect missing or unreadable content. Migration scripts declare whether they are reversible. If a migration is irreversible, the updater must clearly state that application rollback may require restoring the backup and must test that path before supporting the release.

The normative backup metadata schema is
[`update/schema/backup-manifest-v1.schema.json`](../../update/schema/backup-manifest-v1.schema.json).
The initial consistency method stops Pi-hole while its authoritative state is
archived, then restarts and health-checks it before the update proceeds. Four
separate, mandatory payloads cover Pi-hole state, Sovereign configuration,
secrets, and the previous release pointer. Runtime container storage, logs,
staging data, and earlier backups are excluded.

Backup archives and manifests are root-only. Digests, sizes, role completeness,
permissions, and safe archive listings must validate before `backed_up` can be
recorded. Restore extracts into staging, validates again, preserves the old
copy until health checks pass, and never deletes both the old and candidate
trees on failure. See the
[backup and journal contract](../../update/BACKUP_AND_JOURNAL.md).

## Health and Commit

Minimum commit gates:

- Pi-hole container running;
- TCP DNS query succeeds;
- UDP DNS query succeeds;
- upstream resolution succeeds when internet is available;
- known blocked-domain behavior succeeds under controlled test data where practical;
- Nginx configuration is valid;
- `/dns/admin/` returns the expected application response;
- `/dns/api/` authentication behavior is sane;
- `/admin/*` and `/api/*` remain outside Pi-hole;
- persistent data is mounted from `/data`.

Internet-independent checks must be separated from upstream-connectivity checks so an internet outage does not incorrectly classify a locally healthy update as corrupt.

## Rollback

Rollback restores:

- previous active-release reference;
- previous Pi-hole container digest;
- previous configuration;
- persistent data from backup when the migration requires it.

Rollback itself is health checked and journaled. If rollback fails, DNS recovery instructions must remain available locally.

## Base-OS Updates

This RFC does not make package-manager updates atomic. Base-OS security updates use a separately controlled procedure until an A/B system is selected.

The updater may report base-OS update status, but it must not represent an `apt` transaction as equivalent to a rollback-capable appliance update.

## Distribution

The update client fetches metadata and artifacts over HTTPS from a configurable release origin. Authenticity does not depend solely on TLS; signed metadata is mandatory.

No device account, telemetry, or inbound connection is required. Update checks are client-initiated.

## Security and Privacy

- Verify signatures before trusting compatibility or URLs.
- Verify digests before installation.
- Treat archives and migration scripts as hostile until authenticated.
- Prevent archive path traversal and unsafe ownership/modes.
- Do not send device data beyond the minimum update request.
- Do not expose Pi-hole data in update logs.
- Restrict updater state and backups.
- Protect against downgrade unless explicitly authorized for recovery.
- Bound download, staging, backup, and log storage.

## Testing Strategy

- Signature, wrong-key, revoked-key, and tampered-manifest tests
- Truncated and corrupted download tests
- Compatibility and downgrade rejection
- Insufficient-storage handling
- Concurrent update lock
- Power loss at every state transition
- Invalid Compose/Nginx/systemd payloads
- Container import and digest mismatch
- Pi-hole migration and backup restore
- DNS/UI health-check failure
- Automatic rollback and rollback failure
- Offline and upstream-DNS outage behavior
- Update artifact and clean-image version consistency
- Real Raspberry Pi update from every supported source version

## Alternatives Considered

### Reflash new disk images

Retained for recovery, rejected for routine updates because it erases installation state.

### Docker pull and Compose up

Useful primitives but insufficient alone: they do not authenticate the whole appliance release, back up data, coordinate configuration, journal migration, or provide product-level rollback.

### Package everything as Debian packages

Potentially useful for individual host components but does not solve container/data migration or atomic cross-component activation by itself.

### A/B root filesystems now

Preferred long-term direction for base-OS updates but deferred until the application/appliance updater and target partition design are validated.

## Unresolved Questions

- Production signing-key custody, rotation publication, and CI integration
- Release hosting
- Backup format and validation depth
- Pi-hole data compatibility matrix
- Downgrade policy
- Release retention and disk quotas
- Whether to use an existing update framework for application bundles
- Integration boundary with future A/B updater

## Acceptance Criteria

The v1 manifest schema, detached Ed25519 format, verifier trust ordering,
backup contract, and transaction journal are now concrete. The RFC may become
Proposed when the production key-custody workflow and rollback compatibility
rules are concrete enough for independent security and failure-mode review.

## Decision

The high-level separation of images and updates is accepted in [ADR-0002](../adrs/0002-install-images-and-update-artifacts.md). This detailed RFC remains Draft.
