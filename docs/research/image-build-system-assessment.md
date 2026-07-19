# Image Build System Assessment

**Status:** Concluded  
**Started:** 2026-07-19  
**Concluded:** 2026-07-19  
**Decision informed:** [RFC-0010](../rfcs/0010-raspberry-pi-image-deployment.md) and the M2 implementation plan

## 1. Question

Should the Phase 01 Raspberry Pi OS Lite image be generated with `pi-gen`, `rpi-image-gen`, or by modifying an already-published image?

## 2. Recommendation

Use **`rpi-image-gen`**, pinned to an exact released tag and source revision, as the Phase 01 image builder.

Use a native ARM64 build host running a supported Debian or Raspberry Pi OS release for the first proof build and release pipeline. Do not make cross-architecture QEMU or macOS-hosted container builds the supported release path until separately validated.

The recommendation remains conditional on a proof build that demonstrates:

- boot on the target Raspberry Pi 5;
- a boot, root, and persistent `/data` partition layout;
- custom Sovereign files and systemd units;
- embedded Pi-hole ARM64 OCI/Docker artifact;
- exported image writable by Raspberry Pi Imager;
- removal of build identity and secrets;
- acceptable repeat-build differences.

If that proof fails because of an unresolved `rpi-image-gen` defect, use `pi-gen` as the fallback for the POC and implement the data partition in a controlled post-image step. That is a fallback, not the preferred architecture.

## 3. Project Requirements

| Requirement | Importance |
| --- | --- |
| Raspberry Pi 5 boot support | Required |
| Raspberry Pi OS-compatible ARM64 userspace | Required |
| Flashable raw disk image | Required |
| Custom boot/root/data partition layout | Required |
| Persistent `/data` partition | Required before POC release |
| Custom packages, files, and systemd services | Required |
| Embedded pinned Pi-hole container artifact | Required |
| First-boot hooks | Required |
| Reproducible inputs and provenance | Required |
| Image inspection and CI integration | Required |
| SBOM and security evidence | Strongly desired |
| Future A/B root plus persistent data | Strategic requirement |
| Single-maintainer usability | Required |

## 4. Findings: pi-gen

