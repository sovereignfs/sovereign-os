# rpi-image-gen Proof Build Report

Status: **Engineering build passed; hardware and release-host qualification pending**  
Build date: 2026-07-19

## 1. Outcome

The upstream minimal Raspberry Pi 5 ARM64 configuration completed filesystem,
SBOM, image, compression, manifest, and deploy stages. The generated image has
the expected boot and root partitions and is ready to be flashed for the
physical Pi 5 portion of Proof 1.

This run used a native ARM64 Linux kernel and userspace supplied by Docker
Desktop's LinuxKit VM on Apple Silicon. It is useful engineering evidence, but
it is not the supported native Debian/Raspberry Pi OS release host required by
the assessment. No claim is made yet that the image boots on a physical Pi 5.

## 2. Pinned Inputs

| Input | Value |
|---|---|
| Builder | Raspberry Pi `rpi-image-gen` |
| Release tag | `v2.7.0` |
| Commit | `a7b6d4806183195f3efadb533f58c8e46393d057` |
| Builder config | upstream `config/trixie-minbase.yaml` |
| Target | Raspberry Pi 5, ARM64, SD storage |
| Container base | `debian:trixie-slim` |
| Container base digest | `sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd` |
| Build OS | Debian GNU/Linux 13.6 (Trixie) |
| Build kernel/platform | Linux 6.12.54-linuxkit, aarch64 |
| Python | 3.13.5 |
| Toolchain mode | native |

The pin is stored in `image-builder/rpi-image-gen.version`. Release builds must
not replace it with a branch name or an unpinned checkout.

## 3. Execution

Run:

```bash
./scripts/build-rpi-image-gen-proof.sh
```

The script builds a privileged ARM64 proof container, checks the upstream
commit before building, executes the minimal upstream configuration, and copies
deploy artifacts plus evidence to the ignored
`build/rpi-image-gen-proof/` directory.

The first clean container build installed the build dependencies. On the final
corrected run, host support tool compilation took 39 seconds and `mmdebstrap`
root-filesystem generation took 46.57 seconds. These are engineering timings on
Docker Desktop and are not Pi 5 build-host benchmarks.

## 4. Container Compatibility Findings

Two issues in the v2.7.0 root execution path were found before filesystem
generation:

1. `bin/ns` uses `/bin/sh` but evaluates an exported function containing Bash
   `[[ ... ]]` syntax.
2. `_ns_setup` returns status 1 when no APT cache mount exists; combined with
   `set -e` in `bin/ns`, this exits before the requested command runs.

The proof container applies the narrow patch at
`image-builder/patches/v2.7.0-bin-ns-bash.patch`. The Docker build first runs
`git apply --check`, so drift fails closed. This patch is an adapter for the
privileged root container. A supported non-root native build uses the upstream
Podman/Bash path and must be tested without the patch.

An earlier attempt placed the work tree on a macOS bind mount. It was rejected
as an unsuitable design because a Linux root filesystem requires ownership,
device-node, xattr, and filesystem semantics that macOS cannot preserve. The
final build kept both source and work tree on Docker's Linux filesystem.

## 5. Generated Artifact

| Property | Result |
|---|---|
| Uncompressed image | `deb13-arm64-min.img` |
| Uncompressed size | 1,619,001,344 bytes (1.51 GiB) |
| Uncompressed SHA-256 | `111f2636837a868b545e70951a4278e17fc4caee8fade027fabc7e1d58d2b7ca` |
| Flash artifact | `deb13-arm64-min.img.zst` |
| Flash artifact size | 210,233,417 bytes |
| Flash artifact SHA-256 | `44717f459256e037388acadf50f5b4bb0f10dbe2d806fab9aaf04593640e5342` |
| IDP archive | `deb13-arm64-min-v2.7.0-dirty.tar.zst` |
| IDP archive SHA-256 | `41f3ee9f5c5d2f75ada24ac3615b0f5b1289864a80429318e6195fd6d479e68b` |
| Package count | 242 |
| SBOM provider | Syft 1.44.0 |

The `-dirty` version suffix is expected because the proof container applies the
documented compatibility patch after verifying the pinned upstream commit.

## 6. Partition Inspection

```text
Disklabel: DOS/MBR
Sector size: 512 bytes

Partition 1: start 16384, 212992 sectors, 104 MiB, bootable FAT32 (LBA)
             label BOOT, mounted at /boot/firmware
Partition 2: start 229376, 2932736 sectors, 1.4 GiB, Linux ext4
             label ROOT, mounted at /, expand-to-fit enabled
```

This passes the image-structure portion of Proof 1. It does not satisfy Proof 3:
the upstream minimal image has no persistent `/data` partition.

## 7. Remaining Qualification

Proof 1 remains open until all of the following are recorded:

- run the same pinned configuration on a supported native ARM64 Debian or
  Raspberry Pi OS host as a non-root user;
- flash `deb13-arm64-min.img.zst` with Raspberry Pi Imager;
- boot it on the target Raspberry Pi 5;
- verify console, Ethernet/Wi-Fi behavior, DHCP, SSH policy, reboot, and root
  filesystem expansion;
- record native-host build time, free-space peak, boot time, and hardware notes.

After that, proceed to Proof 2 (external Sovereign layer and hostname) and Proof
3 (boot, root, and persistent `/data` partitions). Docker and Pi-hole remain a
later proof as established by the assessment.

