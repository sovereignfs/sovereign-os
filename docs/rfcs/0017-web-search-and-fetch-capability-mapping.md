# RFC-0017: `web.search` and `web.fetch` Capability Mapping

**Status:** Draft
**Author:** Project creator and Claude
**Created:** 2026-08-21
**Reviewers:** Project creator
**Target phase:** [Milestone 01.2, Local Conversation and Capabilities](../roadmap/01-2-local-conversation-capabilities.md)
**Supersedes:** None

## Summary

Register `web.search` and `web.fetch` against [RFC-0003](0003-capability-contract.md)'s
contract, backed by a locally deployed SearXNG instance per
[docs/research/searxng-deployment-assessment.md](../research/searxng-deployment-assessment.md).
Both capabilities are `read_only`/`external`, which RFC-0003's structural
table already fixes as `confirmation: required` — the part this RFC adds
that RFC-0006 didn't need is a concrete design for the confirmation
pause/resume flow RFC-0004 specified architecturally but left as
"implementation, not architecture," and for the opt-in policy state
(`external_enabled`) the executor already gates on but nothing currently
sets. `web.search`/`web.fetch` are also the first capabilities that
genuinely send household-originated content outside the device, so this
RFC additionally fixes the SSRF-safe fetch policy the milestone plan names
("restricted by URL and content safety policy") but never specified.

## Problem

[ADR-0004](../adrs/0004-provider-neutral-assistant-and-web-search.md)
decided SearXNG is the initial `web.search` provider and named "document
SearXNG deployment, upstream configuration, retention, and failure
behavior" as open follow-up.
[searxng-deployment-assessment.md](../research/searxng-deployment-assessment.md)
closed the deployment half of that gap. What remains is the capability
mapping itself — the same relationship
[pihole-api-assessment.md](../research/pihole-api-assessment.md) had to
[RFC-0006](0006-pihole-capability-mapping.md).

Three concrete gaps block `web.search`/`web.fetch` from being usable, all
visible directly in the running code today, not hypothetical:

1. **Not registered.** `sovereign_conversation.py`'s `build_registry()`
   says so explicitly in its own comment: *"web.search/web.fetch are not
   registered here; they don't exist yet (blocked on the SearXNG
   deployment decision)."*
2. **No confirmation flow.** Even once registered, `read_only`+`external`
   is `confirmation: required` per RFC-0003's table. The executor-level
   primitives for this already exist and are unit-tested —
   `sovereign_capabilities.ConfirmationStore.issue()`/`.consume()`, and
   `invoke(..., confirmation_token=...)` (see `tests/test_capabilities.py`,
   `ConfirmationTokenTests`) — but the Conversation Service layer above
   them does not use them. Its own comment says so: *"Confirmation-required
   capabilities are detected and refused with a clear error, not silently
   executed and not given a working pause-and-resume flow across
   requests... this path is exercised by nothing real yet, but must still
   fail loudly rather than pretend to support it."* RFC-0004 fixed the
   architecture of this flow (§ Confirmation Flow) but explicitly deferred
   "how a denied/expired confirmation is presented to the user
   specifically" as a UI design question for whichever capability needs it
   first — that's this RFC.
3. **No policy state.** The executor already gates `external`-classified
   capabilities on `policy.get("external_enabled", False)`
   (`sovereign_capabilities.invoke`, stage 3) — but
   `bin/sovereign-conversation`'s `_handle_message` never passes a `policy`
   argument to `process_turn()` at all, so it silently defaults to `{}`,
   which means `external_enabled` is always `False` today. There is no
   persisted policy state anywhere for this to read even if it were wired
   up. Registering `web.search`/`web.fetch` without fixing this would ship
   two capabilities the executor can never actually run.

Without this RFC, an implementer would have to invent the confirmation
wire format and the SSRF-safe fetch policy ad hoc — exactly the kind of
consequential, safety-relevant decision this project's RFC process exists
to make deliberately rather than by omission (the same rationale RFC-0006
gave for the Pi-hole privacy boundary).

## Goals

- Register `web.search` and `web.fetch` against RFC-0003's contract:
  schemas, classification (already fixed:
  `read_only`/`external`/`required`), and bounds.
- Design the confirmation pause/resume wire format `bin/sovereign-conversation`
  needs to actually surface a pending `required`-confirmation decision to
  the client and accept an approval/denial back, on top of the
  already-implemented `ConfirmationStore` primitives.
- Fix where the `external_enabled` opt-in policy flag is persisted, its
  safe default, and how `process_turn()` reads it.
- Fix the SSRF-safe URL-fetch policy `web.fetch` must enforce, since it is
  the first capability that lets a model-proposed argument influence what
  the device's own network stack contacts.
- Fix the SearXNG-backed implementation specifics research left open:
  `settings.yml`'s `image_proxy` decision, and upstream engine selection.

## Non-Goals

- Re-deciding that SearXNG is the provider — closed by ADR-0004.
- Re-deriving the confirmation *architecture* (proposal surfaced as a
  pending decision, single-use time-bounded token, model never sees the
  token, denial is a normal audited outcome) — fixed by RFC-0004. This RFC
  only fixes the parts RFC-0004 named as implementation-level and left
  open.
