# First Production-Signed Release Qualification Report

**Date:** 2026-07-31

## Purpose

Confirm the production signing key (`sovereign-production-1`, generated
under [ADR-0006](../adrs/0006-production-signing-key-custody.md)) works
end-to-end: a release built by the normal workflow, signed offline by the
maintainer with the password-manager-held private key, published as a
real GitHub release, and correctly discovered and verified by
`sovereign-update check` on physical Raspberry Pi 5 hardware running the
real installed `0.1.0-preview.14`.

This is the first release ever signed with a key intended for production
use, as opposed to the disposable qualification keys (`preview-local`,
`restore-qual-local`, `preview-checktest`, etc.) used throughout every
prior hardware campaign.

## Method

1. Built `0.1.0-preview.17` via the standard `build-image.yml` workflow
   with `build_update_candidate: true`, `update_source_minimum:
   0.1.0-preview.14`, `update_key_id: sovereign-production-1`, published
   as a draft release.
2. The maintainer downloaded the unsigned `release-manifest.json`,
   decrypted the private key from their password manager onto their own
   machine, and signed it with `scripts/sign-update-manifest.py` —
   the private key was never handled by, or exposed to, the assistant at
   any point in this step.
3. Verified the resulting signature locally against the committed public
   key before publishing (`openssl pkeyutl -verify`) — confirmed valid.
4. The maintainer uploaded `release-manifest.sig` and published the
   release (`draft: false`).
5. On the device (still running the real, shipped `0.1.0-preview.14`):
   installed only the `sovereign-production-1` public key as a trust
   entry, temporarily deployed the current (`check`-capable)
   `sovereign-update` script — the installed preview.14 binary predates
   the `check` subcommand — and ran `sovereign-update check` for real.

## Result

```json
{
  "available_version": "0.1.0-preview.17",
  "channel": "preview",
  "checked_at": "2026-07-31T20:56:53Z",
  "current_version": "0.1.0-preview.14",
  "error": null,
  "notes_url": "https://github.com/sovereignfs/sovereign-os/releases/tag/v0.1.0-preview.17",
  "reboot_required": false,
  "schema_version": 1,
  "status": "update_available"
}
```

Correct in every field, verified under the real production key, sourced
entirely from the real GitHub API and the real signed manifest.

## Cleanup

The temporarily deployed `check`-capable script, the production trust
key, and the check-result file were removed from the device. The
original `sovereign-update` binary was restored from the exact matching
Git blob (verified by SHA-256 against the pre-change installed binary)
rather than assumed, and `sovereign-update status` and `systemctl
--failed` confirmed the device returned to its exact prior state with no
regression.

Unlike the earlier positive-path validation releases (`v0.1.0-preview.15`,
deleted; `v0.1.0-preview.16`, deleted — both signed with disposable
throwaway keys), **`v0.1.0-preview.17` is intentionally left published**:
it is the first real, production-signed release and is not a throwaway
validation artifact.

## A private-key handling incident, disclosed

During earlier preparation of the production key (before this
qualification), the assistant made a mistake: an initial candidate
private key was briefly displayed in a chat tool-output transcript. It
was caught immediately, that key was discarded and shredded without ever
being used to sign anything, and a second keypair was generated with the
private half never read by the assistant at any point. The key actually
used for this qualification (`sovereign-production-1`, fingerprint
`cff2e702365d0f8f08e552af977eaed37cb549de9d8ac9eb5408f8e70288149c` over
its DER-encoded public key) is the second, never-exposed one. Recorded
here for anyone auditing this key's provenance later.

## Recommendation

The production signing key is now proven end-to-end on real hardware.
Remaining gaps before this is the *normal* release path rather than a
one-off:

- `restore`, `prune`, and `rotate-trust` have still never shipped through
  a signed release actually *installed* on a device (only `check`'s
  discovery has been exercised against `v0.1.0-preview.17`) — a real
  `prepare`/`stage`/`activate` run from `0.1.0-preview.14` to
  `0.1.0-preview.17` would close that gap.
- Signing is still a fully manual, single-maintainer step; that matches
  ADR-0006's accepted custody model at this project's current scale and
  is not itself a gap to close.
