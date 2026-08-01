# Console Check-Trigger Hardware Qualification Report

**Date:** 2026-08-01

## Purpose

Verify the ADR-0008 mechanism — `console-auth`'s new trigger endpoint,
the `systemd` path-activated oneshot runner, and `console-health`'s new
read endpoint — actually works end-to-end on physical Raspberry Pi 5
hardware, deployed permanently (not reverted) alongside the already-live
Console authentication from earlier this session.

## Two real bugs found and fixed before qualification passed

Both were caught by deploying to real hardware, not by the unit test
suite — neither is the kind of thing a test running entirely in a normal
process, with no `systemd` sandbox and no pre-existing group namespace,
can catch on its own.

### 1. `sovereign-console-auth.service` had no `ReadWritePaths`

The service only ever *read* the credential file before this feature; the
unit correctly never granted write access. Adding a feature that needs to
*write* a trigger file, without also adding `ReadWritePaths`, meant
`ProtectSystem=strict` silently blocked every write attempt — the trigger
endpoint returned `503 trigger_unavailable` for every authenticated,
correctly-CSRF'd request. Fixed by adding
`ReadWritePaths=/data/sovereign/console/actions` to the unit, and added a
regression test asserting this specific line is present (a test that,
notably, would not have caught the *original* bug, since the bug was an
*absence*, not a wrong value — worth remembering: sandboxed write access
needs to be exercised against the real unit, not just asserted about
after the fact once you already know what broke).

### 2. The static group `sovereign-console` collided with `sovereign-console.service`'s own `DynamicUser` identity

Restarting the *pre-existing*, unrelated `console-health` service
(`sovereign-console.service`) after this change failed outright:
`Failed to update dynamic user credentials: User or group with specified
name already exists`. `DynamicUser=yes` derives a same-named dynamic
user/group from the unit's own name at every start; a static group
literally named `sovereign-console` (created for the *auth* service's
`SupplementaryGroups`, back when Console auth was first implemented)
collided with the *health* service's own transient identity, since both
share the `sovereign-console` prefix. This is a real, previously-unnoticed
latent defect in the Console-auth work itself, only surfaced now because
this was the first time `sovereign-console.service` was restarted after
the static group existed.

Fixed by renaming the group to `sovereign-console-secrets` everywhere
(the `sysusers.d` file — itself renamed —,
`sovereign-console-auth.service`'s `SupplementaryGroups`, `proof-init`'s
directory bootstrap, and `sovereign-console-password`'s default), with a
comment at the declaration site explaining why the name is deliberately
not `sovereign-console`. Verified the rename didn't leave orphaned state:
`groupdel sovereign-console` after re-`chgrp`-ing every affected path,
confirmed via `getent group sovereign-console` returning nothing
afterward.

A downstream symptom cascaded from bug #2 while `console-health` was
crash-looping: `sovereign-local-access.service` (which polls local HTTP
reachability) also failed, since every poll returned `502` while
`console-health` was down. Confirmed this was purely a transient symptom,
not a separate bug — it recovered cleanly (`active (exited)`, success) on
its own once retried after the actual fix landed.

## Method, after both fixes

1. Deployed the corrected `console-auth`, `console-health`, frontend
   assets, `sovereign.conf`, and the new `.path`/`.service` units to the
   live `v0.1.0-preview.18` release tree and `/etc/systemd/system/`.
2. To avoid disturbing the real Console credential the device owner had
   already set and verified working, backed up the real credential file
   (checksum recorded), temporarily wrote a known test credential, ran
   the full qualification below, then restored the real file from the
   backup — verified byte-identical by checksum afterward.
3. Exercised the complete real chain over HTTP through the real Nginx
   proxy:
   - `GET /api/v1/update/check` before any trigger: `{"status":
     "never_checked"}`.
   - `POST /api/v1/console/actions/check` without a session: `401`.
   - Login, then trigger with a wrong CSRF token: `403`.
   - Trigger with the correct CSRF token: `202 {"triggered": true}`.
   - Within ~1 second, `sovereign-console-check-trigger.service` fired
     (confirmed via `systemctl status`: `ExecStartPre` removed the
     trigger file, `ExecStart` ran `sovereign-update check`, both
     `code=exited, status=0/SUCCESS`).
   - `GET /api/v1/update/check` afterward reflected the *real* result of
     that real check: `up_to_date`, `current_version:
     "0.1.0-preview.18"`, `error: "DOWNGRADE_REJECTED"` — correct, since
     `.18` is the newest real published release right now.
   - An immediate second trigger: `429 {"error": "cooldown"}` with
     `Retry-After: 56`.
4. Confirmed no regression: no failed units, Pi-hole healthy, Console and
   health endpoints responding, DNS resolving, `sovereign-update status`
   unchanged at `0.1.0-preview.18`/`committed` (this feature never
   touches the update-transaction state machine).

## Result

The full ADR-0008 mechanism works exactly as designed on real hardware,
after fixing two real defects the design review alone did not catch.
This deployment, like the Console-auth deployment before it, is left in
place permanently rather than reverted — real drift against the last
tracked image build, accepted per the same trade-off discussed when
Console auth was first deployed this way.

## Recommendation

None further for this feature. The next natural piece of related work
remains what ADR-0008 already scoped out: extending this mechanism (or
choosing a different one, per the ADR's own Revisit Conditions) to an
action with real parameters or higher blast radius, such as a
Console-triggered install.