- The Console UI's actual approve/deny prompt and the settings toggle
  that sets `external_enabled` — this RFC fixes the API contract and
  storage location both depend on, the same way RFC-0006 fixed Pi-hole's
  API contract without itself building Console UI. Building those is
  necessary follow-up implementation work, named in Acceptance Criteria,
  not built here.
- Measuring real resource footprint on this project's actual Raspberry
  Pi 5 device under real concurrent load, and hardware-qualifying any of
  this — still open per
  [searxng-deployment-assessment.md](../research/searxng-deployment-assessment.md)'s
  Addendum, unchanged by this RFC. (The real ARM64 image digest itself
  has since been pinned and embedded — see
  `image-builder/sovereign/searxng-image.env` — but that's image-builder
  work this RFC's capability mapping doesn't depend on being reviewed
  first.)
- General web crawling, recursive link-following, or fetching more than
  one page per `web.fetch` invocation — explicit milestone non-scope
  ("no generic network tool").
- Any capability beyond `web.search`/`web.fetch` — Home Assistant's future
  capabilities (Milestone 5) will reuse this RFC's confirmation wire
  format once they exist, but are not designed here.

## Context and Evidence

- [ADR-0004](../adrs/0004-provider-neutral-assistant-and-web-search.md)
  (Accepted): SearXNG is the initial `web.search` provider; `web.search`
  and `web.fetch` are separate capabilities; the model receives no
  generic network tool; search is explicitly enabled/approved and
  visibly communicates the query and external boundary.
- [RFC-0002](0002-local-conversation-and-inference-runtime.md) (Accepted)
  named "the `web.search`/`web.fetch` privacy design in full detail" as a
  Non-Goal, "tracked separately" — this RFC is that separate document.
- [RFC-0003](0003-capability-contract.md) (Accepted): both capabilities
  are already classified in its own Initial Capability Classification
  table — `read_only`/`external`/`required` for both — and its
  Confirmation Model table derives that classification structurally, not
  as a per-capability choice this RFC can revisit.
- [RFC-0004](0004-ai-capability-invocation.md) (Accepted): fixes the
  confirmation flow's architecture (§ Confirmation Flow) and the
  untrusted-forever boundary on capability results, and explicitly defers
  "exact confirmation-token format and expiry duration" and "how a
  denied/expired confirmation is presented to the user specifically" as
  implementation-level, to be fixed by whichever capability needs them
  first.
