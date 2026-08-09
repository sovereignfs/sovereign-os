# Pi-hole API Assessment

**Status:** Concluded
**Author:** Project creator and Claude
**Started:** Planned, date unrecorded
**Concluded:** 2026-08-09
**Decision informed:** [RFC-0006 (Pi-hole capability mapping)](../rfcs/0006-pihole-capability-mapping.md)

## Question

Which supported Pi-hole APIs, authentication method, permissions, and
response semantics can safely implement `pihole.status` and
`pihole.summary`, the two read-only capabilities RFC-0006 registers?

## Context

RFC-0006 named this document's open questions as blocking implementation
(though not blocking the RFC's own acceptance): exact endpoint paths and
response shapes, whether a least-privilege credential exists, and real
rate-limit/error behavior, all verified against the actual pinned
Pi-hole image this device runs
(`pihole/pihole:2026.04.1`, per
[image-builder/sovereign/pihole-image.env](../../image-builder/sovereign/pihole-image.env)),
not general upstream documentation. The only existing Pi-hole
integration, `console-health`, only performs a bare TCP check on port
8080 and never calls Pi-hole's real API — there was no prior empirical
basis for this document at all.

## Sources and Environment

- Raspberry Pi 5 (`sovereign.local`), this project's qualification
  device, running the pinned Pi-hole image above.
- Pi-hole's REST API, reached directly at `http://127.0.0.1:8080/api/`
  from the device itself (the same origin `console-health` already
  probes for its coarser TCP check).
- Pi-hole self-serves its own complete, version-matched OpenAPI 3.0.2
  specification, unauthenticated, at `/api/docs/specs/main.yaml` (and
  per-tag files it `$ref`s: `auth.yaml`, `stats.yaml`, `dns.yaml`,
  `info.yaml`, `common.yaml`, etc.) — this is the actual spec the
  running FTL binary documents itself with, not a copy of generic
  upstream docs, and confirms the live instance identifies as API
  version `"6.0"`.
- A real authenticated round trip was performed against the live
  device: the project owner set a fresh Pi-hole administrator password
  via the existing `sudo sovereign-pihole-password` tool (the assistant
  never saw or handled the password, consistent with this project's
  standing password-handling constraint), then ran a short, disposable
  script that authenticated, called the two candidate endpoints, and
  logged out — output pasted back and reviewed here. The assistant
  never held the password or the resulting session's credential
  material beyond the ephemeral SID visible in that pasted output,
  which was invalidated by logout before this document was written.

## Findings

Findings are separated into what was directly observed (spec content,
real HTTP responses) versus inference drawn from them.

### Observed: Authentication

- `POST /api/auth` with JSON body `{"password": "<password>"}` is the
  login call. A correct password returns
  `{"session": {"valid": true, "sid": "<opaque>", "csrf": "<opaque>",
  "validity": 1800, "message": "password correct"}, "took": <seconds>}`
  — verified live: a real wrong password first returned
  `{"session": {"valid": false, "sid": null, "validity": -1, "message":
  "password incorrect"}}`, and after the password was reset, a real
  correct password returned a live `sid`.
- The session lasts 1800 seconds (30 minutes) by default
  (`session.validity`), extended by further authenticated activity per
  the spec's description.
- The `sid` is presented on subsequent requests via an `sid` header (also
  supported via cookie or query parameter per the spec) — verified live
  against `GET /api/dns/blocking` and `GET /api/stats/summary`, both of
  which returned `401 {"error": {"key": "unauthorized", ...}}` before
  authentication and real data after.
- `DELETE /api/auth` with the `sid` header ends the session —
  verified live, returned `204 No Content`.
- The spec documents login rate-limiting (`429`, error key
  `rate_limiting`, message "Rate-limiting login attempts") and a
  concurrent-session cap (`429`, error key `api_seats_exceeded`, hint
  "increase `webserver.api.max_sessions`") — not independently
  triggered during this pass (doing so deliberately would have required
  either many real failed logins or exhausting real session seats,
  neither justified for this research), but present in the same
  self-served spec that already matched every other behavior observed
  live.

### Observed: No Least-Privilege Credential Exists

Pi-hole v6's only alternative to the full administrator password is an
*application password* (`GET /api/auth/app`, itself requires an existing
authenticated session). Per the spec's own description: it "can be used
to authenticate against the API **instead of** the regular password,"
carries the same authority as the regular password (no read-only or
scope-limited variant exists), and **generating one invalidates all
currently active sessions** — disruptive to anyone concurrently logged
into the Pi-hole web UI. This directly answers RFC-0006's open question:
**no least-privilege or read-only credential is available** on this
Pi-hole version. RFC-0006's "accepted, broader-than-necessary risk"
fallback is not a fallback — it is the only option Pi-hole v6 actually
offers.

### Observed: `pihole.status` Source

`GET /api/dns/blocking` — verified live, returned
`{"blocking": "enabled", "timer": null, "took": <seconds>}` against the
device's real, currently-enabled blocking state. The spec's `blocking`
enum is `"enabled" | "disabled" | "failed" | "unknown"`, plus a `timer`
field (seconds remaining until an active temporary toggle expires,
`null` when the state is permanent).

**Important, security-relevant finding:** `GET /api/dns/blocking` and
`POST /api/dns/blocking` are the *same URL* — the POST verb is what
changes blocking state (`{"blocking": true/false, "timer": ...}`). This
is not a separate mutating endpoint with a different path; it is the
same resource with a different HTTP method. The `pihole.status`
capability implementation must be hard-restricted, at the code level, to
issuing GET requests only against this path — never merely "intending"
not to send a POST.

### Observed: `pihole.summary` Source, and a Two-Endpoint Correction

RFC-0006 assumed a single endpoint could answer a period-scoped summary
question. The real API splits this across two different endpoints, each
verified live:

- **`GET /api/stats/database/summary?from=<unix>&until=<unix>`** — the
  period-scoped, historical endpoint. Both `from` and `until` are
  required Unix timestamps (seconds). Verified live for the last 24
  hours, returning `{"sum_queries": <int>, "sum_blocked": <int>,
  "percent_blocked": <number>, "total_clients": <int>, "took": <seconds>}`
  — exactly matching the spec's declared schema, and confirming
  `total_clients` is a count only, with no per-client field anywhere in
  this response.
- **`GET /api/stats/summary`** (no query parameters) — a *live*,
  current-state endpoint, not period-scoped. Verified live; its
  top-level response shape is `{"queries": {...detailed live counters
  by type/status/reply...}, "clients": {"active": <int>, "total":
  <int>}, "gravity": {"domains_being_blocked": <int>, "last_update":
  <unix timestamp>}, "took": <seconds>}`. **This corrects a
  misreading of the spec file's nesting**: the OpenAPI schema declares
  `clients` and `gravity` as properties alongside `queries` inside one
  combined schema object, which a first read suggested might mean they
  are nested *under* `queries` in the actual response — live output
  showed they are siblings of `queries` at the top level instead. This
  is exactly the kind of gap between "what the schema seems to imply"
  and "what the server actually returns" that empirical verification
  against the real pinned instance exists to catch, and general
  documentation reading would not have caught.

Because `blocklist_size` (`gravity.domains_being_blocked`) and an
active-client count (`clients.active`, a rolling last-24-hours figure
per its own description, not scoped to an arbitrary requested period)
only exist on the live, unscoped endpoint, `pihole.summary`'s
implementation needs **two** real API calls per invocation — the
period-scoped `database/summary` for `queries_total`/`queries_blocked`/
`blocked_percentage`, and the live `summary` for `blocklist_size` and
`unique_clients` — not one, and RFC-0006's schema should be read with
that composition in mind rather than assuming a single upstream call.

### Observed: No Client-Identity or Domain-Level Leakage in Either Source

Both endpoints used above (`database/summary` and `summary`) return only
counts and percentages — no domain names, no client IP addresses or
hostnames, no per-query timestamps. This empirically validates RFC-0006's
aggregate-only design rather than merely asserting it.

The same spec also documents real, readily-available endpoints that
**would** leak exactly what RFC-0006 excludes, named here so a future
implementer sees the temptation was considered and deliberately
declined, not overlooked:

- `GET /api/stats/recent_blocked` — returns an actual list of recently
  blocked domain names.
- `GET /api/stats/top_clients` / `GET /api/stats/top_domains` — return
  per-client and per-domain identification and counts.

None of these are used by `pihole.status` or `pihole.summary`, and
RFC-0006's Non-Goals already excludes them; this document is the
concrete evidence that exclusion is a real, available capability being
turned down, not a hypothetical one.

### Observed: Error Taxonomy

Every error response observed, and every error example in the spec,
shares one shape: `{"error": {"key": "<machine-readable>", "message":
"<human-readable>", "hint": <string-or-null>}, "took": <seconds>}`.
Keys observed live or documented for these two endpoints' realistic
failure paths: `unauthorized` (401, missing/invalid/expired session),
`rate_limiting` (429, too many login attempts), `api_seats_exceeded`
(429, concurrent session cap reached), and `bad_request`/`body_error`
(400, malformed request body — relevant to the login call, not to the
two read-only GET endpoints, which take no body). This taxonomy maps
directly onto RFC-0003's bounded-execution failure path: each key is a
distinct, classifiable failure reason for the capability implementation
to report, not an undifferentiated error string.

### Inference: Session Management Strategy

Given the 30-minute session lifetime, extension-on-activity, and a real
concurrent-session cap that a household's own Pi-hole web-UI login also
competes for, the capability implementation should authenticate once and
reuse/refresh a single long-lived session across invocations, rather
than authenticating fresh per capability call. Authenticating per-call
would needlessly consume a seat against `webserver.api.max_sessions` on
every single `pihole.status`/`pihole.summary` invocation and risks
starving a household member's own concurrent web UI login. This is
inference from the observed session/seat model, not itself independently
load-tested.

## Gaps and Limitations

- Rate-limiting and seat-exhaustion behavior were confirmed to exist in
  the spec and were not independently triggered live — deliberately, to
  avoid locking out the device's real Pi-hole admin access during this
  pass. If precise thresholds matter for implementation, they should be
  measured in a dedicated qualification pass, not assumed from the spec
  alone.
- This assessment covers exactly the two endpoints RFC-0006 needs. It
  does not attempt a full inventory of Pi-hole's API (DHCP, group/domain/
  client management, Teleporter export, etc.) — out of scope for this
  milestone's read-only, non-mutating capabilities.
