# Phase 01 Scope and Non-Goals

**Status:** Draft  
**Version:** 0.2  
**Detailed plan:** [Flashable Pi-hole Image POC](../roadmap/01-preview-poc.md)

## Scope Statement

Phase 01 proves that Sovereign can deliver a useful home appliance as one flashable Raspberry Pi image. A user writes the image, boots a Raspberry Pi 5, and receives an operational Pi-hole service at:

```text
http://sovereign.local/dns/admin/
```

The phase validates distribution and appliance foundations, not the AI-native platform.

## Included

- Raspberry Pi 5 with 16 GB RAM as the sole target.
- Raspberry Pi OS Lite 64-bit base.
- One reproducible compressed disk image.
- Docker Engine and Compose deployment boundary.
- Official Pi-hole ARM64 container pinned by immutable digest.
- Pi-hole artifact embedded for offline first boot.
- Persistent Pi-hole configuration and data.
- Unique device identity and Pi-hole credential generated on first boot.
- Nginx routing Pi-hole under `/dns/*`.
- Avahi/mDNS providing `sovereign.local`.
- Direct-IP fallback.
- Automatic startup and idempotent first-boot initialization.
- DNS, HTTP, reboot, interruption, persistence, resource, and release tests.
- Checksums, release metadata, flashing instructions, router DNS instructions, and known limitations.

## Explicit Non-Goals

- Sovereign web dashboard, backend, administration interface, or API.
- Local or remote LLM, AI chat, capability registry, or Pi-hole AI adapter.
- Voice or wake-word support.
- Home Assistant, documents, calendar, or other service integrations.
- A general plugin lifecycle or marketplace.
- Public internet exposure or remote administration.
- Automatic router configuration.
- Pi-hole DHCP enabled by default.
- Multi-user support.
- Broad hardware, OS, SD/USB/NVMe, or architecture support without testing.
- Production-grade automatic update, rollback, or support guarantees.
- Replacing Raspberry Pi OS or creating a new Linux distribution from scratch.

## Required External User Action

Pi-hole will be operational immediately after first boot, but network-wide filtering requires the user to configure a router or individual devices to use the Raspberry Pi's stable IP address as DNS. The image must not attempt to modify unknown router settings or enable a competing DHCP server automatically.

## Change Control

An item may enter Phase 01 only when it is required to produce, boot, access, secure, diagnose, or verify the Pi-hole appliance image. All AI and broader platform work remains in the master-plan backlog until this phase meets its exit criteria.

