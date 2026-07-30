# ADR-0006: Production Update Signing-Key Custody

**Status:** Accepted
**Date:** 2026-07-30
**Decision owner:** Project creator
**Related RFC:** [RFC-0014](../rfcs/0014-appliance-update-system.md)
**Related milestone:** [Appliance Update Foundation](../roadmap/01-1-update-foundation.md)
**Supersedes:** None

## Context

Every signed release manifest is verified against a trust store of
`<key-id>.pem` / `<key-id>.json` pairs under `/etc/sovereign/update-trust.d/`
(schema, channel scoping, and revocation are already implemented — see
`load_trusted_key()` in `sovereign-update`). The shipped trust store is
intentionally empty:

> No preview key is installed until release-key custody and rotation are
> approved. An empty trust store fails closed and prevents update
> installation.
> — `image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/etc/sovereign/update-trust.d/README`

Every key used so far — including the `preview-local` and `restore-qual-local`
keys used during hardware qualification — has been an ephemeral, disposable
Ed25519 keypair generated on an operator's own machine for a single
qualification session and discarded afterward. That is appropriate for
qualification but is not a production key: no real household should ever
install a Sovereign OS update signed by a key with no defined custody,
rotation, or revocation story.

This ADR does not choose custody for the project owner. It lays out the
realistic options at this project's current scale (a small/solo maintainer
team, self-hosted household infrastructure, budget-conscious) so a deliberate
choice can be recorded and revisited as the project grows.

### What the signing key actually protects

A holder of the production private key can produce a manifest that every
device trusting that `key_id` will accept as authentic for its scoped
channel(s). Layered defenses (archive-safety validation, Compose/Nginx
config validation, digest pinning, health-gated activation, automatic
rollback) limit what a malicious *payload* can do once accepted, but they
do not substitute for keeping the key itself out of reach of anyone who
shouldn't have it. For a device that answers DNS for someone's home network
and holds their Pi-hole credentials, this is the update system's single
highest-value secret.

### Constraints already fixed by the existing design

- Algorithm is fixed: Ed25519 only (`manifest["signing"]["algorithm"] ==
  "Ed25519"`).
- Trust is per-key, per-channel: a key's JSON metadata scopes it to
  `preview` and/or `stable`. Separate keys per channel are already
  supported without any code change — only a custody decision.
- Revocation is already implemented at the verification layer
  (`metadata["revoked"]`), but **distribution of a revoked-flag update to
  already-flashed devices is not yet automated.** Today it would require
  either a manual per-device file copy (as done for qualification) or
  waiting for the "Update Discovery and Console Controls" milestone to
  ship signed trust-metadata distribution. This ADR's recommendation should
  account for that gap, not assume revocation is instantly effective.
- The trust store ships baked into the base image (like
  `update-policy.json`) but is currently empty; once a production key
  exists, its **public** key and metadata are natural candidates to add to
  the image-builder overlay so future base images trust it out of the box,
  removing the manual per-device installation step used during
  qualification.

## Decision

The project owner selected **a variant of Option B (password-manager-held
key), with Option C (hardware security key) as an accepted future upgrade
path** rather than a required starting point.

- The production Ed25519 private key is generated and stored as an
  encrypted secret in the maintainer's password manager. This gives the key
  professional-grade encryption at rest and, importantly, solves the
  single-point-of-failure backup problem that Option A (bare offline
  device) has on its own — most password managers replicate across devices
  and have their own account-recovery process.
  - When a release needs signing, the key is decrypted out to a machine to
    run the actual `openssl pkeyutl -sign -rawin` operation, then that
    plaintext copy should be removed from disk afterward. Preferring a
    machine that is not your everyday browsing/email machine for that
    moment further reduces exposure, but is a practice recommendation, not
    a hard requirement of this decision.
  - This does **not** eliminate the exposure window at signing time the
    way a hardware token would — see the Risks below.
- A hardware security key (Option C) remains open as a future upgrade once
  its exact Ed25519/PKCS#11 compatibility with this project's signing flow
  is verified by a hands-on spike. Nothing about today's decision blocks
  moving to it later; the trust-store mechanism only cares about the public
  key and `key_id`, not how the private half was held.
