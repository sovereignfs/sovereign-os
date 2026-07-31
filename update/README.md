# Sovereign Appliance Updates

This directory owns the installed-appliance update formats. A full disk image
remains a clean-install and recovery artifact; it is not an in-place update.

## Manifest v1

The JSON Schema is
[`schema/sovereign-update-manifest-v1.schema.json`](schema/sovereign-update-manifest-v1.schema.json).
The [`examples/update-manifest-v1.example.json`](examples/update-manifest-v1.example.json)
fixture illustrates the complete initial contract.

The publisher serializes the manifest as UTF-8 JSON with a final newline and
signs those exact bytes using Ed25519. Verification does not reserialize or
canonicalize JSON. The detached `release-manifest.sig` contains the base64
encoding of the raw 64-byte Ed25519 signature and no surrounding JSON.

The client selects a trusted public key using `signing.key_id`, verifies the
signature before trusting any manifest field, and then applies compatibility,
downgrade, storage, digest, migration, and rollback policy. A key identifier is
not proof of trust; it is only an index into keys already installed on the
device.

Version 1 supports one `update_bundle` artifact compressed with Zstandard. The
archive remains hostile until signature and digest verification succeed, and
extraction must reject absolute paths, `..` traversal, device nodes, unsafe
links, and ownership or modes outside the update contract.

The example hashes and sizes are illustrative and must never be published as a
real release manifest.

## Installed verifier

The image installs the update client as `sovereign-update`. It intentionally
does not download releases yet; an operator supplies previously downloaded
inputs. Inspection remains non-mutating:

```text
sovereign-update status
sovereign-update inspect \
  --manifest release-manifest.json \
  --signature release-manifest.sig \
  --artifact sovereign-update-<version>.tar.zst
```

Inspection verifies the signature over the exact manifest bytes before using
compatibility or artifact fields. It then enforces the installed channel,
trusted-key metadata, revocation state, device, source-version range,
downgrade rule, free-space requirement, artifact size, and SHA-256 digest.
Success performs no mutation.

`sovereign-update prepare` accepts the same three inputs and is the first
mutating boundary. Under an exclusive updater lock, it copies authenticated
inputs into a mode-`0700` transaction directory under
`/data/sovereign/update-state/`, fsyncs them, verifies the staged copies again,
and advances an atomic journal through `available`, `downloading`, and
`verified`. It does not extract the bundle, stop a service, or activate files.
An interrupted transaction therefore remains diagnosable and safely precedes
the backup/service-mutation boundary.

`sudo sovereign-update backup <transaction-id>` creates the first quiesced
backup boundary. It stops only Pi-hole, archives the four mandatory roles with
root-only permissions, rejects unsafe or unreadable archive listings, records
size and SHA-256 metadata, restarts Pi-hole immediately, and requires container,
TCP/UDP DNS, HTTP routing, Nginx, and DATA-mount health before entering
`backed_up`. A restart or health failure enters `recovery_required`; activation
is never attempted.

## Update bundle v1

`scripts/create-update-bundle.py` produces the deterministic payload covered by
the outer signed manifest. The archive has one closed root:

```text
sovereign-update-v1/
├── bundle-manifest.json
└── release/
    └── <versioned appliance files>
```

The inner manifest follows
[`schema/update-bundle-manifest-v1.schema.json`](schema/update-bundle-manifest-v1.schema.json)
and allowlists every regular file, size, SHA-256, and normalized mode. Bundle
creation rejects symlinks and special files. Installation must reject absolute
or parent paths, links, device nodes, unlisted files, duplicate names, unsafe
modes, digest mismatches, and a release version different from the signed outer
manifest.

After a successful backup, `sovereign-update stage <transaction-id>` safely
decompresses and manually extracts regular files, verifies the closed inner
manifest, and installs small immutable runtime metadata under
`/opt/sovereign/releases/<version>/`. Large OCI data remains temporarily on the
DATA partition.

`sovereign-update activate <transaction-id>` imports and verifies the pinned
Pi-hole image, atomically switches `/opt/sovereign/current`, recreates Pi-hole
against its existing persistent state, and runs the complete local health gate.
Success records `committed` and removes transient OCI payloads. Failure switches
back to the previous release and records `rolled_back` only after that release
passes the same health gate; otherwise it records `recovery_required`. Initial
v1 activation rejects data migrations and releases without rollback support.

