# Sovereign OS Roadmap

## Current Phase

🟢 Phase 01 — Flashable Pi-hole Image POC

## Next Priority

🟡 Milestone 01.1 — Appliance Update Foundation

Deliver signed, rollback-capable Pi-hole and appliance updates without reflashing or erasing persistent data.

## Following Milestone

⚪ Milestone 01.2 — Local Conversation and Capabilities

Deliver a minimal Sovereign-owned conversation experience backed by
provider-neutral local inference, a constrained capability executor, Pi-hole
read operations, and opt-in web search through a self-hosted SearXNG instance.

## Progress

- ✅ Concept Paper
- ✅ Master Plan
- 🟡 Pi-hole Image POC Plan (Draft)
- 🟡 Product and Documentation Foundation (Draft)
- ✅ Phase 01 Appliance Architecture Decision
- 🟡 RFC-0010 Raspberry Pi Image Deployment (Proposed)
- ✅ Image Build System Assessment — `rpi-image-gen` recommended
- ⏳ `rpi-image-gen` Proof Build
- ⏳ Raspberry Pi Image
- ⏳ Signed Appliance Update Artifact
- ⏳ Local inference benchmark on Raspberry Pi 5
- ⏳ Conversation and capability architecture RFC
- ⏳ SearXNG-backed web search capability

---

## Phases

- [00 Master Plan](docs/roadmap/00-master-plan.md)
- [01 Flashable Pi-hole Image POC](docs/roadmap/01-preview-poc.md)
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
- [RFC-0014: Appliance update system](docs/rfcs/0014-appliance-update-system.md)
