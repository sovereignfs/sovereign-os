# Phase 01 - Flashable Pi-hole Image POC

**Status:** Draft  
**Version:** 0.2  
**Target:** Raspberry Pi 5 with 16 GB RAM  
**Owner:** Project creator  
**Related decision:** [ADR-0001](../adrs/0001-phase-01-appliance-architecture.md)

## 1. Objective

Produce a reproducible disk image that a user can write with Raspberry Pi Imager, boot on a Raspberry Pi 5, and use as an operational Pi-hole appliance without installing packages or running commands.

Pi-hole must be reachable at:

```text
http://sovereign.local/dns/admin/
```

The image establishes the distribution foundation for Sovereign Home OS. It does not yet implement the broader Sovereign platform.

## 2. User Promise

```text
Download image
    -> flash storage
    -> boot Raspberry Pi
    -> wait for first-boot initialization
    -> open sovereign.local
    -> use Pi-hole
```

Pi-hole will be installed, configured with safe appliance defaults, and started automatically. Direct-IP access will remain available when mDNS is unavailable.

The image cannot safely reconfigure arbitrary home routers. To filter the entire network, the user must still configure their router or individual devices to use the Raspberry Pi's stable IP address as DNS.

## 3. Target Environment

- Raspberry Pi 5 with 16 GB RAM
- Raspberry Pi OS Lite 64-bit
- microSD card initially; USB/NVMe support is not claimed until tested
- one local household network
- DHCP-provided address for first boot
- router DHCP reservation recommended for stable DNS service
- browser on another local device
- no public internet exposure

## 4. Architecture

```text
Raspberry Pi OS Lite 64-bit
├── Docker Engine and Compose
├── pinned official Pi-hole ARM64 container
├── Nginx reverse proxy
├── Avahi/mDNS
├── Sovereign first-boot systemd service
├── dedicated persistent data partition
└── root-owned device secrets
```

### Network Paths

```text
LAN TCP/UDP 53
    -> Pi-hole container TCP/UDP 53

LAN TCP 80
    -> Nginx
    -> strip /dns prefix
    -> Pi-hole webserver on loopback-only host port
```

Externally visible routes:

```text
/                 -> redirect to /dns/admin/
/dns              -> redirect to /dns/admin/
/dns/             -> redirect to /dns/admin/
/dns/admin/*       -> Pi-hole /admin/*
/dns/api/*         -> Pi-hole /api/*
```

The root `/admin/*` and `/api/*` namespaces remain reserved for future Sovereign services.

## 5. Image Contents

- Bootable Raspberry Pi OS Lite 64-bit base
- Docker Engine and Compose support
- Exact official Pi-hole ARM64 image pinned by digest
- Embedded Pi-hole container artifact for offline first boot
- Nginx configuration for the `/dns/*` namespace
- Avahi configuration for `sovereign.local`
- Idempotent first-boot initialization service
- Dedicated `/data` partition and persistent data/secret directory structure
- Health-check and diagnostic commands
- Log rotation
- Release manifest, checksums, and build metadata

## 6. First-Boot Responsibilities

The first-boot service must be safe to rerun after interruption. It will:

1. Confirm that initialization has not completed.
2. Expand or verify the root filesystem.
3. Set and advertise the `sovereign` hostname.
4. Generate a unique machine identity and SSH host keys where required.
5. Create persistent data and secret directories.
6. Generate a unique Pi-hole administrator credential.
7. Import and verify the embedded Pi-hole container artifact.
8. Materialize runtime configuration without embedding secrets in Compose files.
9. Start Pi-hole and wait for a healthy DNS service.
10. Start Nginx and verify `/dns/admin/` routing.
11. Start Avahi and advertise the HTTP service.
12. Run local DNS and HTTP smoke tests.
13. Record a completion marker only after required checks pass.

## 7. Persistent Data Layout

The exact paths remain subject to RFC review. The proposed layout is:

```text
/data/sovereign/
├── apps/
│   └── pihole/
│       └── etc-pihole/
├── secrets/
│   └── pihole-admin-password
└── update-state/
    └── firstboot-complete

/opt/sovereign/
└── bootstrap/
    ├── compose.yaml
    ├── images/
    └── manifests/
```

Compatibility bind mounts or links may expose conventional paths such as `/var/lib/sovereign`, but `/data/sovereign` is authoritative. This prepares the appliance for the [immediate post-POC update milestone](01-1-update-foundation.md) and later A/B root-filesystem updates.

The build artifact must contain no credential generated on a build machine. Device secrets must be created on first boot and restricted to the minimum required users and services.

## 8. Pi-hole Defaults

The image should provide a working, conservative default configuration:

- DNS on TCP and UDP port 53
- Pi-hole DHCP disabled
- Pi-hole NTP server disabled
- official default blocking configuration unless explicitly changed in the RFC
- documented upstream DNS default
- Pi-hole webserver reachable only through the host reverse proxy
- Pi-hole path prefix configured as `/dns`
- unique administrator password
- persistent Pi-hole configuration
- no mutable `latest` container tag

Enabling DHCP automatically is explicitly prohibited because an existing router DHCP service is expected.

## 9. Scope

