# RFC-0010: Raspberry Pi Image Deployment

**Status:** Proposed  
**Author:** Project creator and Codex  
**Created:** 2026-07-19  
**Target phase:** Phase 01  
**Related decision:** [ADR-0001](../adrs/0001-phase-01-appliance-architecture.md)

## Summary

Build a reproducible Raspberry Pi OS Lite 64-bit disk image that embeds a pinned official Pi-hole ARM64 container. On first boot, an idempotent systemd unit creates device identity and secrets, imports the container, starts DNS, configures `/dns/*` reverse-proxy routing, and advertises `sovereign.local` over mDNS.

## Problem

The project needs a first artifact that proves Sovereign can deliver self-hosted software as a coherent appliance rather than a collection of manual installation steps.

The solution must:

- be writable using Raspberry Pi Imager;
- boot without user shell work;
- avoid build-machine identity and minimize the lifetime of preview bootstrap credentials;
- operate without downloading Pi-hole on first boot;
- persist configuration across reboot and container replacement;
- reserve root `/admin` and `/api` paths for future Sovereign services;
- remain reproducible and auditable.

## Goals

- One compressed flashable image for Raspberry Pi 5.
- Raspberry Pi OS Lite 64-bit base.
- Pi-hole v6 deployed using the official ARM64 container.
- Immutable container digest and recorded provenance.
- Offline first boot after the image has been downloaded.
- Unique first-boot identity and Pi-hole credential.
- Pi-hole DNS on TCP/UDP 53.
- Pi-hole UI and API under `/dns/*`.
- `sovereign.local` mDNS discovery with direct-IP fallback.
- Persistent Pi-hole data and recoverable initialization.

## Non-Goals

- Sovereign dashboard or API
- AI or LLM runtime
- Public remote access
- Automatic router configuration
- Pi-hole DHCP by default
- Multi-device clustering
- Multi-platform images
- General container marketplace
- Fully automatic updates or transactional rollback

## Proposed Build Inputs

Every release build must pin and record:

- source repository revision;
- image-build-tool revision;
- Raspberry Pi OS release and base inputs;
- Debian package snapshot or resolved package versions where practical;
- Docker Engine and Compose versions;
- Pi-hole container repository, version, platform, and digest;
- Nginx and Avahi package versions;
- build environment and architecture;
- release configuration and build timestamp.

Mutable references such as `latest` must not be release inputs.

## Image Build

The build will:

1. Generate a Raspberry Pi OS Lite 64-bit root filesystem and boot partition.
2. Install Docker Engine, Compose support, Nginx, Avahi, and required utilities.
3. Add Sovereign-owned systemd units and configuration.
4. Pull the exact Linux ARM64 Pi-hole container by digest in the build environment.
5. Export it as an OCI or Docker archive.
6. Store the archive and digest manifest under `/opt/sovereign/bootstrap/`.
7. Add an idempotent first-boot initializer.
8. Remove package caches, temporary files, build SSH keys, machine identity, and logs.
9. Export the raw image.
10. Verify partitions and filesystem integrity.
11. Compress, checksum, and produce release metadata.

The [image-build assessment](../research/image-build-system-assessment.md) recommends `rpi-image-gen`, pinned to an exact release tag and commit, using a supported native ARM64 Debian/Raspberry Pi OS build host. This becomes the proposed builder when the minimal boot, Sovereign layer, and persistent-partition proof builds pass. `pi-gen` remains the fallback if a blocking `rpi-image-gen` defect cannot be resolved within the POC scope.

## Runtime Components

### Docker

Docker is an internal deployment mechanism. Users do not need to run Compose commands for normal use.

The service definition must:

- pin Pi-hole by digest;
- publish DNS on TCP and UDP 53;
- publish Pi-hole HTTP only on a loopback host port;
- mount persistent `/etc/pihole` data;
- use a read-only secret file for the administrator password;
- define bounded logs and restart behavior;
- avoid privileges and Linux capabilities not required for DNS-only operation;
- leave DHCP and NTP ports unpublished.

### Nginx

Nginx owns LAN TCP port 80 and routes only `/dns/*` to Pi-hole. It strips `/dns` before proxying. Pi-hole is configured with `webserver.paths.prefix = "/dns"` so its generated links, redirects, and API calls retain the external prefix.

Nginx must normalize or reject ambiguous paths and prevent traversal or prefix escape.

### Avahi

Avahi advertises hostname `sovereign` and an HTTP service. `.local` remains an mDNS name rather than a Pi-hole-managed unicast DNS zone.

### First-Boot Initializer

The initializer is a root-owned systemd oneshot unit with explicit dependencies on local filesystems, networking where required, and Docker.

It must use atomic writes and per-step state or safely detectable outcomes. A final completion marker may be written only after DNS and HTTP smoke tests succeed.

## Proposed Port and Path Ownership

| Listener | Owner | Exposure | Purpose |
| --- | --- | --- | --- |
| TCP/UDP 53 | Pi-hole container | Local network | DNS |
| TCP 80 | Nginx host service | Local network | Appliance HTTP entry point |
| TCP 8080 or selected high port | Pi-hole container mapping | Loopback only | Proxy backend |
| `/dns/admin/*` | Nginx to Pi-hole | Local network | Pi-hole UI |
| `/dns/api/*` | Nginx to Pi-hole | Local network | Pi-hole API |
| `/admin/*` | Reserved | None in Phase 01 | Future Sovereign administration |
| `/api/*` | Reserved | None in Phase 01 | Future Sovereign API |

