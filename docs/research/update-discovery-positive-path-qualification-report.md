# Update Discovery Positive-Path Qualification Report

**Date:** 2026-07-31

**Hardware:** Raspberry Pi 5 Model B Rev 1.1, running `0.1.0-preview.14`

**Status:** `sovereign-update check` qualified against a real, live, publicly
published GitHub release — the "update found" path, not just the
"nothing found" path already covered in
[docs/research/prune-and-rotate-trust-hardware-qualification-report.md](prune-and-rotate-trust-hardware-qualification-report.md)
and repeated live checks throughout RFC-0015's implementation.

## Purpose

Every prior verification of `sovereign-update check` — 12 unit tests and
several runs against the real live GitHub API — could only prove the
*negative* path, because no non-draft release had ever been published for
this project. This campaign closes that gap: build a real release
candidate, sign it, publish it for real (non-draft, publicly visible), and
confirm `check` actually discovers, verifies, and reports it correctly
against live data.

## A real gap found along the way

Attaching the signed update-candidate manifest to the draft release
surfaced a genuine, previously-undiscovered bug in
`.github/workflows/build-image.yml`: the "Publish draft release" step only
uploads `build/release/*` (the image's own build-provenance bundle, which
happens to also be named `release-manifest.json`); it never uploads
`build/update-release/*` (the actual signed update-candidate manifest and
bundle), even when `build_update_candidate: true`. As things stood before
this campaign, **no update candidate could ever have been discovered via a
real GitHub release**, regardless of `sovereign-update check`'s own
correctness — the file it looks for was never being published in the first
place. This was worked around manually for this one release (see Method);
the underlying workflow gap and filename collision are now fixed (see
Recommendation) — the image-provenance file was renamed to
`image-manifest.json`, and the workflow now conditionally uploads
`build/update-release/*` when `build_update_candidate` is set.

## Method

1. Built `0.1.0-preview.15` as a draft GitHub release via the standard
   `build-image.yml` workflow, with `build_update_candidate: true`
   (`update_source_minimum: 0.1.0-preview.14`).
2. Deleted the colliding `release-manifest.json` (image-provenance) asset
   from that one draft release.
3. Generated an ephemeral Ed25519 key (`preview-checktest`) and signed the
   real update-candidate manifest downloaded from the workflow's own build
   artifact — the same `scripts/sign-update-manifest.py` used throughout
   this project's qualification history, not a special test-only path.
4. Uploaded the signed manifest, its detached signature, and the real
   42.6 MB update bundle to the release under their canonical names
   (`release-manifest.json`, `release-manifest.sig`,
   `sovereign-update-0.1.0-preview.15-rpi5-arm64.tar.zst`).
5. Published the release (`draft: false`) — confirmed publicly visible via
   an unauthenticated call to the exact same
   `api.github.com/repos/sovereignfs/sovereign-os/releases` endpoint
   `check` itself uses.
6. On the device (still running the real, shipped `0.1.0-preview.14`):
   manually installed only the `preview-checktest` public key as a trust
   entry (matching every prior qualification session's private-key-free
   pattern), deployed the `check`-capable script (not yet part of any
   shipped image), and ran `sovereign-update check` for real.

## Result

```json
{
  "status": "update_available",
  "current_version": "0.1.0-preview.14",
  "available_version": "0.1.0-preview.15",
  "channel": "preview",
  "notes_url": "https://github.com/sovereignfs/sovereign-os/releases/tag/v0.1.0-preview.15",
  "reboot_required": false,
  "error": null
}
```

Correct in every field, sourced entirely from the real GitHub API and the
real signed manifest — no test fixture involved. `sovereign-update status`
correctly surfaced the same result as `update_check`.

## Cleanup

The trust key and the deployed script were both removed/reverted from the
device; the on-device `sovereign-update` binary's SHA-256 was confirmed to
match the original shipped `0.1.0-preview.14` build exactly, and full
health/failed-unit checks passed afterward. The published `v0.1.0-preview.15`
release itself, and its signing key, are left as an open decision for the
project owner — see Recommendation.

## Recommendation

Two follow-ups were identified; the first is now done.

1. **Fix the workflow gap. Done.** `build-image.yml`'s release-publish
   step now conditionally uploads `build/update-release/*` alongside
   `build/release/*` when `build_update_candidate` is set. The filename
   collision on `release-manifest.json` is resolved by renaming the
   image-provenance file to `image-manifest.json`
   (`scripts/create-release-bundle.py`), since `release-manifest.json`/
   `.sig` is the long-established, widely-referenced name for the *signed
   update* manifest throughout this codebase, tests, and documentation,
   not the other way around. The uploaded update-candidate manifest is
   still unsigned (CI never holds the signing key); an operator must sign
   it offline and upload the resulting `.sig` before a release becomes
   discoverable by `check`. Re-validating this end-to-end through the
   normal workflow (rather than the manual workaround used for
   `0.1.0-preview.15`) is a natural follow-up qualification.
2. **Decide what to do with `v0.1.0-preview.15` and the `preview-checktest`
   key.** The release is real and public but was built from unchanged
   source purely to validate discovery — it carries no functional
   difference from `0.1.0-preview.14`. Options include deleting the
   release, leaving it as harmless (no device trusts `preview-checktest`
   by default, so it poses no real installation risk), or repurposing it
   as an intentional next release now that the workflow gap above is
   fixed. Still an open decision for the project owner.