- `image-builder/sovereign/appliance/lib/sovereign_capabilities.py`,
  read directly: `ConfirmationStore` (token issue/consume, single-use,
  time-bounded via `DEFAULT_CONFIRMATION_TTL_SECONDS = 120`), and
  `invoke()`'s stage-3 policy gate (`policy.get("external_enabled",
  False)`) and stage-4 confirmation gate — both already implemented and
  covered by `tests/test_capabilities.py`'s `ConfirmationTokenTests` and
  `test_external_capability_rejected_when_policy_disabled`/
  `test_required_confirmation_rejected_without_token`.
- `image-builder/sovereign/appliance/lib/sovereign_conversation.py` and
  `image-builder/sovereign/appliance/bin/sovereign-conversation`, read
  directly: confirm, in their own comments and code, all three gaps this
  RFC closes (not registered; confirmation refused outright; no `policy`
  argument ever passed).
- [docs/research/searxng-deployment-assessment.md](../research/searxng-deployment-assessment.md)
  (Concluded, desk research, later live-verified in its own Addendum):
  image (`ghcr.io/searxng/searxng`), local port (`8093`, avoiding the
  collision with Pi-hole's existing `8080`), required `settings.yml`
  overrides (`formats: [html, json]`, `autocomplete: ""`, `limiter:
  false` confirmed correct), the `SEARXNG_SECRET` environment-variable
  mechanism (confirmed real and required — no `_FILE` convention exists),
  and the JSON search API's request shape
  (`q`/`categories`/`language`/`pageno`/`time_range`/`safesearch`) and
  real response shape (confirmed live: `results[]` entries carry
  `title`/`url`/`content` among other fields this RFC's schema doesn't
  surface). This RFC still decides `image_proxy` itself (see Proposal).
- [docs/roadmap/01-2-local-conversation-capabilities.md](../roadmap/01-2-local-conversation-capabilities.md)
  §6 (Web Search and Privacy): "search only when the user requests it or
  the user approves a proposed search," "show the exact query before or
  while it is sent," "do not silently mix private household context into
  search queries," "strip capability secrets and unnecessary
  identifiers," "return source URLs and distinguish fetched evidence from
  model knowledge," "support disabling web search entirely." §4 names
  `web.fetch` as "restricted by URL and content safety policy" without
  specifying what that policy is — this RFC's job.

## Proposal

### `web.search`

- **Purpose:** answer questions the model cannot answer from its own
  training or from a registered local capability, by querying the
  self-hosted SearXNG instance.
- **Arguments:** `{ "query": string (required, 1-500 chars),
  "time_range": "day" | "month" | "year" (optional) }`. No `categories` or
  `safesearch` argument in this first pass — SearXNG's own defaults for
  both are acceptable for a general-purpose assistant, and RFC-0003's
  "bounded, enumerated argument set" precedent (RFC-0006's `period`
  argument) favors the smallest schema that answers the milestone's real
  questions over speculative flexibility. `time_range` is optional because
  most questions ("what's the weather saying," "who won") aren't
  time-scoped explicitly.
- **Result:** `{ "query": string, "results": [ { "title": string, "url":
  string, "snippet": string } ], "result_count": int, "retrieved_at":
  timestamp }`. At most 5 results, no pagination argument — the same
  "summary endpoint by design, not an export" bound RFC-0006 applied to
  `pihole.summary`. `query` is echoed back in the result (not just the
  argument) so the structured citation object the client renders is
  self-contained per RFC-0004's "distinguished from generated prose"
  requirement, without the client needing to correlate it back to the
  original proposal's arguments.
- **Classification:** `read_only`, `external` (fixed by RFC-0003),
  `required` confirmation (derived, not chosen).
- **Bounds:** `timeout_seconds=10` (SearXNG runs locally; a slow response
  indicates an unresponsive upstream engine, not normal latency),
  `max_result_bytes` left at `DEFAULT_MAX_RESULT_BYTES` (64KiB — five
  short results comfortably fit), `max_invocations_per_turn=1` — matching
  every other registered capability's default rather than special-casing
  search to allow rapid-fire repeated queries in one turn.

### `web.fetch`

- **Purpose:** retrieve the actual content of a specific URL — typically
  one `web.search` just returned, but not restricted to only those (a
  user may paste a URL directly and ask about it; RFC-0004's
  untrusted-forever boundary already governs what happens to fetched
  content regardless of how the URL was obtained, so provenance-based
  restriction would add complexity without closing a real gap the SSRF
  policy below doesn't already close).
- **Arguments:** `{ "url": string (required, http/https only) }`.
- **Result:** `{ "url": string, "final_url": string, "content_type":
  string, "text": string, "truncated": bool, "redirected": bool,
  "retrieved_at": timestamp }`. (Implementation note: `redirected` was
  added during implementation — this bullet originally omitted it while
  the SSRF-Safe Fetch Policy section below already described the flag in
  prose; the two are now consistent.) `text` is plain-text extracted
  content — built on the standard library's `html.parser.HTMLParser`
  (tags, `<script>`, and `<style>` content excluded), not a third-party
  HTML/rendering dependency — truncated at `max_result_bytes` if the page
  is larger, with `truncated: true` set rather than silently dropping the
  tail. `final_url` equals `url` for an ordinary fetch; on a redirect
  response it instead holds the redirect's `Location` target, and
  `redirected` is `true` — no redirect is ever followed automatically
  (see SSRF-Safe Fetch Policy below), so `final_url` never reflects a
  same-origin hop that was silently taken.
- **Classification:** `read_only`, `external`, `required` confirmation.
- **Bounds:** `timeout_seconds=15` (a real external server's own latency,
  not this device's — longer than `web.search`'s local-instance budget is
  deliberate, not an oversight), `max_result_bytes` left at
  `DEFAULT_MAX_RESULT_BYTES`, `max_invocations_per_turn=1`.

### SSRF-Safe Fetch Policy

`web.fetch` is the first capability where a model-supplied argument
influences what the device's own network stack contacts, which is a
different risk class than the untrusted-content boundary RFC-0004 already
covers (that boundary governs what fetched *content* is allowed to do;
this policy governs what fetching is allowed to *reach*). The
implementation must, before making any request:

1. **Scheme allowlist.** Reject anything but `http://`/`https://`
   outright — no `file://`, `ftp://`, `gopher://`, or any scheme that
   could reach local files or unexpected protocols.
2. **Resolve before connecting, and check the resolved address, not the
   literal hostname.** A hostname that *looks* external can still resolve
   to an internal address (DNS rebinding), so the check must happen
   against the actual IP the connection is about to use, immediately
   before connecting — not a one-time hostname-string check earlier in
   the pipeline that a second, later DNS lookup could bypass.
3. **Reject private, loopback, link-local, and multicast destination
   addresses** — RFC1918 (`10.0.0.0/8`, `172.16.0.0/12`,
   `192.168.0.0/16`), loopback (`127.0.0.0/8`, `::1`), link-local
   (`169.254.0.0/16`, `fe80::/10`), and multicast/reserved ranges. This is
   the concrete, real-stakes reason the check matters on this specific
   device: `127.0.0.1` on this appliance is Pi-hole's admin API (`8080`),
   console-auth (`8091`), the Conversation Service itself (`8092`), and
   llama-server (`8081`) — a `web.fetch` proposal targeting any of them
   would be a real internal-service-reconnaissance vector, not a
   theoretical one, and the household LAN behind it hosts real devices
   (routers, other appliances) an external-facing capability must never be
   able to reach.
