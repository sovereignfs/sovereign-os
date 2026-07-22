# Raspberry Pi image proof builder

This directory pins the builder used by the `rpi-image-gen` proof. The supported
release environment remains a native ARM64 Debian or Raspberry Pi OS host, as
specified in the image-builder assessment. `Dockerfile.proof` is an engineering
adapter for running the same ARM64 userspace on Apple Silicon; it is not a
qualified release environment.

Run from the repository root:

```bash
./scripts/build-rpi-image-gen-proof.sh
```

The script builds the upstream `trixie-minbase.yaml` configuration and copies
deploy artifacts plus build metadata to the ignored
`build/rpi-image-gen-proof/` directory. It does not copy the complete chroot,
because Linux device nodes and other special files cannot be exported to a
macOS filesystem. It intentionally retains the named container after the run so
failed build evidence can be inspected before removal.

The privileged container is required for Linux namespaces, mounts, ownership,
device-node, and filesystem-image operations. The checkout and build work stay
inside Docker's Linux filesystem; do not put the root filesystem work tree on a
macOS bind mount.

## Compatibility patch

The pinned v2.7.0 `bin/ns` script uses `/bin/sh` while evaluating the exported
`_ns_setup` Bash function when run as root. That function also returns status 1
when no APT cache mount needs cleanup, which combines with `set -e` to stop the
root path before its command is executed. The container applies the narrow,
checksum-checked patch in `patches/v2.7.0-bin-ns-bash.patch`. Native non-root
builds use the upstream Podman/Bash path and do not need this adapter patch.

## Qualification boundary

A successful container build proves ARM64 dependency resolution, layer
assembly, root-filesystem generation, and image generation. It does not prove
Pi 5 boot, networking, console behavior, or release-host support. Those checks
must be completed on a physical Pi 5 and a supported native ARM64 build host.

## Sovereign layer and storage image

Build the external Sovereign layer and its boot/root/DATA layout with:

```bash
./scripts/build-sovereign-image.sh
```

Release builds must provide the version and channel so the installed image and
published artifact identity cannot diverge:

```bash
SOVEREIGN_VERSION=0.1.0-preview.6 \
SOVEREIGN_CHANNEL=preview \
./scripts/build-sovereign-image.sh
```

The build exports the embedded `/etc/sovereign-release` as evidence, and release
packaging fails if it does not match the requested release identity.

The flash artifact is written to the ignored path
`build/sovereign-image/deploy/sovereign-proof.img.zst`. Product-owned inputs
live under `image-builder/sovereign/`; the pinned upstream checkout is not
modified beyond the documented proof-container compatibility patch.

The same build creates a deterministic ARM64 OCI proof archive, embeds it under
`/usr/lib/sovereign/artifacts/`, and exports a copy to
`build/sovereign-image/evidence/oci/`. The appliance verifies its checksum and
layout on first boot. Runtime import into the appliance is intentionally left
for the Docker installation milestone.

## Release candidate bundle

After a successful Sovereign image build, package the flash image and its build
evidence with `scripts/create-release-bundle.py`. The script creates versioned
payload names, a machine-readable release manifest, and `SHA256SUMS` in an
empty output directory. The complete operator flow and the distinction between
an engineering candidate and a hardware-qualified release are documented in
`docs/operations/image-build-and-release.md`.

The release bundle also includes `create-imager-manifest.py`. It produces a
local Raspberry Pi Imager catalog for the versioned `.img.zst`, enabling the
user to supply Wi-Fi and SSH settings before flashing. See
`docs/operations/raspberry-pi-imager-provisioning.md` for the complete flow and
the supported first-boot configuration subset.
