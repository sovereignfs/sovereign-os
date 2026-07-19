# OTA Update Framework Assessment

**Status:** Planned  
**Decision informed:** Appliance Update RFC and future A/B OS update RFC

## Questions

1. Should Milestone 01.1 use a small Sovereign-specific signed application/appliance updater or adopt an existing framework?
2. Which framework should later provide A/B root-filesystem updates on Raspberry Pi 5?

These are related but not necessarily the same decision.

## Required Capabilities

### Application and Appliance Updates

- Signed metadata and payload verification
- Hardware/version compatibility
- Versioned application files
- OCI/container payloads
- Pre/post-install hooks with constrained authority
- Persistent-data backup and migration
- Health-gated commit and rollback
- Durable interruption recovery
- Local/manual installation and HTTPS distribution
- No mandatory hosted control plane

### Future OS Updates

- Raspberry Pi 5 boot-chain integration
- A/B root filesystems
- Persistent data partition
- Trial boot and automatic rollback
- Signed full-rootfs artifacts
- Bootloader and kernel update strategy
- Power-loss resilience
- Recovery environment

## Candidates

### Small Sovereign updater

Evaluate implementation cost, auditability, archive safety, signature libraries, failure-state complexity, and the risk of creating a security-critical custom updater.

### RAUC

Evaluate signed bundles, HTTP streaming, A/B slot support, Raspberry Pi boot integration, application/tar bundle suitability, operational complexity, licensing, and release tooling.

### Mender

Evaluate A/B Debian-family integration, persistent data, update modules, Raspberry Pi 5 integration requirements, optional hosted/server components, licensing, and the ability to operate without mandatory cloud dependency.

### SWUpdate or other candidates

Include only when they meet the local-first, signed, rollback-capable, Raspberry Pi requirements and can be evaluated from maintained primary documentation.

## Evaluation Method

1. Define a minimal Pi-hole appliance update payload.
2. Define a rootfs A/B test image separately.
3. Implement proof transactions for viable candidates.
4. Interrupt each transaction at controlled points.
5. Verify boot, data persistence, health commit, and rollback.
6. Measure image/storage overhead and maintainer burden.
7. Document security boundaries and signing-key workflow.

## Evaluation Criteria

- Failure safety and recovery quality
- Signature and compatibility model
- Raspberry Pi 5 support and integration effort
- Local-first operation without mandatory service accounts
- Persistent-data behavior
- Container/application update fit
- A/B OS update fit
- Project maturity and maintenance activity
- Documentation quality
- Licensing and redistribution
- Complexity for one maintainer
- Ability to test locally and in CI

## Required Output

- Evidence-backed comparison
- Recommendation for Milestone 01.1 application/appliance updates
- Separate recommendation or deferral for A/B OS updates
- Prototype and failure-injection results
- Partition and boot integration implications
- Signing and key-management implications
- Explicit rejection reasons for non-selected candidates

