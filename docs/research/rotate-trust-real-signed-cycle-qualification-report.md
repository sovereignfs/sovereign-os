# `rotate-trust` in a Real Signed-Release Install Cycle — Qualification Report

**Date:** 2026-08-09

**Hardware:** Raspberry Pi 5 (`sovereign.local`), the project's qualification
device, running `0.1.0-proof.3` on channel `preview` throughout — a real,
production-signed, already-committed release, not a throwaway build for
this campaign.

**Status:** Closes the last remaining named gap in Milestone 2: `rotate-
trust` had previously only been exercised standalone, with ephemeral test
keys signing ephemeral test keys (see the
[prune and trust rotation qualification report](prune-and-rotate-trust-hardware-qualification-report.md),
2026-07-31). This pass used the real `sovereign-production-1` production
key — held only in the maintainer's password manager per
[ADR-0006](../adrs/0006-production-signing-key-custody.md), never handled
by the assistant — to sign a real rotation manifest applied against the
device's live, real trust store while it was running a real signed
release.

## Scope decision

Rather than either leaving the device with a real standing second
production key (which would need its own custody decision, out of scope
for this pass) or repeating the July 31 test's fully-ephemeral setup
(which wouldn't touch the real production key at all), this pass used a
**qualification-only key added under real dual trust, then self-revoked**:

1. The assistant generated a fresh Ed25519 keypair
   (`rotation-qualification-2026-08-09`) — a key the assistant is allowed
   to hold, since it is not the production key ADR-0006 restricts.
2. The maintainer signed an **add-only** rotation manifest with the real
   `sovereign-production-1` key, adding the qualification key to the
   `preview` channel without revoking anything — genuine dual trust, so
   the device was never at risk of losing its production trust anchor.
3. The qualification key then signed its own revocation, self-cleaning
   back to the original single-key baseline without needing the
   maintainer's key a second time.
4. A negative test — a manifest attempting to revoke
   `sovereign-production-1`, signed by the now-revoked qualification key —
   confirmed revocation is enforced immediately.

## Method and results

### 1. Add-only rotation, signed by the real production key

A manifest (schema `trust-rotation-v1`) was built adding
`rotation-qualification-2026-08-09` (Ed25519, `preview` channel) with no
revoke operations, `signing.key_id: sovereign-production-1`. The
maintainer signed it with the real production private key via
`scripts/sign-update-manifest.py`, deleting the decrypted key file
immediately after (per standing operational practice for this key).

The signature was verified independently — `openssl pkeyutl -verify`
against `sovereign-production-1.pem` as already checked into the
image-builder overlay's trust store — *before* it was ever copied to the
device, confirming this was genuinely signed with the real key and not
just accepted on trust.

```console
$ sudo sovereign-update rotate-trust --manifest /tmp/trust-rotation-manifest.json --signature /tmp/trust-rotation-manifest.sig
{"operations": [{"action": "add", "key_id": "rotation-qualification-2026-08-09"}], "status": "rotated"}
```

Trust store afterward showed genuine dual trust — both keys present and
`"revoked": false`:

```console
sovereign-production-1.json:            "channels": ["preview", "stable"], "revoked": false
rotation-qualification-2026-08-09.json: "channels":["preview"], "revoked":false
```

### 2. New key proven functional, by self-revoking

Rather than a throwaway release-manifest signature (the July 31 report's
approach), this pass proved the new key genuinely works by using it for a
real `rotate-trust` operation: a manifest revoking
`rotation-qualification-2026-08-09`, signed by that same key, applied
successfully —

```console
$ sudo sovereign-update rotate-trust --manifest /tmp/trust-revoke-manifest.json --signature /tmp/trust-revoke-manifest.sig
{"operations": [{"action": "revoke", "key_id": "rotation-qualification-2026-08-09"}], "status": "rotated"}
```

— which only succeeds if `load_trusted_key`/`verify_signature` genuinely
validated a signature from the added key against the device's real trust
store, i.e. a more direct proof of function than a side-channel test
manifest would have been.

### 3. Revocation enforced immediately

A manifest attempting to revoke `sovereign-production-1`, signed by the
now-revoked qualification key, was rejected outright:

```console
$ sudo sovereign-update rotate-trust --manifest /tmp/trust-negative-test-manifest.json --signature /tmp/trust-negative-test-manifest.sig
{"status": "rejected", "code": "REVOKED_SIGNING_KEY", "message": "The signing key is revoked"}
```

Nothing about the trust store changed as a result of the rejected attempt
— `sovereign-production-1` was never at risk, since the rejection happens
at signature verification, before any operation is simulated or applied.

### Final state

```console
sovereign-production-1.json:            "revoked": false   (unchanged throughout)
rotation-qualification-2026-08-09.json: "revoked": true    (added, proven functional, then revoked)
```

The device ends this campaign trusting exactly `sovereign-production-1`
for real signing — its original baseline — plus one revoked audit-trail
entry for the qualification key, matching `rotate-trust`'s designed
behavior of flipping `revoked` in place rather than deleting key records.
`/tmp` scratch files on the device were removed; the qualification
private key was deleted from the assistant's local scratch directory once
no longer needed.

## Conclusion

`rotate-trust` has now been exercised end-to-end with the real production
key, against the real device trust store, while the device was running a
real production-signed release — closing the specific gap the July 31
report left open ("has not been exercised with a production (non-
ephemeral) signing key"). Add-only dual trust, self-revocation by a newly
added key, and immediate enforcement of revocation against a real
production key's rotation manifest all behaved correctly. This closes
Milestone 2's last named gap; see [ROADMAP.md](../../ROADMAP.md).