4. **No automatic redirect-following.** If the response is a redirect,
   `web.fetch` returns that fact (`final_url` set to the redirect target,
   `text` empty, a `redirected: true` flag) rather than silently following
   it — blind redirect-following is a well-known SSRF bypass (a public
   URL redirecting to an internal one after the first check already
   passed). A model that wants the redirect target fetches it as an
   explicit second `web.fetch` proposal, which the confirmation flow below
   surfaces and the SSRF checks re-apply to independently.
5. **Content-type allowlist.** Only `text/html`, `text/plain`, and
   `application/json` are extracted; anything else (binary, executable,
   archive) is rejected before the body is read, not merely not rendered.
6. **Size cap enforced while streaming**, not after a full download — a
   multi-gigabyte response must not be fully retrieved before its size is
   checked.

This is deliberately stricter than "restricted by URL," the milestone
plan's own phrasing — it is restricted by *resolved destination and
response shape*, which is the only version of that restriction that
actually holds against DNS rebinding and redirect-based bypasses.

### Confirmation Pause/Resume Wire Format

`ConfirmationStore.issue()`/`.consume()` and `invoke(...,
confirmation_token=...)` already implement RFC-0004's confirmation
*mechanics*. What's missing is the request/response shape that lets a
client actually drive that mechanism across two HTTP requests. This RFC
fixes it:

- When `process_turn()` encounters a `required`-confirmation proposal that
  has passed RFC-0003's resolve/validate/policy stages, it no longer
  raises `confirmation_unsupported`. Instead it calls
  `confirmation_store.issue(name, version, arguments)` and **halts that
  round without executing**, returning a `pending_confirmation` object
  instead of continuing to propose/execute further in the same turn:
  `{ "token": string, "capability": string, "version": int, "arguments":
  object, "expires_in_seconds": int }`. `arguments` is included verbatim
  and unredacted — RFC-0004 requires the exact external-bound content
  (the literal search query, the literal URL) to be disclosed before
  approval, and the milestone plan's "show the exact query" requirement
  is not satisfied by a summary or a capability name alone.
