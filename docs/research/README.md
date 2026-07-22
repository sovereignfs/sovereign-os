# Research Index

Research documents establish evidence before the project commits to an implementation direction.

## Preview Research Backlog

- [Image build system assessment](image-build-system-assessment.md) - Concluded; `rpi-image-gen` recommended pending proof build
- [rpi-image-gen proof build report](rpi-image-gen-proof-build-report.md) - ARM64 engineering build passed; native-host and Pi 5 boot qualification pending
- [Sovereign layer and storage proof report](sovereign-layer-storage-proof-report.md) - External product layer and `/data` image structure passed; hardware persistence test pending
- [Embedded OCI artifact proof report](embedded-oci-artifact-proof-report.md) - Deterministic ARM64 OCI embedding and Docker import passed
- [Docker runtime and first-boot import proof report](docker-runtime-import-proof-report.md) - Pinned ARM64 runtime build and import integration passed; Pi 5 boot execution pending
- [Pi-hole image embedding report](pihole-image-embedding-report.md) - Official Pi-hole 2026.04.1 ARM64 artifact pinned, embedded, and import-validated
- [Pi-hole first-boot runtime report](pihole-first-boot-runtime-report.md) - Persistent Compose configuration, unique secret generation, DNS startup, and health gating passed locally
- [Preview 0.4 physical qualification](preview-4-physical-qualification-report.md) - Real Pi 5 boot, persistence, routing, load, and security results; release blockers identified and remediated in source pending rebuild
- [Raspberry Pi 5 platform assessment](rpi5-platform-assessment.md)
- [Deployment model comparison](deployment-model-comparison.md)
- [Local network discovery](local-network-discovery.md)

## Immediate Post-POC Research

- [OTA update framework assessment](ota-update-framework-assessment.md)
- [Local AI options](local-ai-options.md) - Direction selected; Raspberry Pi 5 runner and model benchmark pending

## Deferred Platform Research

- [Pi-hole API assessment](pihole-api-assessment.md)

Use the [research-note template](../templates/research-note.md). Conclusions should identify which RFC or decision they inform.