- Options A (pure offline device), D (cloud KMS), and E (threshold signing)
  were not selected — D specifically because it introduces a third party
  into the trust chain, which the project owner weighed against the
  project's self-hosted values as described in the Options section below.

## Options

### Option A — Offline, air-gapped signing device

Generate and keep the private key only on a device that is never connected
to any network: a spare Raspberry Pi, an old laptop, or even a
write-protected USB boot environment. Manifests to be signed are moved onto
the device (SD card / USB), signed with `openssl pkeyutl -sign -rawin`
exactly as the qualification tooling already does, and the signature is
moved back off.

- **Cost:** near zero — reuses hardware most maintainers already have.
- **Fits the project's own "sovereign"/self-hosted values** — no third
  party ever holds the key.
- **Downsides:** fully manual (slower release cadence), a single point of
  physical loss/theft/fire unless backed up, no built-in access log, key
  backup (e.g., an encrypted copy on separate media in a separate physical
  location) is the maintainer's own responsibility to set up and remember.

### Option B — Passphrase-protected key on the maintainer's regular machine

The simplest option: an Ed25519 key encrypted at rest (e.g.,
`openssl genpkey` output protected by a passphrase, or a standard encrypted
keychain), used directly from a day-to-day development machine.

- **Cost:** zero, fastest to set up.
- **Downsides:** weakest option here. Malware or compromise of that machine
  at the moment the passphrase is entered exposes the key directly. This is
  materially the same trust level as the disposable qualification keys
  already used — arguably not a real step up to "production."

### Option C — Hardware security key / smartcard

A dedicated hardware token (e.g., a FIDO2/OpenPGP-capable security key)
generates the private key on-chip; it never leaves the device, and signing
requires physical possession plus a PIN or touch.

- **Strong protection against remote compromise** — malware on the signing
  machine can request a signature but cannot exfiltrate the key.
- **Cost:** modest (roughly $25–$70 for a suitable token).
- **Feasibility caveat, not yet verified:** the update tooling signs via
  `openssl pkeyutl -sign -rawin` against a raw manifest byte stream. Whether
  a specific token exposes Ed25519 signing through a PKCS#11/engine
  interface compatible with that exact flow needs a hands-on spike before
  committing to this option — don't take it as validated by this ADR.
- **Downsides:** token loss means a real rotation event; a lost token
  cannot be "restored," only replaced.

### Option D — Cloud KMS (e.g., AWS KMS, Google Cloud KMS, HashiCorp Vault)

The private key is generated and held inside a managed key-management
service; signing happens via an API call, never exposing key material.

- **Strongest operational story:** audit logs, access control, straightforward
  to wire into CI for automated release signing later.
- **Downsides:** recurring cost; introduces a third party into the trust
  chain for a project whose product explicitly avoids third-party
  dependencies for the household's own data — worth weighing against the
  project's stated values even though the *signing infrastructure* isn't
  the shipped *product*. Ed25519 support and exact API shape vary by
  provider and should be verified current before relying on this option;
  don't take Ed25519 availability as confirmed by this ADR. Adds IAM/service
  -account complexity that is arguably disproportionate for a solo
  maintainer today.

### Option E — Threshold / multi-party signing

