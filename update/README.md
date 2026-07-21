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

## Backup and Journal v1

The [backup and transaction journal contract](BACKUP_AND_JOURNAL.md) defines
the initial quiesced Pi-hole backup, safe restore boundary, retention floor,
atomic state snapshot, append-only diagnostic events, and restart decisions.
Its machine-readable contracts are:

- [`schema/backup-manifest-v1.schema.json`](schema/backup-manifest-v1.schema.json);
- [`schema/transaction-state-v1.schema.json`](schema/transaction-state-v1.schema.json).

The corresponding files under [`examples/`](examples/) are test fixtures, not
real backup or transaction metadata.
