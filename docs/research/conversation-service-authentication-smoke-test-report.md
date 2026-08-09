# Conversation Service Authentication Smoke Test Report

**Date:** 2026-08-09

**Hardware:** Raspberry Pi 5 (`sovereign.local`), the project's qualification
device, still on release `0.1.0-proof.3`.

**Status:** First real-hardware exercise of the auth wiring added between
`bin/sovereign-conversation` and console-auth's new
`GET /api/v1/auth/verify-mutating` — real HTTP round trips for all three
outcomes (no session, valid session with a bad/missing CSRF token, valid
session with the correct CSRF token), including one full authenticated
turn that reaches real inference and executes a real capability.

## Method

Unlike the [prior Conversation Service smoke test](conversation-service-smoke-test-report.md),
this run needed **no sudo for the application processes**: the
auth-success test case was scoped to `system.health` rather than a
Pi-hole capability, so `bin/sovereign-conversation` never needed to read
the root-only Pi-hole secret and could run as the ordinary `sovereign`
user throughout.

A second, disposable instance of `console-auth` was started on a scratch
port (`8191`, not the real `8091`) with a throwaway credential the
assistant generated and hashed itself (`console-auth`'s own
`hash_password()`, called directly — nothing sensitive, since this
credential exists only for this test and is discarded with the rest of
the scratch directory). `bin/sovereign-conversation` was pointed at it
via `SOVEREIGN_CONSOLE_AUTH_BASE_URL=http://127.0.0.1:8191`. This
deliberately avoids two riskier alternatives: replacing the real,
already-running production `console-auth` process (which is actively
protecting the real Console and predates this session's
`verify-mutating` endpoint), and asking for the real Console admin
password, which the assistant must never handle even with permission.
The real `console-auth` (pid confirmed throughout, still serving
`/api/v1/auth/session` at the end) was never touched.

llama-server was started the same way as the prior report (fresh
Qwen2.5-3B-Instruct-Q4_K_M download, Docker, project owner's own
terminal — the only sudo step this run needed).

Four real HTTP round trips were made directly against the scratch
`sovereign-conversation` instance's `/api/v1/conversation/message`:

## Results

**No `Cookie` header at all:**

```json
{"error":{"code":"NOT_AUTHENTICATED","message":"a valid Console session is required"}}
```

`HTTP 401`, matching `_check_authentication()`'s mapping of
console-auth's `401` response.

**Valid session cookie, no `X-CSRF-Token` header:**

```json
{"error":{"code":"CSRF_MISMATCH","message":"missing or invalid CSRF token"}}
```

`HTTP 403`.

**Valid session cookie, wrong `X-CSRF-Token` value:** same `403
CSRF_MISMATCH` — confirms the check compares the actual token, not just
presence.

**Valid session cookie and the correct CSRF token** (both obtained from
a genuine `POST /api/v1/auth/login` round trip against the scratch
console-auth, using the throwaway password): the request correctly fell
through to real inference. The model proposed `system.health`, it
executed against the real registry (temperature `81.0°C` — see
Observation below), and the narration came back correctly:

```
"The system is healthy. There are no degraded components detected."
```

`HTTP 200`, `capability_events: [{"name": "system.health", "outcome":
"executed"}]`, one matching audit log entry (`stage_reached: "audited"`,
`outcome: "executed"`) — same shape the [earlier smoke test](conversation-service-smoke-test-report.md)
already established.

## Observation (not a finding)

The real device reported `temperature_celsius: 81.0` during this run —
1°C above [ADR-0012](../adrs/0012-local-inference-resource-and-dns-latency-budgets.md)'s
80°C thermal budget, under only a single short-lived turn's worth of
inference load, not sustained use. This isn't a new discrepancy; it's
one more real data point toward the "realistic intermittent-use thermal
pass" ADR-0012 already lists as a non-blocking open Required Follow-up
item, not something this smoke test needed to resolve.

## Cleanup, verified rather than assumed

Both scratch processes were owned by the assistant's own unprivileged
SSH session this run (not root), so they were stopped directly rather
than requiring the project owner — confirmed by checking that the real,
production `console-auth` process (a distinct, still-running pid on the
real `8091`) was never among the processes matched or killed, and that
it still answered `/api/v1/auth/session` (`200`) after cleanup. After
the project owner removed the llama-server container, `127.0.0.1:8081`
was confirmed unreachable before the scratch directory was deleted.
Deleting the scratch directory's *contents* needed no privilege (the
assistant owned everything in it), but removing the now-empty directory
*entry itself* did — the same reason creating it needed `sudo` in the
first place: `/data` itself is root-owned, and removing a directory
entry requires write permission on its parent, not the directory being
removed. One final `sudo rmdir` closed that out.

## Limitations

This validates the real `console-auth` ↔ `sovereign-conversation` HTTP
delegation and the real session/CSRF logic on both sides, on real
hardware — but against a disposable `console-auth` instance, not the
live production one (a deliberate, disclosed choice, not an oversight —
see Method). Nginx's routing of `/api/v1/conversation/{health,message}`
onto the LAN-facing surface was not exercised live here; that's config
already covered exactly by
[`tests/test_console_auth.py`](../../tests/test_console_auth.py)'s
`ConversationServiceGatingProvisioningTests`, and real nginx wasn't
touched to avoid any risk to the actual LAN-facing Console during this
pass. Only `system.health` was used for the success-path round trip
(Pi-hole capabilities' own auth-independent behavior was already proven
in the prior smoke test).

## Conclusion

The Conversation Service's authentication wiring behaves correctly
against real HTTP traffic on real hardware: rejects with the right code
for no session, rejects with the right code for a missing or wrong CSRF
token even with a valid session, and correctly proceeds to real
inference and real capability execution once both checks pass — with no
behavioral gap from what the 4 new unit tests already predicted. Real
production services (`console-auth` on `8091`, the actual Console a
household would use) were never touched or interrupted by this pass.
