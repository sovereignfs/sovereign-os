# Console Authentication Hardware Qualification Report

**Date:** 2026-08-01

## Purpose

Verify the ADR-0007 authentication mechanism — `console-auth`,
`sovereign-console-password`, session cookies, CSRF protection, and rate
limiting — actually works end-to-end on physical Raspberry Pi 5 hardware,
under systemd's real `DynamicUser`/`SupplementaryGroups` enforcement and
behind the real Nginx proxy, not just against the local unit-test server.

## Method

Deployed onto the device (still running the real, shipped
`0.1.0-preview.17`, `committed`) without a full update transaction, matching
this project's established manual-qualification pattern:

1. Installed the `sovereign-console` group via the real declarative
   `systemd-sysusers` mechanism (not a manual `groupadd`).
2. Bootstrapped `/data/sovereign/console` with the same ownership/mode
   `proof-init` will apply on real images.
3. Deployed `console-auth` and `sovereign-console-password` into the live
   release tree and `/usr/sbin/`.
4. Deployed the updated Nginx config, **validated with `nginx -t` before
   reloading**, and the updated Console frontend assets.
5. Installed and started `sovereign-console-auth.service`.

Before any of this, recorded SHA-256 checksums of every file about to be
modified, specifically to make the revert verifiable rather than assumed.

## Result

Every check passed against the real service, through the real Nginx proxy:

- `GET /api/v1/auth/session` before any login: `{"authenticated": false}`.
- `POST /api/v1/auth/login` before a credential exists: `503
  not_configured`.
- After setting a credential: wrong password → `401 invalid_credentials`;
  correct password → `200`, `Set-Cookie` with `HttpOnly`, `SameSite=Strict`,
  `Max-Age=28800`, and a `csrf_token` in the body.
- `GET /api/v1/auth/session` with the session cookie returned the *same*
  `csrf_token` as login — confirms the fix (made before this campaign) that
  lets a reloaded page still be able to sign out.
- `POST /api/v1/auth/logout` without the CSRF header: `403 csrf_mismatch`.
  With the correct header: `200`, cookie cleared (`Max-Age=0`).
- Six rapid wrong-password attempts: the first five returned `401`, the
  sixth returned `429 rate_limited` — exactly the designed 5-per-5-minute
  threshold.
- Throughout, Console (`/console/`, `200`), health (`/api/v1/health`,
  `200`), Pi-hole admin (`/dns/admin/`, `302`), and DNS resolution were all
  unaffected.
- Separately verified the **interactive** `sovereign-console-password`
  script (not just the login backend) under a real allocated pty via `ssh
  -t`: it correctly refuses a piped, non-tty stdin (matching
  `sovereign-pihole-password`'s own behavior), and under a real terminal
  session it prompted, hashed, and wrote the credential with the correct
  `root:sovereign-console`, `0640` ownership — a subsequent login with that
  password succeeded.

## Cleanup

Every modified file was restored from its **exact original bytes**, not
reconstructed from git history — git history at the time of revert did not
match the live device (the running release predates later, unrelated
documentation commits, and `index.html` carries a build-time version
substitution that source control never contains literally). The correct
source of truth was the real `v0.1.0-preview.17` update bundle downloaded
earlier in this session, unpacked locally, and confirmed by SHA-256 to
match the pre-qualification device state exactly before being used to
restore it. All four modified files verified byte-identical to their
pre-qualification checksums afterward; the new group, directory, systemd
unit, and binaries were removed entirely; `systemctl --failed` empty;
`sovereign-update status` unchanged at `0.1.0-preview.17`/`committed`;
Console, health, and DNS all confirmed healthy after the revert.

## Recommendation

The mechanism is now proven on real hardware end-to-end, including the
part most likely to fail silently in unit tests alone — `DynamicUser`
actually being able to read a group-permissioned secret file through
`SupplementaryGroups`, and Nginx actually forwarding `X-Real-IP` correctly
for rate limiting. Remaining before this ships through a real release:

- No mutating action exists yet for this to gate, per ADR-0007's own
  scope — that is the next real piece of work, once the "Update Discovery
  and Console Controls" milestone defines what Console should actually be
  allowed to trigger.
- This has only ever been deployed manually for qualification; it has
  never shipped through an actual signed release install the way
  `restore` now has (see the
  [production-signed restore qualification report](production-signed-restore-qualification-report.md)).
