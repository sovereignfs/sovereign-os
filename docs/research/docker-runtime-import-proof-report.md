# Docker Runtime and First-Boot Import Proof Report

Status: **Proof passed and superseded by the embedded Pi-hole image; Pi 5 boot execution pending**
Build date: 2026-07-19

## Outcome

The Sovereign appliance image now contains a pinned Docker Engine and Compose
installation from Docker's official Debian repository. Docker and containerd
wait for the dedicated DATA filesystem and keep their persistent state under
`/data`, so a future OS-root replacement does not discard images, containers,
or volumes.

The proof implementation used `sovereign-oci-import.service` to wait for the
embedded-artifact verification and Docker daemon, load the archive by immutable
manifest digest, and run an isolated ARM64 smoke test. That synthetic service
and artifact have since been removed from the current image and replaced by the
equivalent Pi-hole-specific verification and import units.

## Pinned Runtime

| Package | Version |
|---|---|
| `docker-ce` | `5:29.6.2-1~debian.13~trixie` |
| `docker-ce-cli` | `5:29.6.2-1~debian.13~trixie` |
| `containerd.io` | `2.2.6-1~debian.13~trixie` |
| `docker-buildx-plugin` | `0.35.0-1~debian.13~trixie` |
| `docker-compose-plugin` | `5.3.1-1~debian.13~trixie` |

The build uses Docker's signed Debian 13/Trixie ARM64 repository and verifies
the downloaded signing key against a pinned SHA-256 before apt uses it. The
runtime packages are placed on apt hold; appliance updates must deliberately
change the recorded pins and pass image qualification.

Docker officially supports Debian 13 and ARM64. Its documentation also notes
that Docker Engine 29 uses the containerd image store on fresh installations,
and that `data-root` does not relocate containerd's separate content store.
Therefore this image configures both locations:

```text
/data/docker       Docker daemon data-root
/data/containerd   containerd root
```

Sources:

- [Install Docker Engine on Debian](https://docs.docker.com/engine/install/debian/)
- [Docker daemon data directory](https://docs.docker.com/engine/daemon/#daemon-data-directory)

## Boot Ordering and Security Boundary

- `containerd.service` and `docker.service` require `/data` to be mounted.
- Both persistent directories are seeded into the DATA filesystem at image
  creation and defensively created before daemon startup.
- Docker listens on its default local Unix socket only; no TCP daemon endpoint
  is configured.
- The image's `pi` user is not added to the root-equivalent `docker` group.
- The proof container runs with `--network none`, `--read-only`, and `--rm`.
- Docker uses the bounded `local` logging driver and live restore.

## Build Evidence

The native ARM64 engineering build completed successfully. The package
manifest exported from that exact root filesystem contains all five pinned
versions. Extracted Docker, containerd, and import-unit configurations match
the repository inputs byte for byte.

Generated local artifacts:

| Artifact | Result |
|---|---|
| Raw image | 2.98 GiB before compression |
| Flashable image | `build/sovereign-image/deploy/sovereign-proof.img.zst` |
| Flashable image size | 304 MiB |
| Flashable image SHA-256 | `ca3ef4751c9bfb52472023d8668a18f631cc8c2a4c6e14af141a9a904c0a6cfd` |
| IDP release bundle | `build/sovereign-image/deploy/sovereign-proof-v2.7.0-dirty.tar.zst` |
| IDP release bundle size | 605 MiB |

These artifacts are local, ignored engineering outputs and are not a published
release.

## Remaining Qualification

The build environment cannot boot systemd with the Raspberry Pi kernel and
real DATA partition. A Raspberry Pi 5 test must still verify:

1. Docker and containerd start only after `/data` mounts.
2. Both daemons write persistent state to the configured DATA paths.
3. The import unit creates `oci-import-ready` and the proof container exits
   successfully.
4. The image remains present after reboot.
5. Removing only the marker causes safe revalidation, while removing only the
   image causes a safe reload.

The synthetic proof artifact has now been replaced by the exact pinned official
Pi-hole ARM64 artifact. The next implementation step is the idempotent Pi-hole
configuration and container-start service.