Split the key (e.g., Shamir's Secret Sharing) across multiple trusted
parties so no single person can sign alone.

- Meaningful once the project has more than one person who should be able
  to authorize a release.
- **Not recommended now** — every other document in this repository lists a
  single "Decision owner: Project creator." Revisit this option if that
  changes.

## Initial Recommendation (superseded by Decision above)

Before a decision was made, this ADR initially leaned toward Option A
(offline air-gapped device) or Option C (hardware security key) as the
best fit for the project's scale, budget, and self-hosted values, and
cautioned that a bare passphrase-protected key (Option B) was only
marginally stronger than the disposable qualification keys already in use.
The project owner weighed that tradeoff and chose the password-manager
variant recorded in Decision above specifically because it closes the
backup/durability gap that made plain Option B weak, while keeping Option C
open as a later upgrade. Recorded here for context, not as standing
guidance.

## Rotation

**Update since this ADR was first drafted:** routine rotation is now
implemented as `sovereign-update rotate-trust` (see the "Trust Rotation v1"
section of `update/README.md`), which delivers a new trust key through the
same signed-artifact mechanism as everything else, rather than a manual
`sudo install` of raw key files. The realistic flow given this ADR's
single-key custody decision:

1. Generate the new keypair using the chosen custody mechanism (currently:
   password manager, decrypted onto a signing machine when needed).
2. Sign a trust-rotation manifest, using the *current* key, that both `add`s
   the new key and `revoke`s the current one in the same manifest — an
   atomic handoff with no gap where two keys are simultaneously trusted
   unless that overlap is explicitly wanted (a manifest can also add-only
   and revoke the old key in a later, separate manifest if a longer overlap
   window is preferred).
3. Run `sovereign-update rotate-trust` with that manifest against each
   device. Its built-in lockout check refuses to apply any rotation that
   would leave the channel with zero trusted keys, so a mistake here cannot
   brick a device's ability to trust future updates.
4. Sign subsequent releases with the new key.
5. Reaching *already-flashed* devices with step 3 is still a manual,
   operator-run command today — that part of the distribution gap remains
   open until "Update Discovery and Console Controls" can fetch and apply a
   rotation manifest automatically. What's closed is the *safety* of the
   rotation action itself: it's now a verified, atomic, signed operation
   instead of copying trust-me-bare files over SSH.

## Revocation

If a key is known or suspected compromised: immediately stop signing with
it, and treat every already-signed release under that key as untrustworthy
going forward (the manifest schema has no separate revocation-of-past-
releases mechanism — revocation is key-scoped, not release-scoped).

`sovereign-update rotate-trust` can carry a `revoke` operation and works for
*precautionary* or planned revocation exactly like rotation above — a
still-good signature applies the revoke-plus-replacement atomically to each
device, still gated on manual per-device delivery until Update Discovery
exists.

For a *confirmed adversarial compromise*, be precise about what
`rotate-trust` does and doesn't buy you: it only accepts manifests signed by
the compromised key itself (or another already-trusted key), so whether the
legitimate operator's revocation reaches a given device before an attacker
uses the same stolen key to push something malicious to that device is a
race, not a guarantee — key compromise means an adversary can produce
equally "validly signed" rotation manifests too. The only fully reliable
recovery from a confirmed compromise is treating every device as needing a
fresh trust root, which today means a reflash with a new key baked into the
image (see Recovery below); `rotate-trust` is a convenience for the routine
case, not a substitute for that fallback in the adversarial case.

## Recovery if the key is lost or the custodian is unavailable

Because trust is rooted in whatever key(s) are already installed on a
device, losing the only trusted production key with no backup would leave
existing devices unable to verify *any* future signed update — the fallback
is a full base-image reflash carrying a new key baked into the overlay
(the same mechanism already used to ship `update-policy.json`). Whichever
custody option is chosen, an encrypted backup of the private key material,
stored somewhere physically separate from the primary custody location,
should be treated as a requirement, not an optional nicety — the
alternative is an unrecoverable trust root.

## Consequences

### Positive

- Removes the last structural blocker called out by the trust-store
  README before any real (non-qualification) signed release can be
  installed by a normal user.
- Makes the rotation/revocation story explicit instead of implicit.

### Negative

- Whichever option is chosen adds an ongoing operational responsibility
  (custody, backup, eventual rotation) that today's ephemeral-qualification-key
  workflow does not have.

### Risks

- Choosing Option B (or any option) without a real backup plan creates a
  single point of failure for the entire update trust chain.
- Revocation and rotation are both gated on a distribution mechanism
  ("Update Discovery and Console Controls") that has not shipped yet;
  choosing a custody option does not by itself close that gap.

## Alternatives Considered

### No production key yet; keep using ephemeral qualification keys

Rejected as a standing state — it is fine for continued hardware
qualification, but it cannot be how a real user's device is ever asked to
trust an update. The empty trust store already fails closed specifically to
prevent this from happening by accident.

## Validation and Revisit Conditions

Revisit this ADR if: the project gains additional trusted maintainers
(favoring Option E), the release cadence grows enough that manual air-gapped
signing (Option A) becomes a bottleneck (favoring Option C or D), or a
hands-on spike shows the intended hardware token does not support the
signing flow this project's tooling uses (ruling out Option C as written).