The build workflow can emit an unsigned update candidate beside an image
candidate. `scripts/create-update-release.py` assembles its bundle and outer
manifest from pinned Pi-hole metadata and OCI build evidence.
`scripts/sign-update-manifest.py` signs those exact bytes with a locally held
Ed25519 private key. The private key is never an input to the image builder or
ordinary unsigned packaging workflow.

For physical engineering qualification,
`scripts/prepare-update-qualification.py` validates the unsigned workflow
output, signs and verifies the exact manifest, derives matching public trust
files, and produces a checksummed transfer kit that excludes the private key.
The installed updater also provides explicitly armed durable-boundary
interruption hooks and a safe `discard` command for removing only inactive
failed-test payloads while retaining journals and backups.

Trusted public keys live under `/etc/sovereign/update-trust.d/` as matching
`<key-id>.pem` and `<key-id>.json` files. The preview image intentionally ships
with an empty trust store until release-key custody and rotation are approved;
this fails closed instead of embedding a development private key or silently
trusting an unapproved publisher. Custody is decided in
[ADR-0006](../docs/adrs/0006-production-signing-key-custody.md).

## Trust Rotation v1

Hardware-qualified on Raspberry Pi 5, including the realistic single-key
rotation handoff, immediate enforcement of revocation against the old key,
and the lockout protection — see the
[prune and trust rotation qualification report](../docs/research/prune-and-rotate-trust-hardware-qualification-report.md).

`sudo sovereign-update rotate-trust --manifest trust-rotation.json --signature
trust-rotation.sig` lets an already-trusted key sign new trust-store changes,
so routine key rotation ships through the same signed channel as any other
release instead of requiring a manual per-device file copy. The signed
artifact's schema is
[`schema/trust-rotation-v1.schema.json`](schema/trust-rotation-v1.schema.json)
(fixture at
[`examples/trust-rotation-v1.example.json`](examples/trust-rotation-v1.example.json)).

A manifest declares 1-5 `add`/`revoke` operations against a `channel`, signed
by a `key_id` that must already be trusted, non-revoked, and scoped to that
channel — the same `load_trusted_key`/`verify_signature` path every other
signed artifact uses. `add` refuses to reuse an already-installed `key_id`
(public keys are immutable identities once trusted) and validates the
supplied PEM is a real Ed25519 public key before writing anything. `revoke`
refuses to target a `key_id` that isn't installed. The device's own
configured channel must match the manifest's `channel`.

Everything is validated — including simulating every operation against the
current trust store — before anything is written, and applied atomically.
The one hard safety invariant: after all operations apply, at least one
non-revoked key must remain trusted for that channel, or the whole rotation
is rejected (`TRUST_LOCKOUT_REJECTED`) with nothing changed. This is what
makes the realistic single-key rotation pattern — the outgoing key signing
one manifest that both adds its replacement and revokes itself — safe: a
rotation that would leave a channel with no trusted key can never commit.
Applied rotations are appended to a non-secret audit log at
`/data/sovereign/update-state/trust-rotations.jsonl`.

This command does not itself fetch a rotation manifest — an operator (or,
once it exists, the Console/update-discovery mechanism) still has to deliver
the two files to the device. What it removes is the need to hand-copy raw,
unverified public key material via `sudo install`, the way qualification
sessions have done to date: rotation is now a single verifiable, signed
command instead of an ad hoc file copy.

## Backup and Journal v1

The [backup and transaction journal contract](BACKUP_AND_JOURNAL.md) defines
the initial quiesced Pi-hole backup, safe restore boundary, retention floor,
atomic state snapshot, append-only diagnostic events, and restart decisions.
Its machine-readable contracts are:

- [`schema/backup-manifest-v1.schema.json`](schema/backup-manifest-v1.schema.json);
- [`schema/transaction-state-v1.schema.json`](schema/transaction-state-v1.schema.json).

The corresponding files under [`examples/`](examples/) are test fixtures, not
real backup or transaction metadata.
