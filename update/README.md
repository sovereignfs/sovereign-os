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

Trusted public keys live under `/etc/sovereign/update-trust.d/` as matching
`<key-id>.pem` and `<key-id>.json` files. The preview image intentionally ships
with an empty trust store until release-key custody and rotation are approved;
this fails closed instead of embedding a development private key or silently
trusting an unapproved publisher.

## Backup and Journal v1

The [backup and transaction journal contract](BACKUP_AND_JOURNAL.md) defines
the initial quiesced Pi-hole backup, safe restore boundary, retention floor,
atomic state snapshot, append-only diagnostic events, and restart decisions.
Its machine-readable contracts are:

- [`schema/backup-manifest-v1.schema.json`](schema/backup-manifest-v1.schema.json);
- [`schema/transaction-state-v1.schema.json`](schema/transaction-state-v1.schema.json).

The corresponding files under [`examples/`](examples/) are test fixtures, not
real backup or transaction metadata.
