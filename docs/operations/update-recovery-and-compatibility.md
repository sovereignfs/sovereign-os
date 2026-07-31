# Update Compatibility, Rollback Limitations, and Recovery

**Status:** Draft
**Audience:** the person operating a Sovereign OS device — not a Sovereign
OS contributor. For engineering-internal detail (schemas, state machines,
qualification evidence), see
[BACKUP_AND_JOURNAL.md](../../update/BACKUP_AND_JOURNAL.md),
[RFC-0014](../rfcs/0014-appliance-update-system.md), and the qualification
reports under [`docs/research/`](../research/).

## What this covers

If you run `sovereign-update` on your device, this page tells you plainly:
what it can and can't do today, what happens to your data during an
update, what happens if something goes wrong, and exactly what to run to
find out or recover. Nothing here is aspirational — every claim matches
what's actually implemented and, where noted, hardware-tested on a real
Raspberry Pi 5.

## Where things stand right now

Be clear-eyed about the current state before relying on this:

- A **production signing key exists** (`sovereign-production-1`, see
  [ADR-0006](../adrs/0006-production-signing-key-custody.md)) and its public
  half now ships baked into the image trust store. `v0.1.0-preview.17` is
  the first release signed with it, and it has now been genuinely
  *installed* on real Raspberry Pi 5 hardware through
  `prepare`/`backup`/`stage`/`activate`, confirmed committed across a
  reboot. `restore`, `prune`, and `rotate-trust` still haven't been
  exercised as part of a real signed-release install.
- There is **no Console button** yet — installing, backing up, restoring,
  and pruning are still commands you run yourself over SSH. `sovereign-update
  check` *does* run automatically once a day now (see below) and will tell
  you if a compatible update exists, but nothing downloads or installs
  itself; you still trigger `prepare`/`backup`/`stage`/`activate` by hand.
- Everything here applies to the **preview channel** on **Raspberry Pi 5**
  only. Nothing about a `stable` channel or other hardware is implied.

## What update paths are supported

An update artifact declares the exact range of installed versions it can
update *from* (`compatibility.source_versions` in its manifest). Your
device will refuse an update that:

- targets the wrong device (`rpi5-arm64` is the only supported identifier
  today);
- was built for a different channel than the one your device is on;
- is actually a downgrade (an update can only move you forward);
- doesn't declare your currently-installed version within its supported
  source range.

In practice, this means updates are qualified and intended to be applied
**one step at a time, from the version you're actually running** — not
"latest always works from anything." If you've been offline for a while
and are several versions behind, expect to need an intermediate update
rather than a single jump, until a broader compatibility range has been
qualified.

## Learning about updates

