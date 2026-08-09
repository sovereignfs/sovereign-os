# RFC-0006: Pi-hole Capability Mapping

**Status:** Accepted (2026-08-09, project creator)
**Author:** Project creator and Claude
**Created:** 2026-08-09
**Reviewers:** Project creator
**Target phase:** [Milestone 01.2, Local Conversation and Capabilities](../roadmap/01-2-local-conversation-capabilities.md)
**Supersedes:** None

## Summary

Register the specific read-only Pi-hole capabilities the milestone plan
names, against [RFC-0003](0003-capability-contract.md)'s contract and
reachable through [RFC-0004](0004-ai-capability-invocation.md)'s
invocation path: `pihole.status` (is Pi-hole up, is blocking currently
enabled) and `pihole.summary` (aggregate query/blocking counts for a
bounded recent period). It fixes the household-privacy boundary these
capabilities must respect — no per-domain, per-client, or query-log
detail, only aggregate counts, matching the boundary Sovereign Console's
own health page already established — and the credential-handling
requirement for calling Pi-hole's real API rather than the coarse TCP
reachability check Console currently uses. This RFC does not define
mutating Pi-hole operations (explicit milestone non-scope) or generalize
beyond Pi-hole to any other appliance service.

## Problem

The milestone plan names "read-only Pi-hole health and summary
capabilities" as one of four initial capabilities, and requires a
"Pi-hole capability mapping" as its own required document (item 3 of 8).
[docs/research/pihole-api-assessment.md](../research/pihole-api-assessment.md)
was opened to investigate exactly this — endpoint-to-use-case mapping,
authentication, sensitive-field minimization — but was never completed;
its Status line still reads "Planned" with only the investigation
questions written, not answers.

Separately, the only Pi-hole integration that exists today is
`console-health`'s check (`image-builder/sovereign/appliance/bin/console-health`):
a bare TCP reachability check against Pi-hole's web port, chosen
deliberately for Console's own narrow scope ("Overall Healthy, Degraded,
or Unavailable," explicitly not query history or per-client detail —
see [docs/design/console-health.md](../design/console-health.md)'s
Non-Scope and Privacy and Trust sections). It does not call Pi-hole's
real API at all, so it cannot answer "how many queries were blocked
today" — the kind of question `pihole.summary` needs to answer. This RFC
cannot reuse `console-health`'s implementation, only its privacy
boundary, which it explicitly carries forward.

Without this RFC, an implementation would have to decide, ad hoc, which
Pi-hole data is safe to expose to a model-mediated capability — a much
more consequential decision than Console's own health page, since a
conversational interface invites the kind of specific question
("what did my kid's phone look up today") that Console's glanceable
health page never did, and that this household-facing product must
refuse by design, not by omission.

## Goals

- Register `pihole.status` and `pihole.summary` against RFC-0003's
  contract: schema, classification, and bounds.
- Fix the privacy boundary: aggregate counts only, no per-domain,
  per-client, or timestamped query-level detail, carried forward from
  `console-health`'s own established Non-Scope rather than re-litigated.
- Define how the capability implementation authenticates to Pi-hole's
  real API, and where that credential lives, without exposing it to the
  model or Conversation Service layer.
- Name what remains for `pihole-api-assessment.md` to actually verify
  against the real, pinned Pi-hole version this device runs, rather than
  asserting unverified endpoint specifics as settled.

## Non-Goals

- Any mutating Pi-hole capability (enable/disable blocking, add/remove
  blocklist entries, manage clients) — explicit milestone non-scope.
  This RFC's capabilities are exclusively `read_only`.
- Per-domain or per-client query detail, query history, or anything
  resembling browsing-history reconstruction for a specific household
  member or device — never exposed through this capability surface,
  regardless of what Pi-hole's own admin API can technically return.
- `console-health`'s existing Console-facing health check, which this
  RFC neither replaces nor depends on — they serve different consumers
  (an unauthenticated glanceable page vs. an authenticated conversation)
  with different, independently-justified scopes.
- The general capability contract, executor pipeline, or AI invocation
  flow — fixed by RFC-0003 and RFC-0004; this RFC only supplies
  Pi-hole-specific schemas and data-handling rules.
