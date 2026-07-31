# Sovereign OS Documentation

This directory contains the planning, design, research, and operational record for Sovereign Home OS.

## Start Here

- [Concept paper](../CONCEPT.md): why the project exists and the principles it protects.
- [Public roadmap](../ROADMAP.md): the current phase and public progress summary.
- [Contributing guide](../CONTRIBUTING.md): development setup, branching/commit conventions, pull requests, and how to propose a change.
- [Development workflow](development/workflow.md): the specification-driven planning chain, roles, document types, and definition of done.
- [Master plan](roadmap/00-master-plan.md): the internal source of truth for the complete project plan.
- [Preview POC plan](roadmap/01-preview-poc.md): the operational plan for the current phase.
- [Phase 01 architecture decision](adrs/0001-phase-01-appliance-architecture.md): the accepted appliance boundary.
- [Raspberry Pi image deployment RFC](rfcs/0010-raspberry-pi-image-deployment.md): the proposed build and runtime design.
- [Image release checklist](operations/image-release-checklist.md): the required verification before publication.
- [Appliance update milestone](roadmap/01-1-update-foundation.md): the immediate priority after the POC release.
- [Appliance update RFC](rfcs/0014-appliance-update-system.md): signed, staged, health-gated updates without reflashing.
- [Update discovery RFC](rfcs/0015-update-discovery.md): proposed device-side check-and-notify mechanism, deliberately scoped away from Console and production signing.
- [Production signing-key custody decision](adrs/0006-production-signing-key-custody.md): password-manager-held production release-signing key, hardware key as a future upgrade path, plus rotation and revocation procedure.
- [Trust rotation v1](../update/README.md): `sovereign-update rotate-trust` delivers routine signing-key rotation and revocation through the same signed channel as any other release, instead of a manual per-device file copy.
- [Console Foundation](roadmap/01-console-foundation.md): the Sovereign UI entry point and first read-only system health vertical slice.
- [Console health design brief](design/console-health.md): user experience, states, privacy, and acceptance requirements.
- [Versioned appliance release design](design/versioned-appliance-release.md): stable base/update ownership, versioned payload layout, validation, activation, and rollback boundaries.
- [Local conversation and capabilities milestone](roadmap/01-2-local-conversation-capabilities.md): the first assistant, local inference, capability execution, and web-search vertical slice.
- [Local AI options](research/local-ai-options.md): the provider-neutral inference direction and Raspberry Pi benchmark plan.
- [Preview.6 Console qualification](research/preview-6-console-qualification-report.md): hardware findings, root causes, and live-hotfix evidence.
- [Preview.8 appliance update qualification](research/preview-8-appliance-update-qualification-report.md): signed preview.7-to-preview.8 update, interruption recovery, rollback, commit, reboot, and persistence evidence.
- [Preview.12 appliance update qualification](research/preview-12-appliance-update-qualification-report.md): signed preview.11-to-preview.12 update qualifying the service-readiness and systemd dependency fixes, with interruption recovery, forced rollback, commit, and reboot evidence.
- [Restore hardware qualification](research/restore-hardware-qualification-report.md): `sovereign-update restore` qualified against real Pi-hole state on Raspberry Pi 5, including a forced-health-failure rollback path.
- [Preview.14 appliance update qualification](research/preview-14-appliance-update-qualification-report.md): first update-transaction campaign run against a real base image that shipped restore/prune/rotate-trust natively, rather than a manually patched device.
- [Prune and trust rotation hardware qualification](research/prune-and-rotate-trust-hardware-qualification-report.md): `sovereign-update prune` and `rotate-trust` qualified against real on-device backups, releases, transactions, and a real signed single-key rotation handoff.
- [Versioned appliance update qualification](operations/versioned-appliance-update-qualification.md): hardware procedure for versioned Console, routing, Compose, lifecycle, and health payloads.
- [Update compatibility, rollback limitations, and recovery](operations/update-recovery-and-compatibility.md): plain-language guidance for a device owner — supported update paths, what rollback does and doesn't restore, and what to do if something goes wrong.

## Documentation Areas

- `product/`: users, problems, use cases, scope, terminology, and product decisions.
- `roadmap/`: phase plans, milestones, dependencies, risks, and exit criteria.
- `architecture/`: descriptions of the current system and its boundaries.
- `rfcs/`: proposals for significant interfaces, protocols, and technical systems.
- `adrs/`: accepted architectural decisions and their consequences.
- `research/`: investigations that inform a later proposal or decision.
- `experiments/`: reproducible tests of technical assumptions.
- `design/`: experience and interface design briefs.
- `development/`: contributor and AI-assisted development workflows.
- `operations/`: installation, releases, diagnostics, recovery, and support procedures.
- `security/`: threat models, data handling, privacy, and security practices.
- `plugins/`: plugin authoring and integration documentation.
- `governance/`: contribution, decision-making, licensing, and community policy.
- `templates/`: required structures for project documents.

## Document Status

Use one of these statuses:

- **Draft**: incomplete and open for substantial change.
- **Proposed**: ready for review and a decision.
- **Accepted**: approved as the current direction.
- **Implemented**: accepted and reflected in the running system.
- **Superseded**: replaced by another named document.
- **Rejected**: considered and intentionally not adopted.
- **Archived**: retained for history but no longer active.

Research notes and experiments may instead use **Planned**, **In progress**, **Concluded**, or **Abandoned**.

## Documentation Rules

1. Describe current behavior separately from future intent.
2. Mark assumptions and unresolved questions explicitly.
3. Link decisions to the evidence and proposals that produced them.
4. Define scope, non-scope, privacy implications, and acceptance criteria before implementation.
5. Update documentation in the same work item as the behavior it describes.
6. Do not treat a draft RFC as an accepted decision.
