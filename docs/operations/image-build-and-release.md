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
- whether to create a draft GitHub release.

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

## Bundle Contents

```text
SHA256SUMS
create-imager-manifest.py
release-manifest.json
sovereign-os-<version>-rpi5-arm64.img.zst
sovereign-os-<version>-rpi5-arm64.packages.tsv.zst
sovereign-os-<version>-rpi5-arm64.provenance.json
sovereign-os-<version>-rpi5-arm64.sbom.zst
```

The helper creates a local Raspberry Pi Imager catalog that enables Wi-Fi and
SSH customization for this third-party image. Follow the
[Imager provisioning guide](raspberry-pi-imager-provisioning.md); loading only
the raw image through **Use custom** does not enable customization in Imager 2.

`release-manifest.json` records:

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

When `publish_draft_release` is selected, the workflow creates `v<version>` as a draft GitHub release targeting the exact built commit and uploads the complete bundle. Draft status is mandatory at this stage: the artifact has not yet passed Raspberry Pi 5 qualification.

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