## Configuration and Persistence

Proposed host paths:

```text
/etc/sovereign/                  non-secret appliance configuration
/data/sovereign/apps/pihole/    persistent Pi-hole state
/data/sovereign/secrets/        root-owned secrets
/data/sovereign/update-state/   initialization and future update state
/var/log/sovereign/             bounded appliance logs
/opt/sovereign/bootstrap/       immutable bootstrap assets
```

`/data` is a dedicated persistent partition. Pi-hole data must survive restart, container recreation, and future replacement of the root filesystem. Backup and restore semantics will be defined after the initial layout is validated. See [ADR-0002](../adrs/0002-install-images-and-update-artifacts.md).

## Password Delivery

The device generates a unique Pi-hole administrator password on first boot and passes it using Pi-hole's supported password-file mechanism.

For the Phase 01 POC, the device displays that password on the attached physical console after Pi-hole and the local HTTP entry point pass their health checks. The service writes directly to `/dev/tty1`, not to the system journal. This avoids exposing the secret to unauthenticated LAN clients, the boot partition, or permanent ordinary logs.

This choice requires temporary physical display access for initial login. A later one-time claim mechanism may replace it without changing the persistent password-file model.

For headless preview onboarding, [ADR-0003](../adrs/0003-preview-bootstrap-access.md)
adds the temporary `sovereign`/`sovereign` Linux account. Its password is
expired in the shipped image and must be replaced during the first interactive
SSH login. Once logged in, the user retrieves the separate, device-unique
Pi-hole password from the root-owned secret file. This is an explicit preview
exception, not the intended production credential model.

## Security and Privacy

- No production release may ship a shared password. Phase 01 preview images use
  the constrained bootstrap exception in ADR-0003.
- No secret in source, image build configuration, Compose YAML, or ordinary logs.
- No Pi-hole web port directly exposed to the LAN.
- No public network binding beyond documented DNS and HTTP ports.
- No Pi-hole DHCP or NTP capabilities by default.
- No privileged container unless a measured requirement is documented.
- Final image scanned for SSH host keys, machine IDs, credentials, and build logs.
- Pinned container digest and published checksums.
- Pi-hole query data remains on the device by default.

## Failure and Recovery

- Interrupted first boot must resume without destroying valid data.
- Failed container import must preserve the embedded artifact for retry.
- Pi-hole health failure must prevent false completion status.
- Nginx may start only when its configuration validates.
- mDNS failure must not prevent direct-IP use.
- Container recreation must reuse persistent data.
- A recovery procedure must reset first-boot state without silently deleting Pi-hole data.

## Updates

Phase 01 does not implement unattended updates. The initial documented update model is:

1. Pin a new Pi-hole digest in a new Sovereign image/release definition.
2. Test migration against a copy of persistent data.
3. Publish compatibility and rollback notes.
4. Perform an explicit update only after backup.

Users must not run an unbounded `latest` pull as the supported update process.

## Testing Strategy

- Static inspection of image contents and identity sanitization
- Boot on real Raspberry Pi 5 hardware
- Offline first boot
- First-boot interruption and restart
- TCP and UDP DNS queries from another device
- UI/API prefix regression tests
- Container recreation and data persistence
- Reboot ordering and recovery
- mDNS client matrix and direct-IP fallback
- Port exposure and firewall inspection
- Final compressed-artifact flash test
- Container digest and release checksum verification

## Alternatives Considered

### Bare-metal Pi-hole

Smaller runtime stack but harder to install reproducibly inside a non-running image root and less isolated from the base OS.

### Pull Pi-hole on first boot

Smaller image but creates a mandatory first-boot internet and registry dependency. Rejected for the POC's appliance promise.

### Pi-hole owns ports 80/443 directly

Simpler initially but consumes future Sovereign namespaces and prevents central routing. Rejected.

### Pi-hole subdomain

`dns.sovereign.local` would be clean after local DNS is operational, but is not as reliable for discovery before clients use Pi-hole. Path namespacing is preferred for Phase 01.

## Drawbacks and Maintenance Cost

- Docker and Nginx add update and security responsibilities.
- Embedded container artifacts increase image size.
- Three independently versioned layers must be tested: base OS, container runtime, and Pi-hole.
- Prefix routing becomes a release compatibility test.
- Appliance-specific first-boot code must be maintained and recovered safely.

## Unresolved Questions

- Completion of the `rpi-image-gen` proof build and selection of the exact pinned release
- Exact Raspberry Pi OS release
- Requalification of pinned Docker and Pi-hole inputs at release review
- Firewall implementation
- Release stability duration
- Minimum supported storage

## Acceptance Criteria

The proposal is ready for implementation planning when all unresolved questions that affect M2 are decided or explicitly deferred, and the Phase 01 acceptance criteria are testable from the exported image.

## Decision

The high-level architecture is accepted in [ADR-0001](../adrs/0001-phase-01-appliance-architecture.md). This RFC remains Proposed until its unresolved build, credential-delivery, and version choices are reviewed.
