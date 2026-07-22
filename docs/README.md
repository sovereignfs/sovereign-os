# Sovereign OS Documentation

This directory contains the planning, design, research, and operational record for Sovereign Home OS.

## Start Here

- [Concept paper](../CONCEPT.md): why the project exists and the principles it protects.
- [Public roadmap](../ROADMAP.md): the current phase and public progress summary.
- [Master plan](roadmap/00-master-plan.md): the internal source of truth for the complete project plan.
- [Preview POC plan](roadmap/01-preview-poc.md): the operational plan for the current phase.
- [Phase 01 architecture decision](adrs/0001-phase-01-appliance-architecture.md): the accepted appliance boundary.
- [Raspberry Pi image deployment RFC](rfcs/0010-raspberry-pi-image-deployment.md): the proposed build and runtime design.
- [Image release checklist](operations/image-release-checklist.md): the required verification before publication.
- [Appliance update milestone](roadmap/01-1-update-foundation.md): the immediate priority after the POC release.
- [Appliance update RFC](rfcs/0014-appliance-update-system.md): signed, staged, health-gated updates without reflashing.
- [Console Foundation](roadmap/01-console-foundation.md): the Sovereign UI entry point and first read-only system health vertical slice.
- [Console health design brief](design/console-health.md): user experience, states, privacy, and acceptance requirements.
- [Local conversation and capabilities milestone](roadmap/01-2-local-conversation-capabilities.md): the first assistant, local inference, capability execution, and web-search vertical slice.
- [Local AI options](research/local-ai-options.md): the provider-neutral inference direction and Raspberry Pi benchmark plan.
- [Preview.6 Console qualification](research/preview-6-console-qualification-report.md): hardware findings, root causes, and live-hotfix evidence.
- [Preview.8 appliance update qualification](research/preview-8-appliance-update-qualification-report.md): signed preview.7-to-preview.8 update, interruption recovery, rollback, commit, reboot, and persistence evidence.

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