- `POST /api/v1/conversation/message`'s response gains an optional
  top-level `pending_confirmation` field (absent/`null` on every turn that
  didn't hit this path — no shape change for `system.health`/Pi-hole
  turns). When present, `text` describes the situation in prose (e.g., the
  model's own turn narrating that it wants to search) and the client is
  responsible for prompting the user with the disclosed capability and
  arguments, not inferring intent from prose alone.
- `POST /api/v1/conversation/message`'s request gains an optional
  `confirmation` field: `{ "token": string, "approve": bool }`. When
  present, the server does not start a new turn; it resolves the specific
  pending proposal the token identifies:
  - `approve: true` → `invoke()` is called with that `confirmation_token`,
    consuming it (single-use, enforced by `ConfirmationStore.consume()`
    already). Success appends the result to context and the turn
    continues (further rounds, up to the existing per-turn budget) exactly
    as an `automatic`-confirmation capability's result would.
  - `approve: false`, or the token has expired
    (`DEFAULT_CONFIRMATION_TTL_SECONDS = 120`, unchanged — a concrete
    number already implemented and tested, not re-litigated here) → the
    proposal is recorded as a denial, appended to context as such per
    RFC-0004 (not a generic failure), and the turn continues without
    retrying it.
  - A `confirmation.token` that doesn't match any currently-pending entry
    (wrong token, already consumed, from a different conversation) is
    rejected with `400 INVALID_CONFIRMATION` — the same "never trust the
    caller's own framing" posture RFC-0003's schema validation already
    applies elsewhere.
- The model itself never sees the token — it is minted by the executor
  and returned only in the HTTP response the Console client reads,
  exactly matching RFC-0004's "the model never receives, generates, or
  influences the confirmation token."
- `ConfirmationStore` remains in-memory, per-process (unchanged from
  today) — a token issued by one `sovereign-conversation` process
  restart-cycle does not survive it, which is an acceptable, disclosed
  limitation matching the Conversation Service's own existing statelessness
  (RFC-0002: "no conversation storage... nothing is persisted here").

### Policy State

- A new persisted file, `/data/sovereign/capabilities/policy.json`, holds
  `{ "web_search_enabled": bool }`. (Implementation correction: this
  section originally proposed a top-level `/data/sovereign/policy.json`
  sibling. Before implementing, checking this project's own precedent —
  no `tmpfiles.d` usage anywhere in this repo; every `ReadWritePaths=`
  target is either pre-created by a root-run script like `proof-init`, or
  lazily created by the owning `DynamicUser` process itself — showed a
  new top-level file would need either a new `ReadWritePaths=` grant on
  an unverified not-yet-existing path, or a new root-run bootstrap step,
  exactly the class of gap that caused a real hardware-caught outage
  before, per the console-check-trigger qualification report's missing-
  grant bug. `capabilities/` is already granted to
  `sovereign-conversation.service` and already gets lazily created the
  same way by `append_audit_event()`; `policy.json` reuses that exact,
  already-shipped mechanism instead of inventing a second one.)
- **Default: `false`.** Matching the milestone plan's own policy ("Web
  search is disabled by default or explicitly enabled during
  onboarding") and RFC-0003's general confirmation-model conservatism —
  an appliance that has never been configured must not silently start
  making external requests.
- `bin/sovereign-conversation` reads this file at the start of each
  `_handle_message` call (not cached at process start, so a change takes
  effect on the next message without a service restart — the same
  freshness expectation `sovereign-update check`'s own on-demand reads
  already establish elsewhere in this project) and passes
  `policy={"external_enabled": web_search_enabled}` into `process_turn()`,
  closing the gap where `policy` is never passed today.
- Writing this file: `GET`/`POST /api/v1/conversation/policy`, authenticated
  the same way `/message` is (delegating to console-auth's
  `verify-mutating`), reusing this project's atomic-write convention
  (`.tmp` file, then rename) already established for
  `sovereign-pihole-password` and other per-device secrets. Console's
  Chat page renders this as a labeled toggle, loaded on sign-in and
  written on change — see Acceptance Criteria.

### SearXNG Configuration Decisions

Resolving the two items
[searxng-deployment-assessment.md](../research/searxng-deployment-assessment.md)
left open:

- **`image_proxy: false` (off).** `web.fetch`'s result schema returns
  extracted text, not embedded images — nothing in this RFC's two
  capabilities renders an image inline, so proxying image bytes through
  SearXNG would add real request/bandwidth load for a capability that
  can't use the result. Revisit only if a future capability actually
  needs to reference image content.
- **Upstream engine selection: keep SearXNG's own shipped defaults**,
  rather than hand-curating a smaller engine list. No evidence gathered so
  far (this RFC's research or otherwise) identifies a specific engine as
  unreliable or objectionable for this use case, and curating a list
  without that evidence would be speculative narrowing, not a grounded
  decision. Revisit if real usage surfaces a specific problem engine.

## Interfaces and Data Flow

```text
Model proposes web.search({"query": "..."})           [RFC-0004 flow]
    -> RFC-0003 executor stages 1-3: resolve, validate arguments,
       check policy (external_enabled must be true, read fresh from
       /data/sovereign/capabilities/policy.json each request)
    -> stage 3 fails (policy off) -> rejection appended to context,
       model can tell the user web search is disabled
    -> stage 3 passes, confirmation required (structural, both
       capabilities) -> confirmation_store.issue() -> round halts,
       pending_confirmation returned in the HTTP response instead of
       a normal result
    -> Console prompts: "web.search wants to search for '<query>' —
       this leaves your device. Approve?"
    -> user approves -> client resubmits POST /message with
       {"confirmation": {"token": "...", "approve": true}}
    -> confirmation_store.consume() (single-use) -> invoke() proceeds
       through stages 5-6: SearXNG queried over the local, loopback-only
       instance (port 8093) -> result shaped to web.search's declared
       result_schema -> appended to context as a structured citation
    -> turn continues (model may narrate, propose again within budget,
       or respond with prose)

    -> OR user denies / token expires -> denial appended to context,
       turn continues without a search result
```

`web.fetch`'s flow is identical except stage 5 additionally runs the
SSRF-safe fetch policy (resolve, check destination, no redirect-follow,
content-type/size checks) before returning a result.

## Security and Privacy

- **Every** `web.search`/`web.fetch` invocation requires per-invocation
  user confirmation — there is no automatic path for either capability,
  structurally, per RFC-0003's table. A successful prompt injection can
  cause a proposal, never an execution, matching RFC-0004's own framing.
- The exact query/URL is disclosed to the user before approval, not
  summarized or hidden behind a capability name — the milestone plan's
  disclosure requirement is enforced by the `pending_confirmation`
  object's `arguments` field being the literal proposed arguments, not a
  paraphrase the Conversation Service could get wrong.
- The `external_enabled` policy check happens fresh, per request, from
  persisted state — a household that has never opted in gets a structural
  rejection at stage 3, before a confirmation prompt is even generated,
  so "disabled" genuinely means no external contact is possible, not just
  "no default." This directly satisfies the milestone plan's "support
  disabling web search entirely."
- The SSRF-safe fetch policy (resolve-then-check, no redirect-following,
  content-type/size limits) is the concrete mechanism behind the milestone
  plan's otherwise-unspecified "restricted by URL and content safety
  policy," closing a real internal-network-reconnaissance vector this
  specific device's own port layout (Pi-hole, console-auth, the
  Conversation Service itself, llama-server, all on loopback) makes
  concretely dangerous, not abstractly.
- Capability secrets: neither capability handles a credential (unlike
  Pi-hole's admin password) — SearXNG's local instance requires no
  authentication from Sovereign's side, so there is no credential-scoping
  requirement analogous to RFC-0006's.
- Audit events for both capabilities follow RFC-0003 unchanged: the fact
  of invocation, classification, and outcome, never the query text or
  fetched content — household search/browsing intent is at least as
  sensitive as the DNS query behavior RFC-0006 already refused to log.

## Failure and Recovery

- SearXNG unreachable: `web.search` fails through RFC-0003's normal
  bounded-execution failure path (a timeout or connection error), audited
  like any other capability failure, surfaced to the model as a failure
  it can narrate ("I couldn't reach web search right now") — not a
  fabricated empty-results answer.
- A `web.fetch` target that fails SSRF validation is rejected before any
  connection is attempted, with a specific error code
  (`FETCH_TARGET_REJECTED`) distinct from a genuine network failure, so
  the audit trail and any future debugging can tell "we refused to try"
  apart from "we tried and failed."
- A confirmation token that expires while genuinely pending (user hasn't
  answered) requires the proposal to be re-surfaced from scratch on the
  next message — per RFC-0004, this is not a system failure, only the
  token's deliberately short lifetime elapsing.
- A `sovereign-conversation` process restart while a confirmation is
  pending invalidates that token (in-memory `ConfirmationStore`) — the
  client's next attempt to approve it hits `INVALID_CONFIRMATION` and must
  ask the model to propose again. Disclosed limitation, not silently
  swallowed.

## Compatibility and Migration

No existing `web.search`/`web.fetch` capability to migrate from. The
`pending_confirmation`/`confirmation` request-response fields are
additive to `POST /api/v1/conversation/message`'s existing shape — every
turn that never hits a `required`-confirmation capability (every turn
today, since `system.health`/Pi-hole are all `automatic`) is unaffected,
verified by the existing `test_conversation_service.py` test suite
continuing to pass unmodified. The confirmation wire format this RFC
fixes is intentionally general (token/capability/version/arguments), not
`web.search`/`web.fetch`-specific, so Milestone 5's future mutating
Home Assistant capabilities reuse it rather than needing a second design.

## Operations and Observability

- Policy state (`/data/sovereign/capabilities/policy.json`) should be inspectable the
  same way update/trust-rotation state already is (per RFC-0003's own
  Operations section for the general policy-state precedent) — a future
  Console settings panel reads and writes it, not a separate config path.
- The capability audit log (RFC-0003, unchanged) is the operational
  record of how often `web.search`/`web.fetch` are proposed, approved,
  denied, or rejected by policy — useful for judging whether the
  confirmation flow is actually usable in practice (a denial/expiry rate
  that's too high might mean the UI is confusing, not that users don't
  want search) without needing a new monitoring surface.

## Testing Strategy

- Contract-level tests mirroring RFC-0006's pattern: argument validation
  rejects anything outside `web.search`'s schema (empty query, query over
  500 chars, an invalid `time_range` value) and `web.fetch`'s schema
  (non-http(s) scheme rejected before the SSRF check even runs).
- SSRF policy tests, adversarial by design: a `web.fetch` proposal
  targeting `127.0.0.1` (any of this device's own real loopback ports), a
  private RFC1918 address, a link-local address, and a hostname that
  resolves to one of those (simulating rebinding) must all be rejected by
  `FETCH_TARGET_REJECTED` before any connection attempt — verified by
  mocking DNS resolution to return an internal address for an
  otherwise-innocuous-looking hostname, the direct test that the resolved-
  address check actually runs, not just a literal-string hostname
  denylist.
- A redirect test: a mocked upstream response that redirects confirms
  `web.fetch` reports it (`redirected: true`, `final_url` set) rather than
  following it automatically.
- Confirmation wire-format tests at the HTTP layer, extending
  `test_conversation_service.py`'s existing pattern: a `required`-
  confirmation proposal produces a `pending_confirmation` object and no
  executed result; a correct `confirmation.token`/`approve: true`
  resubmission executes exactly once (token single-use, verified by a
  second resubmission with the same token failing); `approve: false`
  produces a denial appended to context; an unknown/expired/already-used
  token is rejected with `INVALID_CONFIRMATION`.
- Policy-gate tests: `external_enabled: false` (the real default) rejects
  both capabilities at stage 3 before any confirmation is even generated;
  `external_enabled: true` allows the flow to proceed to the confirmation
  stage.
- Fixture-backed tests for `web.search`/`web.fetch`'s SearXNG-calling
  happy path, without requiring a live SearXNG instance for every test
  run — mirroring RFC-0006's own testing strategy for Pi-hole.
- Once a real SearXNG instance is deployed (image-builder work, not this
  RFC), integration tests against it, followed by real-hardware
  qualification per this project's standing practice of a dated report
  under `docs/research/`.

## Alternatives Considered

- **Restrict `web.fetch` to only URLs a prior `web.search` call in the
  same turn returned**, rather than any model-proposed URL passing SSRF
  validation. Considered, but rejected: it would block a legitimate case
  (a user pastes a URL and asks about it) without closing a real gap the
  SSRF policy doesn't already close — the actual risk (reaching an
  internal service) is about destination, not provenance.
- **Auto-approve `web.search` after the first explicit per-conversation
  opt-in**, rather than per-invocation confirmation. Rejected: RFC-0003's
  confirmation model already fixed "freshly-obtained... never a standing
  blanket approval" as structural, not a per-capability choice, and
  loosening it would be a contract change to RFC-0003 itself, out of this
  RFC's scope (RFC-0003 §Drawbacks already names this exact tension as a
  possible future revisit, not decided here).
