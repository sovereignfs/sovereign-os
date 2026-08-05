# Image Build and Release Process

**Status:** Implemented for engineering candidates; hardware qualification pending

## Purpose

The repository has two separate automation paths:

- `Validate` runs lightweight source, shell, and release-bundler checks for pull requests and pushes to `main`.
- `Build Raspberry Pi image` is manually dispatched for a versioned ARM64 engineering image candidate.

Manual dispatch is intentional. Image publication must not occur merely because a commit or tag exists.

## Candidate Build

In GitHub Actions, open **Build Raspberry Pi image**, choose **Run workflow**, and provide:

- a SemVer value without a leading `v`, such as `0.1.0-preview.1`;
- the `preview` or `stable` channel;
- whether to create a draft GitHub release;
- whether to build an unsigned installed-device *appliance* update
  candidate (`build_update_candidate`, plus its source-version bounds and
  key id);
- whether to build an unsigned *base-OS* update candidate
  (`build_base_os_candidate`, plus its own source-version bounds and key
  id) — see [Base-OS Candidate Build](#base-os-candidate-build) below.

The job runs on GitHub's ARM64 Ubuntu runner, confirms the host architecture, invokes the same Sovereign image-build script used locally, and packages the result. ARM64 hosted runners are currently a GitHub public-preview capability. This makes the workflow an engineering-candidate builder, not by itself a qualified Sovereign release environment.

For a local candidate after running `./scripts/build-sovereign-image.sh`:

```bash
source_date_epoch=$(git show -s --format=%ct HEAD)
./scripts/create-release-bundle.py \
  --deploy-dir build/sovereign-image/deploy \
  --output-dir build/release \
  --version 0.1.0-preview.1 \
  --channel preview \
  --source-revision "$(git rev-parse HEAD)" \
  --source-date-epoch "$source_date_epoch"
```

The output directory must be empty. The command fails rather than mixing files from different builds.

The workflow uploads the clean-image release bundle as
`sovereign-os-<version>-rpi5-arm64`. If installed-device update packaging is
enabled, it separately uploads `sovereign-update-<version>-rpi5-arm64`. If
base-OS candidate packaging is enabled, it separately uploads
`sovereign-base-os-<version>-rpi5-arm64`. Operators preparing an
installed-device update therefore do not need to download the much larger
flashable-image artifact.

## Base-OS Candidate Build

[RFC-0016](../rfcs/0016-full-base-os-updates.md) added a second, independent
update path: a signed, health-gated **base-OS** (root filesystem) update
delivered through the Raspberry Pi `tryboot` A/B mechanism, distinct from
the appliance (`build_update_candidate`) update candidate described above.
`sovereign-update stage-base-os` writes it to the currently inactive slot;
`trial-base-os`/`commit-base-os` boot into it behind a health gate before
it becomes permanent.

Producing a base-OS candidate requires images built under the A/B tryboot
layout (`sovereign-ab-proof.yaml`), not the plain image the primary build
above targets — a `boot.vfat`/`root.ext4` pair from the plain image has no
tryboot partitions to stage onto and cannot be used for this. Selecting
`build_base_os_candidate` therefore runs a **second, complete image build**
against the A/B config, roughly doubling the job's runtime; leave it off
unless you specifically need a base-OS candidate out of this run.

The raw `boot.vfat`/`root.ext4` genimage produces as an intermediate step
(before its own android-sparse conversion, which is all `rpi-image-gen`'s
deploy step normally exports) are pulled out of the build container by
`scripts/build-sovereign-image.sh` into `evidence/base-os/`, then packaged
by `scripts/create-base-os-release.py` — the same unsigned-manifest,
signed-separately-offline shape as the appliance update candidate below,
governed by the same [ADR-0006](../adrs/0006-production-signing-key-custody.md)
key-custody boundary.

## Bundle Contents

```text
SHA256SUMS
create-imager-manifest.py
image-manifest.json
sovereign-os-<version>-rpi5-arm64.img.zst
sovereign-os-<version>-rpi5-arm64.packages.tsv.zst
sovereign-os-<version>-rpi5-arm64.provenance.json
sovereign-os-<version>-rpi5-arm64.sbom.zst
```

Named `image-manifest.json`, deliberately distinct from the signed update
system's `release-manifest.json`/`release-manifest.sig`
([RFC-0014](../rfcs/0014-appliance-update-system.md),
[update/README.md](../../update/README.md)) — the two are unrelated
documents with unrelated schemas, and earlier both being named
`release-manifest.json` caused a real collision when both were attached to
the same GitHub release (see the
[update discovery positive-path qualification report](../research/update-discovery-positive-path-qualification-report.md)).

The helper creates a local Raspberry Pi Imager catalog that enables Wi-Fi and
SSH customization for this third-party image. Follow the
[Imager provisioning guide](raspberry-pi-imager-provisioning.md); loading only
the raw image through **Use custom** does not enable customization in Imager 2.

`image-manifest.json` records:

- release version, channel, and source-derived timestamp;
- source repository and full Git revision;
- target board, architecture, storage type, and OS base;
- pinned `rpi-image-gen` tag and revision;
- Pi-hole repository, version, platform, and immutable digest;
- resolved Docker, Compose, Nginx, Avahi, and mDNS package versions;
- every payload filename, byte size, and SHA-256 digest;
- the remaining qualification gates.

Validate the complete bundle from inside its directory:

```bash
sha256sum --check SHA256SUMS
```

## Draft Publication

When `publish_draft_release` is selected, the workflow creates `v<version>` as a draft GitHub release targeting the exact built commit and uploads the image bundle. Draft status is mandatory at this stage: the artifact has not yet passed Raspberry Pi 5 qualification.

If `build_update_candidate` was also selected, the workflow additionally
uploads the *unsigned* update-candidate `release-manifest.json` and its
update bundle to the same draft release. CI never holds the signing key, so
this alone does not make the release discoverable by
`sovereign-update check` — that requires both `release-manifest.json` *and*
`release-manifest.sig` to be present, and the signature only exists once an
operator signs the manifest offline (`scripts/sign-update-manifest.py`,
same as every other qualification in this project) and uploads the
resulting `.sig` as an additional release asset before publishing.

If `build_base_os_candidate` was also selected, the workflow additionally
uploads the *unsigned* `base-os-manifest.json` and its boot/root artifacts
to the same draft release, under the same offline-signing gap described
above (`base-os-manifest.sig` instead of `release-manifest.sig`).

Before making a release public:

1. Download the workflow artifact or draft-release assets to a clean machine.
2. Verify `SHA256SUMS`.
3. Complete every applicable item in the [image release checklist](image-release-checklist.md) using the downloaded artifact.
4. Record the native ARM64 host and physical Pi 5 results.
5. Update release notes and known limitations.
6. Obtain project-owner approval.
7. Publish the existing draft; do not rebuild a different artifact after qualification.

## Trust Boundary

The current bundle is checksummed but not cryptographically signed. GitHub permissions and draft-release controls protect publication operationally, but they are not the final artifact trust model. Signing, key custody, verification, rotation, and revocation belong to RFC-0014/U1 and must be approved before installed-device update artifacts are trusted.

## Sources

- [GitHub-hosted runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [GitHub Actions workflow artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)
