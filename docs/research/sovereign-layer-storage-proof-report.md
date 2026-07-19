# Sovereign Layer and Storage Proof Report

Status: **Engineering proofs passed; physical Pi 5 validation pending**  
Build date: 2026-07-19

## Outcome

The external Sovereign source tree built successfully with the pinned
`rpi-image-gen` v2.7.0 builder. The upstream checkout remained product-agnostic:
the hostname, marker, service, and partition layout all come from
`image-builder/sovereign/`.

This build completes the image-structure portions of Proof 2 and Proof 3 from
the [image-builder assessment](image-build-system-assessment.md). Boot,
first-boot service execution, expansion, reboot, and destructive-update
persistence still require a physical Raspberry Pi 5.

## Proof 2: External Sovereign Layer

Verified in the generated root partition:

- hostname is `sovereign`;
- `/etc/sovereign-release` identifies the image-builder proof;
- `/usr/lib/sovereign/proof-init` is executable;
- `sovereign-proof.service` is installed and enabled for
  `multi-user.target`;
- the service requires `/data` and creates
  `/data/sovereign/proof-ready` on first boot.

The layer and service are deliberately minimal. They prove external product
composition and service enablement; they do not install Docker, Pi-hole, mDNS,
or the Sovereign dashboard.

## Proof 3: Persistent Storage Layout

The generated 2,155,872,256-byte MBR image contains:

| Partition | Size | Type | Purpose |
|---|---:|---|---|
| 1 | 104 MiB | bootable FAT32 | firmware, kernel, initramfs |
| 2 | 1.4 GiB | ext4 | root operating system |
| 3 | 512 MiB initial | ext4, label `DATA` | persistent application data |

The root image contains:

```text
/dev/disk/by-slot/system / ext4 rw,relatime,errors=remount-ro,commit=30 0 1
/dev/disk/by-slot/boot /boot/firmware vfat defaults,rw,noatime,errors=remount-ro 0 2
/dev/disk/by-label/DATA /data ext4 defaults,rw,noatime 0 2
```

The DATA filesystem is seeded with `/sovereign`. The provisioning map marks the
final DATA partition `expand-to-fit`; the root partition is not marked for
expansion. This preserves the intended boundary between replaceable operating
system content and authoritative application data.

## Artifact

| Property | Result |
|---|---|
| Flash artifact | `sovereign-proof.img.zst` |
| Uncompressed size | 2,155,872,256 bytes (2.01 GiB) |
| Uncompressed SHA-256 | `8bc56ac14f7c45f54529b4e1ff1a6a217d913671975b99c8336db0af79fa46b2` |
| Compressed SHA-256 | `d86b6bd8cd3a958214f2fad79b92eda930813b8fa0deb7fe87d6c56036a450db` |
| Root filesystem block size | 16 KiB |
| DATA filesystem block size | 16 KiB |

Local ignored artifacts are written to `build/sovereign-image/deploy/`.

## Build

```bash
./scripts/build-sovereign-image.sh
```

The builder validates both external layer metadata and the generated Image
Description Provisioning document. It also emits compressed partition images,
SBOM, package manifest, configuration, image metadata, and an IDP archive.

## Remaining Physical Tests

1. Flash `sovereign-proof.img.zst` to a microSD card.
2. Boot on a Raspberry Pi 5 and confirm the system announces hostname
   `sovereign` through DHCP.
3. Confirm `/data` is mounted from the DATA partition and has expanded to use
   the remaining card capacity.
4. Confirm `sovereign-proof.service` is active and
   `/data/sovereign/proof-ready` exists.
5. Write a unique test file under `/data/sovereign`, reboot, and verify it.
6. Rebuild or reflash only the boot/root partitions, leaving DATA untouched,
   and verify the unique test file remains.

Only after these tests pass should Proof 2 and Proof 3 be marked complete.