- Verified against `pihole/pihole:2026.04.1` specifically. A future
  Pi-hole image upgrade could change endpoint shapes; this document
  reflects the version pinned at the time of writing, not a permanent
  guarantee.

## Recommendation

Implement `pihole.status` against `GET /api/dns/blocking` (GET-only,
enforced at the code level) and `pihole.summary` as a composition of
`GET /api/stats/database/summary?from=&until=` (period-scoped counts)
and `GET /api/stats/summary` (blocklist size, active-client count),
using a reused/refreshed long-lived session rather than per-call
authentication. Use the existing admin password as the capability's
credential, stored per RFC-0006 under `/data/sovereign/secrets` and
unreachable from the Conversation Service/model — there is no
least-privilege alternative to fall back to, so this is an accepted,
documented risk rather than an oversight. Map the four observed error
keys (`unauthorized`, `rate_limiting`, `api_seats_exceeded`,
`bad_request`) onto RFC-0003's bounded-execution failure classification
directly.

## Unresolved Questions

- Exact `webserver.api.max_sessions` default and whether it needs
  raising for Sovereign's own long-lived session to coexist comfortably
  with normal household web-UI use — an operational tuning question for
  implementation, not an architectural one.
- Precise rate-limit thresholds (attempts per window) — not measured
  live in this pass (see Gaps and Limitations).
- Whether Pi-hole's own credential storage format changes across future
  version upgrades in a way that would require re-verifying this
  document's findings — a standing maintenance question for whichever
  Pi-hole image bump is next.

## Decision Impact

Resolves RFC-0006's three deferred "must still confirm" items (exact
endpoint shapes, least-privilege credential availability, and error/
rate-limit behavior) with real, live-verified evidence against the
actual pinned Pi-hole version, rather than assumed general-documentation
behavior. RFC-0006 should be read alongside this document's two
corrections: `pihole.summary` requires two API calls, not one, and no
least-privilege credential exists, so the credential-handling section's
"fallback" is the only real path.
