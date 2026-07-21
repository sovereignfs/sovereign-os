# Backup and Transaction Journal Contract

## Backup Layout

Each pre-update backup is stored at:

```text
/data/sovereign/backups/<backup-id>/
├── backup-manifest.json
├── pihole-state.tar.zst
├── sovereign-configuration.tar.zst
├── secrets.tar.zst
└── release-pointer.tar.zst
```

The directory is root-owned mode `0700`; the manifest and payloads are mode
`0600`. Backups are not encrypted in Phase 01.1 because they reside beside the
equally sensitive source data, but export or off-device backup requires a
separate encryption design.

The four roles are mandatory and unique:

- `pihole_state`: `/data/sovereign/apps/pihole/etc-pihole`;
- `sovereign_configuration`: `/data/sovereign/configuration`;
- `secrets`: `/data/sovereign/secrets`;
- `release_pointer`: active/previous release identifiers and component metadata,
  represented as regular files rather than archived absolute symlinks.

Docker/containerd runtime data, downloaded update payloads, staging files,
logs, caches, and earlier backups are excluded.

## Consistency and Validation

The initial updater creates a quiesced backup:

1. verify Pi-hole is healthy;
2. stop `sovereign-pihole.service` and record the start of expected DNS downtime;
3. create all four archives using relative paths and numeric ownership;
4. restart Pi-hole immediately and require local DNS and HTTP health;
5. calculate each archive's size and SHA-256;
6. write `backup-manifest.json` atomically and fsync its directory;
7. reject the backup unless its schema, four unique roles, files, sizes,
   digests, permissions, and safe archive listings all validate.

Archive validation rejects absolute paths, `..`, device nodes, FIFOs, sockets,
setuid/setgid bits, unexpected links, and entries outside the role's allowed
restore prefix. A backup is not usable merely because compression succeeded.

If Pi-hole cannot restart after backup, the update does not proceed. The
journal moves to `recovery_required` because the pre-update appliance is no
longer healthy.

## Restore Contract

Restore always targets an empty staging directory first. After digest and
archive-safety validation, the updater extracts with no privilege escalation
from archive metadata, verifies required files, stops affected services, and
atomically exchanges or renames the authoritative directories where the
filesystem permits. The previous directories are retained until restored DNS
and HTTP checks pass.

A restore must use a backup whose source version and data schema match the
rollback plan. Secrets are restored only with mode `0600` under a mode `0700`
directory. Failure leaves retained old and staged paths plus an actionable
`recovery_required` journal state; it must not recursively delete both copies.

At least the newest successful backup and the backup needed by the active
rollback boundary are retained. Cleanup never removes a backup referenced by a
non-terminal transaction. Concrete byte/count quotas remain a release-policy
decision.

## Durable Journal

Transactions live at:

```text
/data/sovereign/update-state/transactions/<transaction-id>/
├── state.json
└── events.jsonl
```

`state.json` follows
[`schema/transaction-state-v1.schema.json`](schema/transaction-state-v1.schema.json).
Every transition increments `sequence`, writes a complete temporary snapshot,
fsyncs it, atomically renames it, and fsyncs the parent directory.

`events.jsonl` is an append-only diagnostic history. Each line records the
transaction ID, sequence, previous and next state, timestamp, and non-secret
reason code. The snapshot is authoritative for recovery; events support audit
and diagnosis. Neither file contains credentials, DNS queries, manifest
contents, or arbitrary subprocess output.

Allowed forward transitions are:

```text
available -> downloading -> verified -> backing_up -> backed_up -> staged
          -> activating -> validating -> committed
```

Any non-terminal state may enter `recovery_required` when automated recovery
is unsafe. Activation or validation failure enters `rolling_back`, followed by
`rolled_back` only after rollback health checks pass; otherwise it enters
`recovery_required`.

On boot, one updater process holds an exclusive lock and examines every
non-terminal transaction. Downloads and pre-activation staging may restart or
resume after revalidation. `activating`, `validating`, and `rolling_back` never
guess: the updater compares the active release, container digest, backup
reference, and health state, then resumes rollback or requires manual recovery.