- Completing `pihole-api-assessment.md`'s full investigation (exact
  endpoint paths verified against the real running version, full error
  taxonomy, rate-limit behavior). This RFC names what that research must
  still confirm before implementation; it does not replace the research.

## Context and Evidence

- [docs/design/console-health.md](../design/console-health.md) (Accepted)
  is the direct precedent for this RFC's privacy boundary: its Non-Scope
  ("Logs, terminal, file browser, container details, or DNS query
  history") and Privacy and Trust section ("must not expose... client
  identities, queries, logs, or browsing history") already establish,
  for a different surface, exactly the boundary this RFC needs for a
  conversational one — arguably a boundary that matters *more* here,
  since a conversation actively invites specific questions a glanceable
  status page never prompted.
- `image-builder/sovereign/appliance/bin/console-health` is the only
  existing Pi-hole integration: a TCP check on port 8080, no
  authenticated API call. Read directly to confirm this RFC is not
  duplicating or silently diverging from working code.
- `image-builder/sovereign/pihole-image.env` pins the actual Pi-hole
  image this device runs (`pihole/pihole:2026.04.1`, digest-verified) —
  this RFC's API assumptions must be checked against this specific
  pinned version, not Pi-hole in general, before implementation.
- [docs/research/pihole-api-assessment.md](../research/pihole-api-assessment.md)
  (Status: Planned, never completed) already scoped the right questions
  — authentication, health/summary endpoints, sensitive-field
  minimization, least-privilege credential support — this RFC answers
  them at the architecture level and names what still needs empirical
  confirmation.
- [RFC-0003](0003-capability-contract.md)'s classification table and
  [RFC-0004](0004-ai-capability-invocation.md)'s catalog-generation
  requirement are the contract these capabilities are registered
  against; this RFC supplies their `argument_schema`/`result_schema`
  and confirms their `side_effect`/`network` classification.

## Proposal

### `pihole.status`

- **Purpose:** answer "is Pi-hole working" and "is blocking currently
  on" — a conversational equivalent of Console's own health indicator,
  not a superset of it.
- **Arguments:** none.
- **Result:** `{ "reachable": bool, "blocking_enabled": bool | null,
  "checked_at": timestamp }`. `blocking_enabled` is `null` if Pi-hole is
  unreachable — the capability reports what it actually observed, never
  guesses a default.
- **Classification:** `read_only`, `local` (the call stays inside the
  device, container-to-container; it never leaves the household network
  boundary the way `web.search` does), `automatic` confirmation per
  RFC-0003's structural table.
- **Bounds:** short timeout (matching `console-health`'s existing
  responsiveness expectations), single result, no pagination.

### `pihole.summary`

- **Purpose:** answer aggregate questions — "how many things got
  blocked today," "is the blocklist working" — without ever answering
  "what did device X look up."
- **Arguments:** `{ "period": "today" | "last_24h" }`. No arbitrary date
  range and no client or domain filter — a bounded, enumerated argument
  set is itself part of the privacy boundary, not just documentation of
  intent, since RFC-0003's argument-schema validation rejects anything
  outside it before the capability implementation ever runs.
- **Result:** `{ "period": "today" | "last_24h", "queries_total": int,
  "queries_blocked": int, "blocked_percentage": number, "blocklist_size":
  int, "unique_clients": int, "checked_at": timestamp }`. `unique_clients`
  is a count only — never a list of identities, addresses, or hostnames.
- **Classification:** `read_only`, `local`, `automatic`.
- **Bounds:** short timeout, single result, no pagination — this is a
  summary endpoint by design, not a query-log export.

No other Pi-hole fields — domain lists, client identities, per-query
timestamps, upstream DNS server detail beyond what's needed to report
`reachable` — are exposed through either capability's result schema.
RFC-0003's argument/result schema validation is what actually enforces
this: a capability implementation cannot return a field the registered
`result_schema` doesn't declare, so this boundary is structural, the
same way RFC-0003 made confirmation structural rather than a per-author
judgment call.

### Authentication and Credential Handling

Pi-hole's real API (as opposed to `console-health`'s bare TCP check)
requires authenticating a session before reading stats — confirmed live
against the real device in
[docs/research/pihole-api-assessment.md](../research/pihole-api-assessment.md)
(Concluded 2026-08-09): `POST /api/auth` with the admin password returns
a session ID valid 30 minutes, extended by activity, presented on
subsequent requests via an `sid` header. **No least-privilege or
read-only credential exists on this Pi-hole version** — its only
alternative to the full admin password is an "application password"
that carries the same full authority and invalidates every other active
session when generated. This is now a confirmed fact, not an open
question: the credential this capability uses:

