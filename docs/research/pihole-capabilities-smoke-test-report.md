# `pihole.status` and `pihole.summary` Smoke Test Report

**Date:** 2026-08-09

**Hardware:** Raspberry Pi 5 (`sovereign.local`), the project's qualification
device, running its real Pi-hole instance (`pihole/pihole:2026.04.1`) —
the same device
[docs/research/pihole-api-assessment.md](pihole-api-assessment.md) verified
the underlying API endpoints against earlier the same day.

**Status:** First real-hardware execution of the
[RFC-0003](../rfcs/0003-capability-contract.md) executor pipeline end to
end, running the [RFC-0006](../rfcs/0006-pihole-capability-mapping.md)
`pihole.status`/`pihole.summary` implementations against the live device.
Not a full qualification pass in this project's usual sense — there is no
Conversation Service yet to invoke these for real — but a genuine,
unmocked round trip proving the implementation (built and unit-tested
against mocked HTTP responses only, see the
[implementation commit](https://github.com/sovereignfs/sovereign-os/commit/61733d2))
behaves correctly against the real API, not just the mock's assumptions
about it.

## Method

`sovereign_capabilities.py` and `sovereign_pihole.py` were copied
unmodified to `/tmp/sovereign-smoke/lib/` on the device (plain `scp`, no
privilege needed — these are read-only library files). A small driver
script registered both capabilities into a real `Registry` and invoked
each through the real, unmodified `capabilities.invoke()` pipeline — the
exact same six-stage executor this milestone's RFC-0003 defines — with no
test doubles, no mocked `urllib`, and no fixture data anywhere in the
path.

Reading the Pi-hole credential from `/data/sovereign/secrets/pihole-admin-password`
requires root, so the project owner ran the driver script themselves via
`sudo python3 /tmp/sovereign-smoke/pihole-smoke-test.py` — the assistant
never had read access to that file and did not need it to.

## Results

```console
=== pihole.status ===
{
  "status": "ok",
  "result": {
    "reachable": true,
    "blocking_enabled": true,
    "checked_at": "2026-08-09T14:17:03Z"
  }
}
=== pihole.summary ===
{
  "status": "ok",
  "result": {
    "period": "last_24h",
    "queries_total": 563,
    "queries_blocked": 200,
    "blocked_percentage": 35.52397918701172,
    "blocklist_size": 99276,
    "unique_clients": 5,
    "checked_at": "2026-08-09T14:17:03Z"
  }
}
=== audit log ===
{"capability":"pihole.status","duration_seconds":0.209313,"network":"local","outcome":"executed","result_bytes":78,"side_effect":"read_only","stage_reached":"audited","timestamp":"2026-08-09T14:17:03Z","version":1}
{"capability":"pihole.summary","duration_seconds":0.003027,"network":"local","outcome":"executed","result_bytes":180,"side_effect":"read_only","stage_reached":"audited","timestamp":"2026-08-09T14:17:03Z","version":1}
```

Both capabilities executed automatically, with no confirmation gate
encountered — correct, since both are classified `read_only`/`local`
(RFC-0003's structural table maps that combination to `automatic`
confirmation), and the pipeline genuinely reached stage `audited` for
both rather than stopping short.

`pihole.summary`'s composition of the two real endpoints
(`GET /stats/database/summary` for the period-scoped counts,
`GET /stats/summary` for `blocklist_size`/`unique_clients`) produced
internally consistent numbers: `queries_blocked / queries_total`
(`200 / 563 ≈ 35.5%`) matches the independently-reported
`blocked_percentage` (`35.52...%`) to within Pi-hole's own rounding —
confirming the two separate API calls this implementation makes are
being combined correctly, not just each individually well-formed.

The audit log is exactly the shape RFC-0003 requires: classification
(`side_effect`, `network`), pipeline outcome (`stage_reached`,
`outcome`), and cost (`duration_seconds`, `result_bytes`) — no query
content, no domain names, no client identities. This is the first time
that audit shape has been produced from a real invocation rather than a
unit test's fixture data.

## Limitations

This is not equivalent to the project's usual hardware qualification
passes (compare the dated reports for `prune`/`rotate-trust`/base-OS
updates): it ran a hand-written driver script directly, not a real
caller (no Conversation Service exists yet), exercised only the
already-covered happy path (no live rejection, confirmation, or failure
case was reproduced against the real device — those are already covered
by the 54 mocked unit tests, not re-verified here), and used a scratch
directory cleaned up immediately after. Treat this as confidence that
the implementation's real-world behavior matches its test doubles, not
as a substitute for qualifying it once wired into an actual invocable
path.

## Conclusion

`pihole.status` and `pihole.summary` behave identically against the real
Pi-hole API as they do against this project's mocked test fixtures — the
mocks accurately modeled the real API's shape and behavior. No
discrepancy was found. Full end-to-end qualification (a real caller, a
real rejection/confirmation/failure path exercised live) should happen
once these capabilities are reachable through an actual Conversation
Service rather than a scratch driver script.
