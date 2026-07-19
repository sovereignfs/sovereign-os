# ADR-0002: Separate Installation Images from Update Artifacts

**Status:** Accepted  
**Date:** 2026-07-19  
**Decision owner:** Project creator  
**Related milestone:** [Appliance Update Foundation](../roadmap/01-1-update-foundation.md)  
**Related RFC:** [RFC-0014](../rfcs/0014-appliance-update-system.md)

## Context

Writing a new raw disk image replaces the target storage layout and normally erases installed configuration and data. That is acceptable for clean installation and recovery but not for routine updates of an operating household service.

Pi-hole's container can be replaced independently when its state is stored outside the container. Sovereign appliance configuration can also be installed into versioned directories and activated atomically. Full operating-system replacement requires a more advanced A/B root-filesystem design.

The update capability is the highest priority immediately after the Phase 01 image is released.

## Decision

- A compressed disk image is the clean-install and recovery artifact.
- Existing installations receive separately packaged, signed update artifacts.
- Application, appliance, and base-OS versions are tracked independently.
- Pi-hole and all valuable user/device state live on a dedicated persistent data partition mounted at `/data`.
- Phase 01 must establish the data partition and version metadata, but need not implement the updater.
- The first updater is user-triggered and may be command-line based.
- Updates are staged, authenticated, backed up, health checked, journaled, and automatically rolled back when safe.
- Mutable container tags are not supported update inputs.
- Full A/B operating-system updates are a later design; the current layout and updater must preserve that option.

## Consequences

### Positive

- Routine releases do not wipe Pi-hole data or credentials.
- New-install and existing-device delivery can evolve independently.
- Container and appliance rollback become practical.
- Release artifacts can be smaller than complete disk images.
- A dedicated data partition prepares the product for A/B OS updates.
- Users are not forced to reconfigure their routers after every release.

### Negative

- The project must build and test both installation and update artifacts.
- Signing, key custody, version compatibility, migrations, and rollback become product responsibilities.
- A dedicated data partition complicates the Phase 01 image layout.
- Container rollback may be unsafe after irreversible Pi-hole data migration.
- Base-OS updates remain a separate problem until A/B support exists.

### Risks

- A flawed updater can interrupt household DNS.
- Signing-key compromise could authorize malicious releases.
- Power loss may leave a partially staged transaction.
- Insufficient storage may prevent backup or rollback.
- Release image and update artifact may drift if built from different definitions.
- Persistent data may contain sensitive DNS history and secrets.

## Alternatives Considered

### Reflash for every release

Rejected as the normal update path because it erases state and creates unnecessary setup and recovery work.

### Modify active files and containers in place

Rejected because partial failure is hard to diagnose and roll back.

### Implement A/B root filesystems immediately

Deferred because it adds bootloader, partition, storage, health-commit, and recovery complexity before the POC image is proven.

### Unattended automatic updates from the first release

Deferred because manual initiation provides better control and diagnosis while formats and compatibility rules are immature.

## Validation and Revisit Conditions

Revisit the design when:

- Phase 01 storage measurements show that a dedicated data partition is impractical;
- Pi-hole migrations prevent safe application rollback;
- base-OS security maintenance requires A/B implementation sooner;
- a selected update framework provides stronger guarantees with less custom code;
- the project introduces additional applications with cross-service migrations.
