# ADR-0001: Phase 01 Pi-hole Appliance Architecture

**Status:** Accepted  
**Date:** 2026-07-19  
**Decision owner:** Project creator  
**Related plan:** [Phase 01](../roadmap/01-preview-poc.md)  
**Related RFC:** [RFC-0010](../rfcs/0010-raspberry-pi-image-deployment.md)

## Context

The original Phase 01 preview combined a dashboard, AI orchestration, capability contracts, and Pi-hole integration. That scope required several platform decisions before producing a usable artifact.

The project instead needs an earlier proof that it can deliver a coherent home appliance: a user flashes one image, boots a Raspberry Pi, and receives an operational Pi-hole service without installing software.

The image also needs a route namespace that will remain compatible with future Sovereign interfaces. Pi-hole must therefore occupy `/dns/*`, leaving `/admin/*` and `/api/*` available to the future platform.

## Decision

Phase 01 will deliver a flashable Raspberry Pi 5 image with:

- Raspberry Pi OS Lite 64-bit as the base operating system;
- Docker Engine and Compose as the application deployment boundary;
- the official Pi-hole ARM64 container pinned by immutable digest;
- the Pi-hole container artifact embedded for offline first boot;
- persistent Pi-hole data on the host;
- a unique Pi-hole administrator credential generated on first boot;
- Nginx as the proposed host reverse proxy, subject to RFC validation;
- Pi-hole served externally under `/dns/admin/*` and `/dns/api/*`;
- Avahi advertising the system as `sovereign.local`;
- an idempotent first-boot systemd service.

The Phase 01 image will not include the Sovereign dashboard, AI runtime, LLM, capability system, voice, Home Assistant, or a general plugin system.

Pi-hole DHCP will be disabled by default. Users must configure their router or devices to use the Pi's stable address as DNS.

## Consequences

### Positive

- Produces a small, understandable, demonstrable first milestone.
- Validates image build, first boot, networking, persistence, and release mechanics early.
- Pins Pi-hole independently of base-OS packages.
- Provides a clean deployment pattern for later containerized services.
- Preserves `/admin` and `/api` for Sovereign.
- Allows container replacement without mixing Pi-hole files into the base OS.
- Supports an offline first boot.

### Negative

- Adds Docker runtime, storage, networking, and maintenance overhead.
- Requires explicit container artifact and base-OS supply-chain management.
- Requires a reverse proxy to provide the `/dns` prefix.
- Does not eliminate the user's router DNS configuration step.
- Defers validation of the AI-native product concept.

### Risks

- Port 53 may conflict with a host resolver.
- Pi-hole prefix behavior may regress across releases.
- Persistent Pi-hole data may not be backward compatible after upgrades.
- Container and host firewall rules may expose unintended services.
- mDNS may fail across isolated networks or unsupported clients.
- First-boot interruption could leave partial state without careful idempotency.

## Alternatives Considered

### Native Pi-hole installation

Rejected for Phase 01 because unattended installation inside an image build is more coupled to chroot state, running services, network detection, and base-OS packages. It remains viable if container behavior becomes a blocker.

### Ubuntu Server base

Rejected for Phase 01 in favor of Raspberry Pi OS Lite's smaller footprint and direct alignment with Raspberry Pi hardware and image tooling.

### Dashboard and AI in the first image

Deferred because they do not contribute to validating the image appliance foundation and would obscure failures behind multiple new systems.

### Pi-hole on root `/admin` and `/api`

Rejected because those paths are valuable future Sovereign namespaces. Pi-hole v6 supports a reverse-proxy prefix specifically for this purpose.

## Validation and Revisit Conditions

Revisit this decision if:

- Docker prevents reliable DNS or significantly complicates recovery;
- Pi-hole cannot pass the required `/dns/*` regression tests;
- the embedded OCI artifact makes image production impractical;
- measured resource or storage overhead is unacceptable;
- official Pi-hole distribution or licensing requirements conflict with embedding;
- a native package path becomes clearly more reproducible and maintainable.
