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