- **Follow redirects up to a small bounded depth, re-validating each hop**,
  instead of never following them. Considered as a real usability
  improvement (many URLs are one hop from `http` to `https`, or through a
  URL shortener), but rejected for this first pass: it's real additional
  implementation complexity (bounded-depth loop, re-validation per hop,
  distinguishing benign protocol-upgrade redirects from actual
  destination changes) for a capability that can already reach the
  intended content via an explicit second `web.fetch` proposal. Revisit if
  real usage shows single-hop redirects are common enough to be a genuine
  friction point.
- **Cache SearXNG results or `web.fetch` content locally** to reduce
  repeat external requests. Rejected: no retention policy exists for this
  data yet (RFC-0002 explicitly left conversation/capability data
  retention to a later data-inventory update), and caching household
  search/browsing content before that policy exists would be exactly the
  kind of privacy-relevant storage decision this project makes
  deliberately, not as a performance side-effect.

## Drawbacks and Maintenance Cost

- Every `web.search`/`web.fetch` call costs the user an extra round trip
  (propose → confirm → execute) compared to the milestone's other three
  capabilities, which all execute automatically. This is an accepted,
  structural consequence of RFC-0003's confirmation model, not a defect
  of this RFC's design — see Alternatives Considered on auto-approval.
- The confirmation wire format adds real, permanent surface area to
  `POST /api/v1/conversation/message`'s contract (two new optional
  fields, a new halting-round behavior) that every future client
  (Console today, anything else later) must handle correctly, not just
  the two capabilities that need it first.