You don't have to already know a new version exists. `sovereign-update
check` runs automatically once a day (with some random jitter, and it
catches up on the next boot if the device was off at the scheduled time)
and reports what it found:

```bash
sudo sovereign-update check
sudo sovereign-update status   # includes the last check result as "update_check"
```

It only ever *looks* — it verifies any candidate release through the same
signature/compatibility check `prepare` uses, and reports `up_to_date`,
`update_available` (with the version and release-notes URL), or
`check_failed` (network trouble, nothing to worry about — it tries again
next scheduled run). It never downloads the update bundle itself, and
never starts an update on its own; you still decide when to run
`prepare`/`backup`/`stage`/`activate`. See
[RFC-0015](../rfcs/0015-update-discovery.md) and
[update/README.md](../../update/README.md)'s "Update Discovery v1"
section for the full design.

## What an update actually does to your device

Running `sovereign-update prepare` → `backup` → `stage` → `activate` does,
in order:

1. **Verifies** the update's signature and every artifact digest before
   touching anything.
2. **Backs up** your Pi-hole configuration and database, Sovereign
   configuration, secrets, and the current release pointer — briefly
   stopping Pi-hole to do it consistently, then restarting it and
   confirming it's healthy again before continuing.
3. **Stages** the new appliance files and Pi-hole container image
   alongside — not in place of — what's currently running.
4. **Activates**: switches over, restarts services, and runs a full local
   health check (DNS, Console, Pi-hole).
5. If everything passes, it **commits**. If anything fails, it
   **automatically rolls back** to what you had running before, and
   re-checks health on the rolled-back version too.

Your Pi-hole admin password, DNS configuration, and query history are
never touched by this process except by the backup itself — a normal
update commit does not modify them.

## Rollback limitations — read this before you rely on it

Automatic rollback (step 5 above) restores the **previous appliance
release and container version**. It does **not** restore your data from
the backup, because the current updater rejects any update that would
require a data migration in the first place — so there's nothing for an
automatic rollback to undo on the data side. This means:

- Automatic rollback is fast, safe, and already hardware-qualified
  multiple times (see the
  [preview.12](../research/preview-12-appliance-update-qualification-report.md)
  and
  [preview.14](../research/preview-14-appliance-update-qualification-report.md)
  qualification reports).
- It is **not** a general-purpose "undo my data changes" button. If you
  need to recover data specifically (not just the appliance version), use
  `sovereign-update restore <backup-id>` — a separate, deliberate command
  (see [Restoring from a backup](#restoring-from-a-backup) below).
- Once data migrations exist in a future update, this section will need to
  change — right now, migrations are flatly rejected, which is what makes
  today's rollback guarantee simple.

## If an update doesn't roll back on its own

If rollback itself fails its own health check, the updater does **not**
guess — it stops and marks the transaction `recovery_required`, leaving
both the old and new state on disk rather than deleting anything. Check
what happened:

```bash
sudo sovereign-update status
```

If you see `"update_state": "recovery_required"`:

1. **Don't delete anything yourself.** The old release and your backup are
   still there specifically so nothing is lost while you sort this out.
2. Check what's actually running and whether Pi-hole/DNS/Console are
   reachable — `recovery_required` on the *transaction* doesn't
   automatically mean the *device* is down.
3. Collect diagnostics before doing anything further:
   ```bash
   sudo journalctl -u sovereign-pihole -u sovereign-console -u nginx --no-pager -n 200
   curl -fsS http://127.0.0.1/api/v1/health
   sudo /opt/sovereign/current/appliance/bin/verify-update-health
   ```
4. This is a real edge case that needs a human decision, not an automated
   one — file it as an issue with the output above, or work through
   [BACKUP_AND_JOURNAL.md](../../update/BACKUP_AND_JOURNAL.md)'s durable
   journal section to understand exactly which state transition failed.

## Restoring from a backup

`sovereign-update restore <backup-id>` is a separate, deliberate command
from automatic rollback — use it when you specifically need to recover
Pi-hole state, Sovereign configuration, or secrets from a prior backup
(for example, after confirming your current data is bad for a reason
unrelated to an in-progress update). It:

- verifies the backup's integrity before touching any live data;
- extracts into isolated staging first, only then swapping it in;
- keeps your pre-restore data on disk until the restore's own health check
  passes;
- automatically rolls back the *restore itself* if that health check
  fails, and — same principle as above — stops and preserves both copies
  rather than guessing if even that fails.

List available backups with:

```bash
sudo ls /data/sovereign/backups/
```

Full detail: [BACKUP_AND_JOURNAL.md](../../update/BACKUP_AND_JOURNAL.md)'s
Restore Contract section, and the
[restore hardware qualification report](../research/restore-hardware-qualification-report.md).

## If the device itself won't come back

If the appliance won't boot to a usable state at all — not just a failed
update transaction, but the device itself — the documented recovery path
today is **reflashing the SD card** with a known-good image. Be aware:

- **Reflashing erases the SD card**, including your persistent DATA
  partition — Pi-hole configuration, gravity database, admin credentials,
  everything. There is currently no tested "reflash, then restore my data"
  path; only in-place restore during a live device has been qualified.
- If your data matters and the device is even partially reachable, take a
  backup (`sudo sovereign-update backup <transaction-id>`, or a manual copy
  of `/data/sovereign/`) before reflashing if you possibly can.
- This is the same reason it's worth using a spare SD card rather than
  your daily-driver one whenever you're testing a new image build.

## Cleanup and retention

Old backups, inactive release directories, and finished transaction
journals don't accumulate forever. `sovereign-update prune [--dry-run]`
removes what's safely beyond your configured retention policy — see
[BACKUP_AND_JOURNAL.md](../../update/BACKUP_AND_JOURNAL.md)'s Retention
status section for exactly what it will and won't touch (it always keeps
your newest backup and your active release, no matter what the policy
says). It also now runs on its own once a day; you don't have to remember
to run it.

## Signing-key rotation

If you're the one operating the signing key for your own device(s) (see
[ADR-0006](../adrs/0006-production-signing-key-custody.md)), routine key
rotation doesn't require touching each device by hand anymore —
`sovereign-update rotate-trust` applies a signed rotation manifest instead
of you copying raw key files over SSH. See
[update/README.md](../../update/README.md)'s "Trust Rotation v1" section.
This still requires you to run the command yourself; nothing fetches or
applies a rotation automatically yet.
