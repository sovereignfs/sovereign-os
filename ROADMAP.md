# Sovereign OS Roadmap

## Status Legend

- ✅ Complete — implemented and qualified on supported hardware
- 🟡 In progress — implementation or hardware qualification is active
- ⚪ Planned — accepted direction, not yet started
- ⏳ Pending decision — research or an RFC must close the design boundary

## Current Position

✅ Phase 01 — Flashable Raspberry Pi Image POC

The Raspberry Pi 5 image build, flash, first-boot, Pi-hole, persistent DATA
partition, local routing, first-login, and Sovereign Console health experience
have been exercised on physical hardware.

🟡 Milestone 01.1 — Appliance Update Foundation

The signed appliance updater can inspect, prepare, back up, stage, activate,
health-check, commit, recover, and roll back versioned releases while preserving
the dedicated DATA partition. An initial signed update transaction passed
Raspberry Pi qualification.

The first fully versioned appliance-release qualification, from preview.9 to
preview.10, exposed service-readiness and systemd dependency races. Automatic
rollback worked and restored preview.9. Fixes are implemented and locally
verified; a clean preview.11 base and preview.12 update must qualify them on the
Raspberry Pi before the updater is considered ready for normal users.

Unattended automatic installation remains disabled until the manual,
health-gated update path and its operational controls are qualified.

## Milestone Sequence

### 1. Complete Appliance Update Qualification

**Status:** 🟡 In progress

**User outcome:** Install a compatible Sovereign appliance release without
reflashing or losing persistent data.

Next qualification pair:

- preview.11: clean flashable base containing the systemd and readiness fixes;
- preview.12: signed, versioned installed-device update built from the same
  source revision.

The physical qualification must prove:

- update compatibility and signature verification;
- staging without changing the active release;
- interruption recovery;
- forced health-check failure and automatic rollback;
- successful activation and commit;
- reboot persistence;
- preservation of Pi-hole configuration, credentials, update state, and the
  dedicated DATA mount; and
- no regression to Console, DNS, Pi-hole, Nginx, SSH, or first-login behavior.

### 2. Production Update Operations

**Status:** ⚪ Planned

**Depends on:** Completed preview.11 to preview.12 qualification

**User outcome:** A supportable update mechanism with trustworthy release and
recovery operations.

Planned work:

- automate persistent-data restore verification;
- define bounded retention and cleanup for old releases, backups, journals, and
  failed transactions;
- establish production signing-key custody, rotation, and revocation;
- approve the update RFC and production manifest policy;
- publish release compatibility, rollback limitations, and recovery guidance;
  and
- qualify every supported source-to-target update path on real hardware.

### 3. Update Discovery and Console Controls

**Status:** ⚪ Planned

**Depends on:** Production Update Operations

**User outcome:** Learn about and install `x+1` from Sovereign Console without
using the command line or reflashing.

Planned work:

- publish signed update-channel metadata over HTTPS;
- periodically check for compatible updates without sending household data;
- show version, channel, release notes, download size, reboot requirements, and
  rollback limitations in Console;
- provide user-triggered download and installation;
- report download, verification, staging, activation, validation, rollback, and
  completion states; and
- retain a CLI recovery path independent of Console.

The initial policy is **notify and require approval**. Automatic download and
maintenance-window installation follow only after repeated field qualification.
Every automatic policy retains signature verification, health-gated activation,
and automatic rollback.

### 4. Local Conversation and Capabilities

**Status:** ⚪ Planned; research and RFC work may proceed in parallel

**Depends on:** Stable appliance update boundary

**User outcome:** Ask Sovereign local questions, inspect system and Pi-hole
status, and explicitly use privacy-transparent, self-hosted web-search tooling.

Milestone 01.2 will deliver:

- a Sovereign-owned conversation experience;
- provider-neutral local inference and model-management contracts;
- a Raspberry Pi 5 benchmark of llama.cpp and Ollama;
- a typed capability registry and deterministic executor;
- `system.health` and read-only Pi-hole capabilities;
- opt-in `web.search` through a locally operated SearXNG instance;
- restricted `web.fetch`, citations, privacy indicators, and audit events; and
- real-hardware qualification within DNS-latency, memory, power, and thermal
  budgets.