- **is the existing Pi-hole administrator password, reused** — the only
  option, not a fallback among alternatives, per the research above;
- is provisioned and stored under `/data/sovereign/secrets`, inside the
  same persistent-data boundary and backup role the appliance's other
  secrets already use — the same secret `sudo sovereign-pihole-password`
  already manages, not a new, separately-tracked credential store;
- is readable only by the `pihole.status`/`pihole.summary` capability
  implementation process, never by the Conversation Service generally,
  the Inference Provider Adapter, or the model — matching RFC-0003's
  "no ambient access beyond what implementation needs" execution
  requirement; this is the boundary that actually bounds the risk of
  reusing a full-authority credential, since nothing in the conversation
  path can reach it even though the credential itself is not scope-
  limited;
- should authenticate once and reuse/refresh a single long-lived session
  across invocations rather than authenticating fresh per call, per the
  research above's session/seat-limit findings — authenticating per
  invocation would needlessly compete with a household member's own
  concurrent Pi-hole web-UI login for Pi-hole's real, confirmed
  concurrent-session cap; and
- is never logged, audited, or included in any capability result —
  RFC-0003's audit events already exclude result content, and this RFC
  adds no separate path that could leak it.

### Endpoints, Confirmed Live

[docs/research/pihole-api-assessment.md](../research/pihole-api-assessment.md)
verified both sources against the real pinned `pihole/pihole:2026.04.1`
image with a real authenticated round trip, not just the self-served
OpenAPI spec:

- `pihole.status` sources from `GET /api/dns/blocking`
  (`{"blocking": "enabled"|"disabled"|"failed"|"unknown", "timer":
  number|null}`) — mapped to this RFC's `reachable`/`blocking_enabled`
  result as: `"enabled"` → `true`, `"disabled"` → `false`,
  `"failed"`/`"unknown"` → `null` (never guessed). **Confirmed
  security-relevant detail:** `GET` and `POST /api/dns/blocking` are the
  *same URL* — POST is what changes blocking state. The implementation
  must be hard-restricted to GET only at the code level, not merely by
  intent.
- `pihole.summary` requires **two** real API calls, not one — a
  correction to this RFC's original assumption: the period-scoped
  `GET /api/stats/database/summary?from=<unix>&until=<unix>` (returns
  `sum_queries`/`sum_blocked`/`percent_blocked`/`total_clients` for the
  requested window) supplies `queries_total`/`queries_blocked`/
  `blocked_percentage`, while the live, unscoped
  `GET /api/stats/summary` supplies `blocklist_size`
  (`gravity.domains_being_blocked`) and `unique_clients`
  (`clients.active`, itself already a rolling 24-hour figure) — neither
  of which has a period-scoped equivalent in Pi-hole's own API. The
  `period` argument this RFC's schema declares is translated by the
  implementation into `from`/`until` Unix timestamps server-side; the
  model never sees or supplies raw timestamps.
- Both confirmed-live responses contain only counts and percentages —
  empirically validating this RFC's aggregate-only, no-client-identity,
  no-domain-detail design, not merely asserting it. The research
  document also names the real, readily-available endpoints
  (`recent_blocked`, `top_clients`, `top_domains`) that would leak
  exactly what this RFC excludes, as evidence the exclusion is
  deliberate.
- The observed error taxonomy (`unauthorized`, `rate_limiting`,
  `api_seats_exceeded`, `bad_request`, uniformly shaped as
  `{"error": {"key", "message", "hint"}, "took"}`) maps directly onto
  RFC-0003's bounded-execution failure classification.