- Reproducible image build
- Flashable compressed image
- Raspberry Pi OS Lite 64-bit base
- Docker-based Pi-hole v6 deployment
- Offline Pi-hole container availability on first boot
- `sovereign.local` through mDNS
- Direct-IP fallback
- `/dns/admin/` and `/dns/api/` proxy routing
- Unique first-boot identity and credentials
- Automatic service startup after reboot
- Fresh-flash, DNS, HTTP, persistence, and recovery testing
- Checksums, build manifest, release notes, and known limitations

## 10. Non-Scope

- Sovereign dashboard, backend, or API
- AI model, LLM runner, chat, or capability orchestration
- General plugin platform
- Voice
- Home Assistant
- Public remote access
- HTTPS trusted by arbitrary local clients
- Automatic router configuration
- Pi-hole DHCP by default
- Multi-user support
- Broad hardware support
- Automatic application update and rollback UI
- Production support guarantees

These capabilities remain part of the broader master plan but are intentionally deferred until the image and appliance foundation is proven.

## 11. Milestones

### M1 - Documentation Approved

- Phase plan reviewed
- Deployment RFC reviewed
- Architecture decision recorded
- Image build research questions recorded
- Release checklist defined

### M2 - Reproducible Base Image

- Selected image builder produces Raspberry Pi OS Lite 64-bit
- Image boots on target hardware
- Build records source revisions, inputs, and package versions
- No build-machine identity or secrets remain

### M3 - Pi-hole Appliance

- Pinned ARM64 Pi-hole artifact is embedded
- First boot imports and starts the container
- DNS answers explicit queries from another local device
- Pi-hole data persists across container recreation and reboot
- Unique administrator credential is generated

### M4 - Sovereign Local Addressing

- `sovereign.local` resolves through mDNS on tested clients
- Direct-IP fallback works
- `/dns/admin/` UI works through Nginx
- `/dns/api/` works through Nginx
- `/admin/*` and `/api/*` do not reach Pi-hole

### M5 - Release Candidate

- Fresh-flash tests pass using the published compressed artifact
- Interrupted first boot recovers safely
- Repeated reboot tests pass
- Resource usage and known limitations are documented
- Artifact checksum and manifest are published
- Router DNS configuration instructions are verified

## 12. Acceptance Criteria

Phase 01 is complete when:

- Raspberry Pi Imager can write the compressed artifact successfully.
- A Raspberry Pi 5 boots from a clean supported storage device.
- First boot completes without shell commands or package installation by the user.
- Pi-hole starts automatically and answers DNS queries on port 53.
- `http://sovereign.local/` redirects to `/dns/admin/` on tested mDNS clients.
- `http://sovereign.local/dns/admin/` provides the complete Pi-hole UI.
- Pi-hole UI login, logout, assets, redirects, and API calls work under `/dns/*`.
- Root `/admin/*` and `/api/*` remain unassigned to Pi-hole.
- Direct-IP access works when mDNS is unavailable.
- Every device receives unique identity, SSH host keys, and Pi-hole credentials.
- No credential or build-host identity is present in the downloadable image.
- Pi-hole configuration and data survive reboot.
- Pi-hole data and device secrets reside on the dedicated persistent data partition.
- A failed or interrupted first boot can resume safely.
- Pi-hole DHCP is disabled by default.
- The image contains an exact Pi-hole image digest, not a mutable tag.
- Build provenance, checksums, release notes, and known limitations are available.
- The user documentation explains stable IP and router DNS configuration.

## 13. Required Tests

- Image build reproducibility comparison
- Image decompression and size verification
- Fresh microSD flash and boot
- First boot with and without internet
- First boot power interruption at multiple steps
- Duplicate hostname behavior
- mDNS tests on representative clients
- Direct-IP fallback
- TCP and UDP DNS queries
- Pi-hole UI and API path-prefix regression suite
- Rejection of traversal or prefix-escape requests
- Secret and machine-identity scan of the final image
- Reboot and service-order tests
- Container recreation with persistent data
- Port-conflict detection
- Resource, storage, and temperature measurements

## 14. Open Questions

- Which exact Raspberry Pi OS Lite release will be pinned?
- Confirm whether `rpi-image-gen` v2.7.0 at commit `a7b6d4806183195f3efadb533f58c8e46393d057` remains the release pin after native-host and Pi 5 qualification.
- Which Docker Engine and Compose versions will be pinned?
- Revalidate the selected Pi-hole `2026.04.1` ARM64 digest at release review.
- Which upstream DNS provider is the default?
- Which client operating systems form the supported mDNS test matrix?
- What minimum storage size will be advertised?
- What stability-run duration is required?

## 15. Immediate Next Actions

1. Repeat the successful ARM64 engineering proof on a supported native ARM64 host, then flash and boot it on the target Pi 5.
2. Flash the generated Sovereign layer/storage image and complete the physical Proof 1-3 checklist on a Pi 5.
3. Test the exact exported artifact on real hardware, including direct-IP fallback and the supported mDNS client matrix.
4. Run the versioned release-candidate pipeline and qualify the downloaded bundle rather than an intermediate local image.
5. Review and accept the deployment RFC after recording hardware evidence.
6. Create the implementation plan for the next incomplete milestone only.
