# Shared Console-Session Gate (ADR-0010) Hardware Qualification Report

**Date:** 2026-08-06

## Purpose

Verify ADR-0010's `auth_request`-based gate — `/dns/` bounced to Console's
sign-in when unauthenticated, reachable once a valid Console session
exists — actually works end-to-end on physical Raspberry Pi 5 hardware,
behind the real Nginx proxy and against the real `console-auth` service,
not just against the local unit-test server and a local mock.

## Method

Deployed onto the qualification device (running the real, shipped
`0.1.0-dev`) without a full update transaction, matching this project's
established manual-qualification pattern:

1. Recorded SHA-256 checksums of every file about to be modified, before
   touching anything, specifically to make the revert verifiable rather
   than assumed: `nginx/sovereign.conf`, `bin/console-auth`,
   `bin/verify-local-access`, `bin/verify-update-health`,
   `console/index.html`, `console/assets/console.js`.
2. Copied the exact original bytes of each file to a scratch location on
   the device, as the real revert source (not git history, which does not
   necessarily match the live device's currently-running release).
3. Deployed the updated files into the live release tree, **validated the
   Nginx config with `nginx -t` before ever reloading**.
4. Reloaded Nginx and restarted `sovereign-console-auth` to pick up the
   new `/api/v1/auth/verify` endpoint.
5. Exercised the gate from both the device's own loopback (`curl`) and a
   real browser pointed at `http://sovereign.local/`.
6. Reverted every file from its saved original bytes, reloaded/restarted
   the same two services, and deleted the throwaway Console credential
   created for this test, restoring the device to its exact prior state.

## Finding: the `nginx-full` package pin was wrong

The original implementation pinned `nginx-full` in `sovereign-proof.yaml`,
reasoning that Debian's bare `nginx` metapackage resolves to `nginx-light`,
which lacks `ngx_http_auth_request_module`. That reasoning holds for older
Debian releases but **not for this image's actual base, Debian 13
(trixie)**: `apt-cache policy nginx-full` on the device reports `N: Unable
to locate package nginx-full` — trixie no longer splits nginx into
light/full/extras variants — and `nginx -V` on the plain, already-installed
`nginx` package (1.26.3-3+deb13u7) confirms
`--with-http_auth_request_module` is already compiled in. The package pin
would have broken the image build outright. Reverted `sovereign-proof.yaml`
to the original plain `nginx` package and corrected the test that had
asserted the wrong pin (see `tests/test_console_auth.py`,
`test_nginx_package_is_unchanged`).

## Result

Every check passed against the real service, through the real Nginx proxy:

- `nginx -t`: syntax OK, both before and after every reload in this
  session.
- Unauthenticated `GET /dns/admin/` (loopback and real browser, at
  `http://sovereign.local/dns/admin/`): `302` to
  `http://127.0.0.1/console/?next=/dns/admin/` — confirmed the real
  browser lands on `/console/?next=/dns/admin/` with the sign-in form
  auto-expanded and the "Sign in to continue." message, matching the
  frontend logic.
- `GET /api/v1/auth/verify` and the internal
  `/api/v1/auth/verify-internal` location: both `404` to a direct,
  unauthenticated-context request from outside the intended path — neither
  is reachable except as an Nginx-internal `auth_request` subrequest,
  confirmed by `internal;` actually being enforced.
- After signing in through the real Console page in a real browser
  (throwaway credential, created and destroyed only for this test):
  browser automatically redirected from `/console/?next=/dns/admin/` to
  `/dns/admin/`, which the gate now let through and which then correctly
  showed **Pi-hole's own** login page (`title: "Pi-hole
  74d985ac3718"`, `/dns/admin/login`) — exactly ADR-0010's documented,
  accepted tradeoff: the Console session gates *reachability*, not
  Pi-hole's own separate session.
- A debug pass (`auth_request_set` + temporary `X-Debug-Auth-Status`
  response header, removed before the final revert) confirmed the
  `auth_request` subrequest itself returned `204` for the authenticated
  case — the `302` seen at that point was conclusively Pi-hole's own
  redirect, not a gate failure, resolving an initial misread of the
  result during this session.
- `verify-local-access` (the boot readiness script, now asserting the
  gate's redirect target instead of raw Pi-hole content per this
  branch's fix) ran for real as root and produced a marker file with
  `pihole_gate=pass` alongside every other check passing, including
  `health_api=pass`.
- The equivalent `verify-update-health` check (`check_dns_admin_proxy`,
  now comparing the redirect target the same way) was verified in
  isolation against the live gate and matched the expected value exactly.
- Console (`/console/`, health, session state) and DNS resolution were
  unaffected throughout.

## Cleanup

Every modified file was restored from its exact original bytes (copied
from the live device before any change, not reconstructed from git
history). Nginx and `console-auth` were reloaded/restarted again after the
revert. The throwaway Console credential created to test the authenticated
path was deleted (`/data/sovereign/console/admin-password.hash` — absent
both before and after, confirmed by direct existence check, matching the
device's real pre-qualification state where no Console credential had yet
been set). All six modified files verified **byte-identical** (SHA-256) to
their pre-qualification checksums afterward. Post-revert: unauthenticated
`/dns/admin/` again reaches Pi-hole's own (ungated) redirect directly,
`/api/v1/auth/session` reports `{"authenticated": false}` with no
credential configured, and `/api/v1/health` reports `"status":"healthy"`
across every check. All scratch files and directories used for this pass
were removed from the device and this machine.

## Recommendation

The mechanism is proven end-to-end on real hardware, including the one
thing a local mock couldn't have exercised: that Nginx's `auth_request`
module is actually present and correctly wired against the real,
already-installed `nginx` package on this image's real Debian base — which
also surfaced and fixed a real implementation bug (the `nginx-full` pin)
before it could have broken a real image build. Remaining before this
ships through a real release:

- This has only ever been deployed manually for qualification, the same
  as every other manually-qualified mechanism in this project before its
  first real signed release; it has not yet gone through an actual update
  transaction.
- The `?next=` allowlist currently covers only `/dns/`; extending it (and
  adding the matching `auth_request` block) is the expected, minimal
  per-service pattern ADR-0010 already describes for future service
  panels.
- `console-auth` being down now makes every gated panel unreachable too
  (ADR-0010's own named risk) — not separately load/failure tested in this
  pass beyond confirming the mechanism works when `console-auth` is
  healthy.
