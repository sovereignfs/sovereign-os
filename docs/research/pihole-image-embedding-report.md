# Pi-hole Image Embedding Report

Status: **ARM64 artifact pin, embedding, and local import passed; Pi 5 boot import pending**
Build date: 2026-07-19

## Outcome

The synthetic OCI proof image has been removed from the current appliance
build. Sovereign OS now embeds the official Pi-hole `2026.04.1` Linux ARM64
image for an offline first boot.

The build resolves no mutable tag. It downloads the selected platform manifest
by immutable digest, preserves all upstream blob digests, creates a normalized
OCI Image Layout archive, and records an archive checksum. The appliance first
verifies that archive and its expected manifest before asking Docker to import
it.

## Selected Artifact

| Property | Value |
|---|---|
| Repository | `docker.io/pihole/pihole` |
| Release tag | `2026.04.1` |
| Multi-platform index digest | `sha256:1c32c36b862a12762656b6471c854cebc01fe945639ba3a893611337c2c95e99` |
| Selected platform | `linux/arm64` |
| ARM64 manifest digest | `sha256:0b26b891bddc2af2cea282201d47ad92e54a53d4dd45d52e377600434d3ebb47` |
| Embedded archive | `/usr/lib/sovereign/artifacts/pihole-arm64.oci.tar` |
| Embedded archive size | approximately 41 MiB |
| Embedded archive SHA-256 | `665525a5493d0e669b8e8c8d6c9d74d85d078d69050efe387b14adc49f01e85d` |

The release was selected from the official Pi-hole Docker release stream. The
April release line includes disclosed security fixes, and `2026.04.1` is its
subsequent bug-fix release. Sources:

- [Official docker-pi-hole releases](https://github.com/pi-hole/docker-pi-hole/releases/tag/2026.04.1)
- [Official Pi-hole Docker configuration](https://docs.pi-hole.net/docker/configuration/)

## Build and Import Flow

At build time:

1. Skopeo fetches `pihole/pihole` by the ARM64 manifest digest.
2. The content is written as an OCI Image Layout while preserving upstream
   digests.
3. The layout is archived with fixed ownership, ordering, and timestamps.
4. SHA-256 metadata is stored beside the archive.

At first boot:

1. `sovereign-pihole-artifact.service` verifies the archive checksum, OCI
   structure, and pinned manifest blob.
2. `sovereign-pihole-import.service` waits for Docker and the DATA mount.
3. Docker loads the local archive without contacting a registry.
4. The importer resolves the immutable digest, applies the human-readable
   `pihole/pihole:2026.04.1` tag, and confirms `linux/arm64`.
5. Import evidence is written atomically under `/data/sovereign`.

Both services are idempotent. If persistent Docker state and the completion
marker remain present, later boots only restore the expected tag.

## Verification Evidence

The complete native ARM64 appliance build passed. The exact archive exported
from that build was then independently checked:

```text
pihole-arm64.oci.tar: OK
Loaded image: pihole/pihole:2026.04.1
linux/arm64 docker-pi-hole 2026.04.1
```

The normalized build produced:

| Artifact | Result |
|---|---|
| Flashable image | `build/sovereign-image/deploy/sovereign-proof.img.zst` |
| Compressed size | 345 MiB |
| Flashable image SHA-256 | `f9afaf63a36777012d6ab7b0500454b048ad8e48613427ff09c10820920732ac` |

The build exporter now clears its ignored deploy and evidence directories
before copying a result, preventing artifacts from an older milestone from
being mistaken for current evidence.

## Acceptance Boundary

This milestone proves artifact selection, supply-chain pinning, deterministic
packaging, offline embedding, and Docker import compatibility. It deliberately
does not start Pi-hole yet.

The next milestone must:

1. generate a device-local administrator password and define its delivery
   mechanism;
2. materialize persistent `/etc/pihole` storage under `/data`;
3. select upstream DNS and listening-mode defaults;
4. claim TCP and UDP port 53 safely;
5. start the pinned container and wait for DNS and HTTP health;
6. prove container recreation and reboot persistence.

Physical Pi 5 execution of both import units remains required before release
qualification.
