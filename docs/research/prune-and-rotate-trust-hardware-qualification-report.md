# Prune and Trust Rotation Hardware Qualification Report

**Date:** 2026-07-31

**Hardware:** Raspberry Pi 5 Model B Rev 1.1, running `0.1.0-preview.14`
(shipped in the base image — not manually deployed for this campaign,
unlike prior qualification sessions)

**Status:** `sovereign-update prune` and `sovereign-update rotate-trust`
qualified against real on-device state on Raspberry Pi 5.

## `sovereign-update prune`

### Method

Real state accumulated from the preview.13-to-preview.14 qualification
campaign was used directly: 3 backups (2 from discarded qualification
transactions, 1 from the committed activation), 2 release directories
(`0.1.0-preview.13` inactive, `0.1.0-preview.14` active), and 3 transaction
journals (2 discarded, 1 committed).

### Default policy — no-op confirmed

`prune --dry-run` with the shipped default policy (`keep_count: 5` backups
/ 30 days, 2 releases, 20 transactions / 90 days) correctly reported nothing
removable — everything was well within the defaults' bounds. This confirms
the default policy is not accidentally aggressive against a freshly-active
device.

### Aggressive policy — real deletion behavior

An all-zero policy (`keep_count: 0` / `keep_days: 0` for every resource)
was applied via `SOVEREIGN_RETENTION_POLICY` (a scratch file, not the
system config) to actually exercise deletion:

- **Backups:** removed the 2 older backups; kept the single newest
  regardless of the zero `keep_count` — confirming the "always keep the
  newest" floor holds on real hardware, not just in the unit-test fixtures.
- **Releases:** removed `0.1.0-preview.13` (inactive); kept
  `0.1.0-preview.14` (active) — confirming the active-release protection
  holds regardless of `keep_count`.
- **Transactions:** removed both discarded journals; left the committed
  transaction's journal untouched, matching the design that committed
  update-transaction journals are never auto-pruned (only `discarded`
  ones are eligible).
- Dry-run output matched the real-run output exactly before either was
  applied.
- **The live device remained fully healthy throughout:** Console, health
  API, `verify-update-health`, and `systemctl --failed` were all re-checked
  immediately after the real prune and showed no regression.
- **Idempotency:** re-running prune with the same aggressive policy
  immediately afterward reported zero further removals, as expected once
  only protected resources remained.

In-flight-reference protection (a backup/release referenced by a
non-terminal transaction) was not separately re-verified on hardware in
this campaign — that logic is pure state-file reasoning with no
hardware-specific risk, already covered by the unit-test suite
(`tests/test_update_prune.py`).

## `sovereign-update rotate-trust`

### Method

Two ephemeral Ed25519 keys were generated for this qualification only
(`preview-local` installed as the starting trust, `preview-rotated` as the
target of rotation) — both discarded at the end of the campaign, and the
device's trust store was restored to its shipped empty default afterward.

### Successful rotation

A single manifest signed by `preview-local` both added `preview-rotated`
and revoked `preview-local` — the realistic single-key handoff pattern from
ADR-0006. Applying it:

- installed `preview-rotated.{pem,json}` (`revoked: false`);
- flipped `preview-local.json` to `revoked: true` in place, without
  removing the file;
- appended one non-secret entry to
  `/data/sovereign/update-state/trust-rotations.jsonl`.

### New key works, old key is rejected

A throwaway test release manifest signed with the new key (`preview-
rotated`) passed `sovereign-update inspect` cleanly. The same manifest
signed with the now-revoked old key (`preview-local`) was rejected with
`REVOKED_SIGNING_KEY` — confirming revocation takes effect immediately for
any further use of the old key, not just for the rotation manifest itself.

### Lockout protection

A manifest that would have revoked `preview-rotated` — at that point the
only trusted key for the `preview` channel — with no replacement key added,
signed by that same key, was rejected outright with
`TRUST_LOCKOUT_REJECTED`. The trust store and the audit log were both
verified byte-for-byte unchanged afterward, confirming the rejection is
fully atomic: nothing partially applies before the lockout check fails.

## Conclusion

Both commands behave correctly against real on-device state and real
signed artifacts, not just unit-test fixtures. `prune` safely deletes real
backups/releases/journals while never compromising the live device's
health, and correctly protects the newest backup and the active release
regardless of an aggressive policy. `rotate-trust` correctly performs the
realistic single-key rotation handoff, immediately enforces revocation, and
cannot be used to lock a channel out of all trusted keys. Neither command
has shipped through a real signed release used for anything beyond this
qualification session, and neither has been exercised with a production
(non-ephemeral) signing key.