[`pi-gen`](https://github.com/RPi-Distro/pi-gen) is the tool used to build official Raspberry Pi OS images and custom images derived from Raspberry Pi OS.

### Strengths

- It is the authoritative Raspberry Pi OS distribution builder.
- Its Stage 2 directly produces Raspberry Pi OS Lite.
- It has a long operating history and broad community familiarity.
- Custom stages can install package lists, run host scripts, run chroot scripts, apply patches, and export images.
- It exports `.img`, `.zip`, `.img.gz`, or `.img.xz` artifacts directly.
- It supports Docker-based builds on non-Debian hosts, subject to host kernel features and privileged operations.
- Raspberry Pi OS settings such as hostname, locale, first user, SSH, and Wi-Fi country are built into its configuration model.

### Weaknesses for Sovereign

- Its primary purpose is producing the Raspberry Pi OS distribution, not defining a product-specific disk/storage architecture.
- The normal model is stage-oriented shell customization rather than declarative product layers and image layouts.
- Adding a dedicated persistent data partition is not a documented first-class workflow. A pi-gen issue about adding a partition points toward `rpi-image-gen` as the tool more suited to such layouts.
- A custom `/data` partition would likely require maintaining export-stage or post-image partition logic outside the normal Lite-image path.
- Future A/B roots plus persistent data would require substantially more custom partition and boot integration.
- Its work directory can consume tens of gigabytes.
- Cross-architecture building depends on `binfmt_misc`, QEMU, loop devices, and privileged host integration.
- Reproducibility is not presented as a core declarative feature in the main workflow; package repositories and build timestamps still need explicit control.
- OCI embedding, OTA layouts, SBOM generation, and product-oriented layout examples are not central features.

### Fit

`pi-gen` is an excellent choice for a lightly customized Raspberry Pi OS Lite image with the standard two-partition layout. Sovereign is no longer in that category because the dedicated persistent partition is a Phase 01 requirement and A/B compatibility is an explicit strategic direction.

## 5. Findings: rpi-image-gen

[`rpi-image-gen`](https://github.com/raspberrypi/rpi-image-gen) is Raspberry Pi's newer builder for highly customized product and appliance images. Raspberry Pi describes it as an alternative to `pi-gen`, designed to provide granular control over filesystem construction and disk layout.

### Strengths

- Disk layout is a first-class concept defining partition tables, filesystems, image formats, and sizes.
- YAML configuration, composable layers, validation, and hooks separate product configuration from build-engine internals.
- It uses Raspberry Pi OS-compatible packages and firmware while permitting a smaller, purpose-built footprint.
- It supports bootable disk images, partitioned layouts, and filesystem archives.
- The repository contains an `ab_userdata` GPT layout and other layout examples, directly aligning with root A/root B/persistent-data direction.
- The repository contains official Docker-export and OCI-creation examples.
- The OCI example uses pinned Debian snapshot inputs and records build origin, supporting stronger provenance and repeatability.
- It contains an official OTA example that produces an update artifact and retains network configuration across A/B slot rotations. Sovereign will not adopt Raspberry Pi Connect as a dependency, but the example demonstrates that the builder is designed for OTA-capable layouts.
- External source directories can provide Sovereign-owned configurations and layers without modifying the upstream repository.
- It supports SBOM and CVE-report generation.
- It is designed for integration with external build systems and CI.
- It can integrate with Raspberry Pi secure-boot and provisioning tooling later.
- Current examples target Trixie/ARM64 and output images writable through Raspberry Pi Imager.

### Weaknesses and Risks

- It is newer and explicitly described as under active development.
- Config, layer, and image-layout interfaces may evolve more rapidly than `pi-gen` conventions.
- The supported build path is narrower: current documentation names native Debian Bookworm/Trixie ARM64 or Raspberry Pi OS ARM64 as the supported environment.
- Container and non-ARM64/QEMU builds may work but are not formally supported.
- Its use of `mmdebstrap` and private mount namespaces requires `CAP_SYS_ADMIN` or equivalent in containerized environments.
- It does not simply reproduce the official Raspberry Pi OS Lite artifact bit-for-bit; Sovereign must define and own its appliance profile.
- A single maintainer must learn its layer metadata, configuration, hooks, and image-layout model.
- Selecting a moving `master` revision would be risky; a released tag and commit must be pinned.
- The available OTA example is tied to experimental Raspberry Pi Connect functionality and does not replace Sovereign's independent update-system design.

### Fit

`rpi-image-gen` aligns directly with Sovereign's product needs: explicit partition layout, product-owned layers, embedded container artifacts, audit output, and future A/B plus user data. These are not incidental customizations; they are central to the project architecture.

## 6. Findings: Modify a Published Raspberry Pi OS Image

This approach would download an official Raspberry Pi OS Lite image, attach it through loop devices, enlarge or repartition it, install files, and export it again.

### Strengths

- Fastest path to an initial familiar Raspberry Pi OS userspace.
- Starts from a specific published artifact with an upstream checksum.
- Avoids constructing the base filesystem from package repositories.

### Weaknesses

- Custom partition creation and filesystem movement become bespoke shell logic.
- Package installation inside a modified image still needs chroot/QEMU and repository pinning.
- Image shrinking, expansion, machine-identity sanitization, and repeatability are project-owned.
- Provenance becomes a combination of upstream image plus opaque transformations.
- Future A/B layout migration remains difficult.
- It risks becoming a one-off build script rather than a maintainable product definition.

### Fit

Suitable only as an emergency prototype or diagnostic control. It should not become the supported release pipeline.

## 7. Comparison

| Criterion | pi-gen | rpi-image-gen | Modify published image |
| --- | --- | --- | --- |
| Official Raspberry Pi project | Yes | Yes | Uses official artifact |
| Produces official Raspberry Pi OS | Yes | No; produces product images from compatible packages | Starts from it |
| Raspberry Pi OS Lite path | Direct Stage 2 | Must define suitable profile | Direct base artifact |
| Product-specific partition layouts | Possible with custom work | First-class | Fully custom scripting |
| Dedicated `/data` partition | Custom export/post-image work | Strong fit | Custom repartitioning |
| Future A/B + data | High custom effort | Existing layout direction/examples | High custom effort |
| Custom package/file hooks | Strong | Strong and layered | Possible but bespoke |
| OCI/container examples | Not central | Official examples | Bespoke |
| Reproducible snapshot examples | Not central | Official examples | Partial base provenance only |
| SBOM/CVE support | External work | Built-in direction | External work |
| Tool maturity | Highest | Newer, active development | Script depends on us |
| Supported host flexibility | Debian; Docker possible elsewhere | Native ARM64 Debian/RPi OS preferred | Linux with loop/chroot tools |
| Best match for Sovereign | Acceptable fallback | Recommended | Not recommended |

## 8. Why the Recommendation Changed from the Initial Lean Toward pi-gen

Before the update architecture was documented, Sovereign looked like a lightly customized Raspberry Pi OS Lite image. `pi-gen` was the natural default for that requirement.

The accepted design now requires a separate persistent data partition in Phase 01 and intends to evolve toward A/B root filesystems. It also embeds an OCI application artifact and values SBOM/provenance output. Those requirements make disk layout and product-layer composition primary concerns, which is exactly the distinction Raspberry Pi makes between `rpi-image-gen` and `pi-gen`.

## 9. Build-Host Recommendation

For the first supported proof and release builds:

```text
Architecture: ARM64
Host OS: supported current Raspberry Pi OS 64-bit or Debian ARM64
Builder: pinned rpi-image-gen release tag and commit
Execution: native host, not QEMU
Storage: fast local Linux filesystem with documented free-space requirement
```

A dedicated Raspberry Pi 5 can be used as the initial supported builder if no ARM64 CI host is available. Build time and storage usage must be measured. A cloud or self-hosted ARM64 CI runner may follow after the local proof succeeds.

macOS is not a supported native build host because the tool relies on Linux namespaces, mounts, `mmdebstrap`, and image/filesystem utilities. Development may occur on macOS, but release builds should run in the documented Linux/ARM64 environment.

## 10. Pinning Policy

The proof build must record:

- `rpi-image-gen` release tag and commit SHA;
- config and layer revisions from this repository;
- Debian/Raspberry Pi package sources and snapshot information where available;
- `SOURCE_DATE_EPOCH` policy;
- target device class and architecture;
- image layout definition;
- embedded Pi-hole OCI digest;
- build-host OS and architecture;
- output manifest, checksum, and tool-generated origin/SBOM data.

Do not build releases from an unpinned `master` checkout.

## 11. Proof-Build Plan

### Proof 1: Minimal Boot

- Pin a released `rpi-image-gen` version.
- Build its supported minimal ARM64 configuration.
- Flash with Raspberry Pi Imager.
- Boot on the target Pi 5.
- Record build time, artifact size, first boot, network, and console behavior.

Engineering update (2026-07-19): v2.7.0 at commit
`a7b6d4806183195f3efadb533f58c8e46393d057` produced the minimal ARM64 image in
an ARM64 Linux Docker environment. See the
[proof-build report](rpi-image-gen-proof-build-report.md). Physical Pi 5 boot
and a supported native ARM64 host run remain required before Proof 1 passes.

### Proof 2: Sovereign Layer

- Add an external Sovereign config and layer.
- Set hostname to `sovereign`.
- Add one file and one systemd oneshot service.
- Verify the upstream repository remains unmodified.

Engineering update (2026-07-19): the external layer builds with hostname
`sovereign`, a release marker, and an enabled systemd oneshot service. See the
[Sovereign layer and storage proof report](sovereign-layer-storage-proof-report.md).
Physical boot and first-boot execution remain to be verified.

### Proof 3: Storage Layout

- Define boot, root, and persistent data partitions.
- Mount data at `/data`.
- Verify data persistence across reboot.
- Verify the root filesystem does not become authoritative for `/data/sovereign`.

Engineering update (2026-07-19): the generated image contains separate boot,
root, and DATA partitions; DATA is mounted at `/data`, seeded with
`/data/sovereign`, and marked expand-to-fit. Physical reboot and update
persistence tests remain to be verified.

### Proof 4: OCI Artifact

- Embed a small ARM64 OCI test artifact.
- Import it on first boot.
- Verify its digest.
- Replace it with the pinned Pi-hole artifact only after the mechanism passes.

Engineering update (2026-07-19): a deterministic static ARM64 OCI test image
is embedded in the appliance, verified at first boot, and was successfully
imported and executed using the build host's ARM64 Docker runtime. See the
[embedded OCI artifact proof report](embedded-oci-artifact-proof-report.md).
On-device import remains assigned to the Docker installation milestone so the
base image does not acquire a throwaway Podman dependency.

### Proof 5: Repeatability

- Build twice in clean equivalent environments.
- Compare partition tables, filesystem trees, package manifests, SBOMs, and hashes.
- Classify expected differences such as filesystem UUIDs or timestamps.
- Decide whether the release claim is reproducible inputs/content or byte-for-byte output.

## 12. Decision Impact

Update [RFC-0010](../rfcs/0010-raspberry-pi-image-deployment.md) to make `rpi-image-gen` the recommended builder pending proof completion. The first implementation plan should cover Proofs 1-3 only; Docker and Pi-hole belong in the following milestone.

The future OTA framework assessment should reuse `rpi-image-gen`'s A/B/user-data layouts as evidence, but must not assume that Raspberry Pi Connect is acceptable. Sovereign's core local update mechanism must not require a proprietary hosted service.

## 13. Sources

- [Raspberry Pi introduction to rpi-image-gen](https://www.raspberrypi.com/news/introducing-rpi-image-gen-build-highly-customised-raspberry-pi-software-images/)
- [rpi-image-gen repository and build requirements](https://github.com/raspberrypi/rpi-image-gen)
- [rpi-image-gen examples](https://github.com/raspberrypi/rpi-image-gen/tree/master/examples)
- [rpi-image-gen image layouts](https://github.com/raspberrypi/rpi-image-gen/tree/master/image)
- [pi-gen repository and build model](https://github.com/RPi-Distro/pi-gen)
- [Raspberry Pi Imager custom-image distribution](https://www.raspberrypi.com/news/how-to-add-your-own-images-to-imager/)
