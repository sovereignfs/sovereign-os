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

**Retention status:** Implemented as `sovereign-update prune [--dry-run]`,
driven by `/etc/sovereign/retention-policy.json` (schema below; falls back to
these defaults if the file is missing), and hardware-qualified on Raspberry
Pi 5 — see the
[prune and trust rotation qualification report](../docs/research/prune-and-rotate-trust-hardware-qualification-report.md).
It prunes three things in one pass:

```json
{
  "schema_version": 1,
  "backups": { "keep_count": 5, "keep_days": 30 },
  "releases": { "keep_count": 2 },
  "transactions": { "keep_count": 20, "keep_days": 90 }
}
```

- **Backups:** a backup is deletable only once it is both older than
  `keep_days` *and* outside the `keep_count` most recent — whichever bound is
  more generous wins. The single newest backup is always retained regardless
  of policy (`keep_count: 0` cannot delete it). A backup referenced by any
  update or restore transaction that has not yet reached a safe terminal
  state (`committed`, `rolled_back`, or `discarded` for updates;
  `committed`, `rolled_back`, or `discarded` for restores — but never while
  `recovery_required`) is never removed regardless of age or count.
- **Releases:** the currently active release, and any release referenced by
  an in-flight transaction's `activation.json` (`previous_release` or
  `target_release`), is always kept; among the rest, the `keep_count` newest
  by version are kept and older ones removed.
- **Transaction journals:** only `discarded` update transactions and
  `committed`/`rolled_back`/`discarded` restore transactions are eligible —
  never a transaction still awaiting manual `recovery_required` resolution —
  and only beyond the configured `keep_count`/`keep_days`.

`--dry-run` reports what would be removed without deleting anything. Not yet
wired into a periodic timer; it is an operator-invoked command today.

**Status:** Implemented (`sovereign-update restore <backup-id> [--force]` and
`sovereign-update discard-restore <restore-id>`) and hardware-qualified
against real Pi-hole state on Raspberry Pi 5 twice — once manually
deployed, and again on a `0.1.0-preview.13` base image that shipped it
natively — see the
[restore](../docs/research/restore-hardware-qualification-report.md) and
[preview.14](../docs/research/preview-14-appliance-update-qualification-report.md)
qualification reports. It has not yet shipped through a release used by
anyone beyond qualification.

`restore` verifies the backup manifest and all four archive digests before
creating any transaction or touching live data, then extracts the
`pihole_state`, `sovereign_configuration`, and `secrets` roles into an
isolated staging directory (`release_pointer` is verified for integrity and
compatibility only; it is not written back to disk). Extraction never trusts
archive-embedded ownership or permission bits: every file is re-created under
a fixed per-role mode (`0755`/`0644`, or `0700`/`0600` for secrets),
regardless of what the archive itself declares. By default `restore` refuses
a backup whose recorded source appliance version does not match the
currently installed release; `--force` overrides this.

Once staging is verified, `sovereign-pihole.service` is stopped, each live
directory is renamed aside (`.<name>.pre-restore.<restore-id>`) only if it
exists, the staged directory takes its place, and the service restarts.
Health failure at this point (or an explicitly armed
`SOVEREIGN_UPDATE_QUALIFICATION_FAIL_HEALTH` during future hardware
qualification) rolls the swap back: the just-installed data moves aside to
`<name>.rollback-failed.<restore-id>` and the retained pre-restore directory
moves back into place. If the rollback's own health check then also fails,
the restore ends in `recovery_required` with both trees left on disk for
manual inspection — matching the "never recursively delete both copies"
requirement above. `discard-restore` only removes a finished restore's
transient staging; it never deletes `recovery_required` data automatically.

The restore journal follows the same `state.json` / `events.jsonl` pattern as
update transactions, at
`/data/sovereign/update-state/restores/<restore-id>/`, with its own state
machine: `available -> extracting -> extracted -> restoring -> verifying ->
committed`, with `rolling_back -> rolled_back` or `recovery_required` on
failure. It is not yet wired into automatic update rollback for migrations;
today it is a standalone administrator command.

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
`recovery_required`. An administrator may explicitly discard a `rolled_back`
or `recovery_required` transaction after confirming the previous release is
active. Discard removes only inactive target and transient payload files; it
retains the transaction journal and referenced backup as evidence.

On boot, one updater process holds an exclusive lock and examines every
non-terminal transaction. Downloads and pre-activation staging may restart or
resume after revalidation. `activating`, `validating`, and `rolling_back` never
guess: the updater compares the active release, container digest, backup
reference, and health state, then resumes rollback or requires manual recovery.