### 5. Home Automation Integration

**Status:** ⚪ Planned

**Depends on:** Qualified capability executor

**User outcome:** Ask about and safely control allowlisted home entities through
the same Sovereign conversation boundary.

The first slice is read-only Home Assistant entity discovery, state, and
history. Later slices may propose allowlisted actions, but deterministic policy
outside the model must authorize them and require confirmation according to
risk. The model never receives unrestricted Home Assistant, shell, Docker, or
network access.

### 6. Full Base-OS Updates

**Status:** ⏳ Architecture decision pending

**Depends on:** Stable appliance updater and persistent partition contract

**User outcome:** Update Debian, kernel, firmware, Docker, and early system
services without reflashing.

The current updater covers versioned Sovereign appliance releases; it does not
make base-OS package transactions atomic. The long-term milestone must select
and qualify an A/B root-filesystem or equivalent immutable deployment design
with:

- persistent DATA independent of either system slot;
- atomic boot-slot selection;
- boot and health confirmation;
- automatic fallback to the previous system;
- signed system artifacts; and
- an external recovery-image path.

This milestone closes the remaining “flash once” gap.

## Progress Summary

- ✅ Concept paper and master plan
- ✅ Phase 01 appliance architecture decision
- ✅ `rpi-image-gen` assessment, proof build, and automated ARM64 image pipeline
- ✅ Flashable Raspberry Pi 5 image exercised on hardware
- ✅ Docker-based Pi-hole, `/dns/*` routing, and persistent DATA
- ✅ First-login credential-change and optional SSH-key flow
- ✅ Sovereign Console read-only health page qualified on Raspberry Pi 5
- ✅ Signed update transaction, interruption recovery, rollback, and persistence
  demonstrated on Raspberry Pi 5
- 🟡 Fully versioned appliance-release qualification and updater hardening
- ⚪ Persistent restore automation, retention, and production signing operations
- ⚪ Update discovery and Sovereign Console update controls
- ⏳ Local inference benchmark and conversation/capability RFCs
- ⚪ SearXNG-backed web-search capability
- ⚪ Home Assistant capability integration
- ⏳ A/B or equivalent full base-OS update architecture

---

## Phases

- [00 Master Plan](docs/roadmap/00-master-plan.md)
- [01 Flashable Pi-hole Image POC](docs/roadmap/01-preview-poc.md)
- [Console Foundation](docs/roadmap/01-console-foundation.md)
- [01.1 Appliance Update Foundation](docs/roadmap/01-1-update-foundation.md)
- [01.2 Local Conversation and Capabilities](docs/roadmap/01-2-local-conversation-capabilities.md)

## Project Documentation

- [Documentation index](docs/README.md)
- [Initial target user](docs/product/target-user.md)
- [Core preview use cases](docs/product/core-use-cases.md)
- [Preview scope and non-goals](docs/product/preview-scope.md)
- [System overview](docs/architecture/system-overview.md)
- [Preview threat model](docs/security/threat-model.md)
- [ADR-0001: Phase 01 appliance architecture](docs/adrs/0001-phase-01-appliance-architecture.md)
- [RFC-0010: Raspberry Pi image deployment](docs/rfcs/0010-raspberry-pi-image-deployment.md)
- [Image release checklist](docs/operations/image-release-checklist.md)
- [ADR-0002: Installation images and update artifacts](docs/adrs/0002-install-images-and-update-artifacts.md)
- [ADR-0004: Provider-neutral assistant and web search](docs/adrs/0004-provider-neutral-assistant-and-web-search.md)
- [ADR-0005: Sovereign Console namespace and health boundary](docs/adrs/0005-sovereign-console-and-health-boundary.md)
- [RFC-0014: Appliance update system](docs/rfcs/0014-appliance-update-system.md)