- SSRF validation adds an implementation and maintenance burden beyond
  what the pihole/system capabilities needed — a resolve-then-check step,
  a private/loopback/link-local address table to keep current, and
  redirect-handling logic — real, ongoing surface area, justified by this
  being the first capability where a model-influenced argument reaches
  the device's own network stack.

## Unresolved Questions

None of the following block acceptance of the mapping and flows fixed
above:

- The exact plain-text extraction method for `web.fetch` (which tags to
  strip, how to handle `<script>`/`<style>` content, whitespace
  normalization) is implementation detail, not architecture.
- Whether `application/json` responses need any special handling beyond
  size/type checks (e.g., pretty-printing before truncation) — cosmetic,
  left to implementation.
- ~~The real JSON response schema from a live SearXNG instance~~ —
  resolved: a real live query against the exact pinned image (see
  [searxng-deployment-assessment.md](../research/searxng-deployment-assessment.md)'s
  Addendum) confirmed `results[]` entries carry `title`/`url`/`content`
  among many other fields this RFC's schema deliberately doesn't surface
  — `content` maps to this RFC's `snippet`. The mapping itself is
  implementation detail; the fields exist as assumed.
- Real upstream-engine blocking/CAPTCHA behavior from this device's
  residential IP, and what `web.search` should report to the model when
  an individual upstream engine fails but others in the same query
  succeed (partial results vs. treating any engine failure as a whole-
  capability failure) — needs real observation, not speculation.
- Whether `/data/sovereign/capabilities/policy.json` should hold other future opt-in
  toggles (a general device-policy file) or stay `web.search`-specific
  until a second policy flag actually exists — deferred until Milestone 5
  or another feature needs its own toggle.

## Acceptance Criteria