All of this RFC's previously-open "must still confirm" items are now
resolved by that research document; none remain blocking.

## Interfaces and Data Flow

```text
Model proposes pihole.summary({"period": "today"})   [RFC-0004 flow]
    -> RFC-0003 executor: resolve, validate arguments against the
       enumerated {"today","last_24h"} schema, check policy
       (automatic confirmation; read_only + local)
    -> pihole.summary implementation:
        authenticate to Pi-hole's real API using the stored,
        capability-scoped credential (never exposed upstream)
        -> aggregate counts only, shaped to the declared result_schema
    -> result appended to model context, structured, per RFC-0004
```

No path in this flow allows a per-domain or per-client field to reach
the result — the schema itself is the enforcement point, not a
convention the implementation is trusted to honor unchecked.

## Security and Privacy

- This is the most privacy-sensitive capability surface in the
  milestone: DNS query behavior across a household is close to browsing
  history. The aggregate-only boundary is deliberately stricter than
  what Pi-hole's own admin API can technically return, not merely as
  strict as it.
- The credential-scoping requirement (capability-only access, never
  exposed to the model/Conversation Service) means even a fully
  successful prompt-injection attack against the model — per RFC-0004's
  untrusted-forever boundary, which already prevents this from executing
  anything unauthorized — could not additionally exfiltrate the Pi-hole
  credential itself, because nothing in the conversation path ever holds
  it.
- `blocking_enabled: null` (rather than a guessed default) when Pi-hole
  is unreachable avoids the specific failure mode of a capability
  fabricating a plausible-looking but false answer about the household's
  protection state.

## Failure and Recovery

- Pi-hole unreachable: `pihole.status` returns `reachable: false,
  blocking_enabled: null` rather than failing the whole invocation —
  "Pi-hole is down" is itself a valid, useful answer, not an error state
  requiring the executor to reject the proposal.
- Pi-hole reachable but the authenticated API call fails (auth failure,
  unexpected response shape): the capability implementation fails the
  invocation through RFC-0003's normal bounded-execution failure path,
  audited like any other capability failure — it does not fall back to
  guessing or to `console-health`'s coarser TCP-only signal, which would
  blur two capabilities with different privacy postures together.
- A response containing fields this RFC excludes is a capability
  implementation bug, not a runtime policy decision — the fix is
  correcting the implementation to match its declared `result_schema`,
  not adding a filter that could itself be forgotten or bypassed later.

## Compatibility and Migration

No existing capability to migrate from. This RFC's only compatibility
obligation is to the pinned Pi-hole version
(`pihole/pihole:2026.04.1`, per `image-builder/sovereign/pihole-image.env`)
and to `console-health`, which this RFC does not modify, replace, or
depend on — both integrations may coexist indefinitely with genuinely
different scopes.

## Operations and Observability

- `pihole.status`/`pihole.summary` invocations are audited exactly like
  any other capability per RFC-0003 — classification and outcome, never
  the household's actual query counts, in the durable log.
- If Pi-hole's real API proves unreliable enough to affect capability
  availability in practice, that shows up as a normal failure rate in
  the existing audit log, not a separate monitoring surface this RFC
  needs to invent.

## Testing Strategy

- Contract-level tests against RFC-0003's registered schema: argument
  validation rejects any `period` value outside the enumerated set, and
  result validation rejects any field the schema doesn't declare (a
  direct test that the privacy boundary is structurally enforced, not
  just documented).
- Fixture-backed tests for both capabilities' happy path and the
  Pi-hole-unreachable path, without requiring live Pi-hole for every
  test run.
- Once `pihole-api-assessment.md`'s empirical questions are answered
  against the real device, integration tests against the real, pinned
  Pi-hole version, followed by real-hardware qualification per this
  project's standing practice of a dated report under `docs/research/`.
- A specific adversarial test: request a result field outside the
  declared schema (simulating either an implementation bug or a
  malicious/compromised Pi-hole response) and confirm it is stripped or
  the invocation fails closed, never silently forwarded.

## Alternatives Considered

