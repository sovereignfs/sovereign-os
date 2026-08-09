# Decision: Defer Wiring Restore Into Automatic Update Rollback

**Date:** 2026-08-09

## Summary

ROADMAP.md's Milestone 2 has long named an open gap: `sovereign-update
restore` "is not yet wired into automatic update rollback for future data
migrations." Before picking this up, we checked what `activate_release`'s
rollback path actually does today and found the gap is currently
unreachable — wiring it in now would add risk with no corresponding
benefit. This is a scope decision, not new code: the sub-item stays
recorded, but as intentionally deferred rather than open work.

## What the code actually does today

`activate_release` (`image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/usr/sbin/sovereign-update`,
around line 1606) only ever does two things to the live system between
`backed_up` and `committed`: import and switch the Pi-hole container image,
and swap the `current` release symlink. Neither step reads, migrates, or
otherwise touches `/data/sovereign/apps/pihole/etc-pihole`,
`/data/sovereign/configuration`, or `/data/sovereign/secrets` — the three
roles a backup actually captures (see
[BACKUP_AND_JOURNAL.md](../../update/BACKUP_AND_JOURNAL.md)). Its rollback
branch (`except UpdateError` around line 1644) mirrors this: it switches
`current` back to `previous` and restarts the appliance. It never touches
persistent data either, because nothing upstream of it did.

The consequence: at the moment rollback runs, the live persistent data is
still byte-identical to what it was before the update attempt started —
there is nothing for a rollback-triggered `restore` to undo. Calling
`restore_backup` from inside `activate_release`'s rollback branch today
would stop and restart Pi-hole a second time (on top of the stop/start
`create_backup` and `activate_release` already do) to extract and swap in
data that is already live, purely to satisfy a code path that has no work
to do. That is added DNS downtime and an added failure surface
(`restore_backup`'s own `restoring`/`verifying`/`rolling_back` state
machine) for a scenario that cannot occur with the update pipeline as it
exists today.

## Decision

Leave `restore` un-wired from automatic rollback until an actual
persistent-data migration step exists somewhere in `prepare` / `stage` /
`activate`. When that step is designed, wiring its failure path to
`restore_backup` (using the transaction's own `backup_id`, already carried
on the snapshot from `create_backup`) becomes straightforward — the
backup's recorded `source.appliance_version` will match the
just-restored `previous` release by construction, so it will restore
without needing `--force`. This is a natural extension of that future
design, not a prerequisite for it.

This matches the project's standing preference against building for
hypothetical requirements (see AGENTS.md / CONTRIBUTING.md and the
judgment calls recorded throughout `docs/research/`): there is no present
scenario this protects against, only a future one that doesn't have a
design yet.

## ROADMAP disposition

This closes the ambiguity in Milestone 2's third named gap. It is no
longer open work blocking the milestone; it is a recorded, deliberate
deferral. See [ROADMAP.md](../../ROADMAP.md) Milestone 2 for the updated
wording and the link back to this note.