- `web.search` and `web.fetch` are registered against RFC-0003's contract
  with the schemas above, classified `read_only`/`external`/`required`
  (structural, unchanged from RFC-0003's own table).
- `bin/sovereign-conversation` reads `/data/sovereign/capabilities/policy.json` fresh
  per request and passes `external_enabled` into `process_turn()`,
  verified by a test that toggling the file's content between requests
  changes the outcome without a service restart.
- A `required`-confirmation proposal halts its round and returns a
  `pending_confirmation` object containing the literal, undisclosed-
  free proposed arguments — verified by a test asserting the exact query/
  URL text is present in the HTTP response, not merely a capability name.
- Approving a pending confirmation executes the capability exactly once;
  a second approval attempt with the same token fails with
  `INVALID_CONFIRMATION` — verified directly (this is the single-use
  guarantee `ConfirmationStore` already provides at the executor layer;
  this criterion confirms the HTTP layer doesn't accidentally bypass it,
  e.g. by calling `invoke()` twice for one approval).
- Denying a pending confirmation appends a denial (not a generic failure)
  to context and the turn continues without executing the capability.
- `web.fetch` rejects, before any network connection, a proposed URL
  whose resolved destination is loopback, RFC1918 private, or link-local
  — verified by the adversarial DNS-rebinding test in Testing Strategy,
  not just a literal-hostname denylist test.
- `web.fetch` does not automatically follow redirects — verified by a
  test asserting a redirect response is reported (`redirected: true`),
  not silently chased.
- `external_enabled: false` (the real default when
  `/data/sovereign/capabilities/policy.json` doesn't exist yet) rejects both
  capabilities at the policy stage, before any confirmation is generated
  — verified directly, confirming the milestone's "disabled by default"
  requirement is structurally true on a fresh device, not merely
  documented.
- Existing tests (`test_conversation_service.py`,
  `test_capabilities.py`) continue to pass unmodified, confirming this
  RFC's additions are additive to the existing turn loop and executor,
  not a breaking change to `system.health`/Pi-hole's already-working
  paths.
- The milestone's Exit Criteria bar for `web.search` specifically
  ("Web search is disabled by default or explicitly enabled during
  onboarding, clearly signals external communication, and returns
  inspectable citations") is satisfied by the policy default, the
  confirmation disclosure, and `web.search`'s structured `results` array
  respectively — each traceable to a specific Acceptance Criterion above,
  not asserted in the abstract.

Explicitly **not** required for acceptance (named as necessary follow-up
implementation, not blocking this RFC per this project's own precedent of
separating proposal from build-out):

- ~~The actual SearXNG image-builder embedding (`searxng-image.env`, a
  real pinned digest, the artifact/import/server systemd units).~~ Done,
  independent of this RFC's own review: `image-builder/sovereign/searxng-image.env`
  (real pinned digest) and `image-builder/sovereign/appliance/searxng/`
  (compose template, `settings.yml`, `start-searxng`/`stop-searxng`,
  three systemd units), unit-tested
  (`tests/test_searxng_deployment.py`).
- ~~The capability implementation itself.~~ Also done, independent of
  this RFC's own review, the same way the deployment above was:
  `sovereign_websearch.py` (both capabilities, the SSRF-safe fetch
  policy), the confirmation pause/resume wire format in
  `sovereign_conversation.py`/`bin/sovereign-conversation`
  (`PendingTurnStore`, `resume_turn()`, `pending_confirmation`/
  `confirmation` request-response fields), and `/data/sovereign/capabilities/policy.json`
  policy-state reading, all unit-tested
  (`tests/test_websearch_capabilities.py`, extended
  `tests/test_conversation.py`/`test_conversation_service.py`). This
  project's implementation-before-formal-acceptance precedent (e.g. the
  Conversation Service itself shipped against RFC-0002/0003/0004 before
  those RFCs' own Decision sections were filled in) applies here too —
  none of this is a substitute for project-owner review of the mapping
  and policy decisions this RFC actually proposes.
- ~~Console's approve/deny confirmation UI.~~ Also done, same
  precedent: a `.confirmation-card` in the Chat page (`console/index.html`,
  `console/assets/console.js`/`console.css`) discloses the literal
  capability name and arguments from `pending_confirmation`, with
  Deny/Approve controls that resume the turn via the `confirmation`
  request field, locking the composer while a decision is pending and
  clearing it on sign-out. Unit-tested
  (`tests/test_console.py`) and manually verified end-to-end (approve and
  deny) against a stub backend. A real, disclosed pre-existing UI bug was
  also found and fixed in the process: chat receipts previously always
  said "stayed local" regardless of classification — now accurate for
  `web.search`/`web.fetch`.
- ~~The settings toggle that writes `policy.json`.~~ Also done: `GET`/
  `POST /api/v1/conversation/policy` (authenticated like `/message`,
  atomic write via a `.tmp` file + rename), and a labeled switch on
  Console's Chat page (`#chat-policy-row`) that loads the real state on
  sign-in and persists a change immediately, reverting the visible toggle
  if the write fails. Unit-tested
  (`tests/test_conversation.py`, `test_conversation_service.py`,
  `test_console.py`, `test_console_auth.py`) and manually verified
  end-to-end (toggle on, confirm a search is offered; toggle off, confirm
  it's rejected before any confirmation prompt) against a stub backend.
  `web_search_enabled` still defaults to `false` on any device that has
  never touched this toggle — the fail-safe default this RFC always
  required, now genuinely reachable and changeable from Console rather
  than only by an operator editing the file directly.
- ~~Real-hardware qualification of any of the above.~~ Done: see the
  [web.search/confirmation flow hardware qualification report](../research/web-search-and-confirmation-flow-hardware-qualification-report.md).
  Real pinned digests pulled and run natively on the Raspberry Pi 5, real
  model + real inference, real SearXNG search, all five capabilities
  exercised through the real executor (including a real SSRF test
  against the device's own actual running services), a real confirmation
  round trip, and a real browser-authenticated pass driven by the
  project owner. Found and fixed one real bug in the process (the
  `web_search` policy toggle's `GET` request was missing its CSRF
  header, so it always failed against the real server — the `POST` path
  was unaffected). This was a manual smoke-test deployment on the
  project's standing qualification device (still `0.1.0-proof.3`, per
  the same precedent the llama-server deployment qualification already
  established), not a real signed release — the artifact/import systemd
  paths and the real `DynamicUser` sandbox for `sovereign-conversation.service`
  remain unexercised, named explicitly in that report's Limitations.

## Decision

Leave blank until review. Record approval, rejection, or requested
changes with date and owner.