- **Reuse `console-health`'s TCP-only check for `pihole.status` and stop
  there, deferring `pihole.summary` entirely.** Considered, but rejected
  as incomplete: the milestone plan names "summary" capabilities
  explicitly, and the Exit Criteria requires "at least three Pi-hole/
  system questions invoke the correct read-only capability reliably" —
  a single up/down check does not support three distinct real questions.
- **Expose per-client query counts (not identities, just counts per
  device) as a middle ground.** Rejected for this pass: even anonymized
  per-client counts can identify a specific household member's device
  by behavior pattern in a small household, which is exactly the kind
  of re-identification risk aggregate-only avoids. Revisit only as its
  own explicit, separately-reviewed decision if a real use case demands
  it — not as a default expansion of this RFC's scope.
- **Let the model construct arbitrary Pi-hole API queries directly**
  (a generic "call this Pi-hole endpoint" capability). Rejected outright:
  this would bypass RFC-0003's typed schema validation entirely and
  reintroduce exactly the "arbitrary service access" RFC-0002's Safety
  Boundary already forbids.

## Drawbacks and Maintenance Cost

- Aggregate-only scoping means some genuinely useful household questions
  ("what got blocked on the kids' tablet just now") are not answerable
  through this capability surface at all. This is an accepted,
  deliberate privacy tradeoff, not an oversight — see Alternatives
  Considered.
- A second, capability-scoped Pi-hole credential (if the pinned version
  supports one) is an additional secret to provision, rotate, and
  include in the persistent-data backup/restore contract — real,
  ongoing operational surface area beyond `console-health`'s
  credential-free TCP check.

## Unresolved Questions

Endpoint shapes, credential availability, and error/rate-limit behavior
— this RFC's original open questions — are now resolved by
[docs/research/pihole-api-assessment.md](../research/pihole-api-assessment.md)
(Concluded 2026-08-09) and incorporated above. What remains is purely
implementation-level:

- Exact `checked_at` timestamp precision/timezone handling.
- Exact `webserver.api.max_sessions` default and whether it needs
  raising for Sovereign's own long-lived session to coexist with normal
  household web-UI use (named as an operational tuning question in the
  research document, not measured there).
- Precise rate-limit thresholds (attempts per window) — documented as
  existing, not independently measured, to avoid locking out the real
  device's admin access during research.

## Acceptance Criteria

- `pihole.status` and `pihole.summary` are registered against RFC-0003's
  contract with the schemas above, classified `read_only`/`local`/
  `automatic`.
- Result schema validation structurally rejects any field beyond what
  this RFC declares, verified by an adversarial test that attempts to
  return an excluded field (a client identity, a domain, a query
  timestamp) and confirms it never reaches the model or conversation
  context.
- The Pi-hole credential these capabilities use is stored under
  `/data/sovereign/secrets`, is unreachable from the Conversation
  Service/model/Inference Provider Adapter, and is never present in any
  audit event.
- `pihole-api-assessment.md`'s empirical questions (endpoint shape,
  credential scoping, rate-limit behavior) are answered against the real
  pinned Pi-hole version — done, see that document, Concluded
  2026-08-09 — not merely assumed from general Pi-hole documentation.
- `pihole.summary`'s implementation genuinely composes both confirmed
  endpoints (`database/summary` for period-scoped counts,
  `summary` for blocklist size and active-client count), not a single
  call this RFC originally assumed.
- `pihole.status` correctly reports `blocking_enabled: null` (not a
  guessed default) when Pi-hole is unreachable, verified against a real
  stopped/unreachable Pi-hole on real hardware.
- The milestone's Exit Criteria bar — at least three Pi-hole/system
  questions reliably invoking the correct read-only capability against a
  versioned evaluation corpus — is met using `system.health` (RFC-0002),
  `pihole.status`, and `pihole.summary` together.

## Decision

**Accepted (2026-08-09, project creator).** `pihole.status` and
`pihole.summary`, their schemas, aggregate-only privacy boundary, and
credential-handling requirements, are accepted, incorporating the
real, live-verified findings from
[docs/research/pihole-api-assessment.md](../research/pihole-api-assessment.md).
