# RFC-0018: Home Assistant Read-Only Capability Mapping

**Status:** Accepted (2026-08-21, project creator)
**Author:** Project creator and Claude
**Created:** 2026-08-21
**Reviewers:** Project creator
**Target phase:** [Milestone 01.2, Local Conversation and Capabilities](../roadmap/01-2-local-conversation-capabilities.md) §11, Following Vertical Slice; [ROADMAP.md](../../ROADMAP.md) Milestone 5, Home Automation Integration
**Supersedes:** None

## Summary

Register two read-only Home Assistant capabilities —
`home_assistant.list_entities` and `home_assistant.get_history` — against
[RFC-0003](0003-capability-contract.md)'s contract, reusing
[RFC-0017](0017-web-search-and-fetch-capability-mapping.md)'s confirmation
pause/resume wire format unchanged. This is deliberately the roadmap's
"first slice" only (discover and read allowlisted entities, answer state
and history questions) — allowlisted mutating actions are explicit
Non-Goal, left to a future RFC once that slice is actually built, matching
this project's own precedent of splitting a read-only capability mapping
from mutation (RFC-0006 did the same for Pi-hole).

The one genuinely new design question this RFC has to resolve that
RFC-0006 and RFC-0017 didn't: Home Assistant is neither device-local
(Pi-hole's loopback container) nor public-internet (SearXNG's federated
search, an arbitrary fetched URL) — it is a separate, household-owned
device on the same LAN. RFC-0003's `network` axis only has `local`/
`external`, and this RFC does not attempt to add a third tier by fiat (see
Proposal, Classification). It also fixes the entity allowlist mechanism
the roadmap already named but never specified, and where the Home
Assistant connection's long-lived access token is stored, following this
project's established credential-storage precedent.

## Problem

[docs/roadmap/01-2-local-conversation-capabilities.md](../roadmap/01-2-local-conversation-capabilities.md)
§11 names the plan directly: "introduce Home Assistant through the same
capability executor: 1. discover and read allowlisted entities; 2. answer
state and history questions; 3. propose allowlisted actions; 4. require
confirmation according to risk; and 5. preserve deterministic
authorization outside the model." [ROADMAP.md](../../ROADMAP.md)'s
Milestone 5 entry narrows the first slice further: "read-only Home
Assistant entity discovery, state, and history. Later slices may propose
allowlisted actions... The model never receives unrestricted Home
Assistant, shell, Docker, or network access."
[RFC-0003](0003-capability-contract.md) already anticipated this by name
in its own Non-Goals ("Home Assistant control is explicit non-scope" for
that milestone) and Compatibility section (a later capability "Home
Assistant, Milestone 5" reuses its classification model), and
[RFC-0017](0017-web-search-and-fetch-capability-mapping.md)'s own
Compatibility section built its confirmation wire format "intentionally
general... so Milestone 5's future mutating Home Assistant capabilities
reuse it rather than needing a second design."

None of that is a capability mapping yet. Four concrete gaps block items
1–2 above from being buildable, none hypothetical:

1. **No capability is registered.** `sovereign_conversation.py`'s
   `build_registry()` has no Home Assistant entry at all today (confirmed
   by direct code inspection).
2. **No classification decision.** RFC-0003's Confirmation Model table is
   keyed on `side_effect` × `network`, and `network` is `local` or
   `external`, defined as "`local` capabilities never leave the device."
   A request to a separate Home Assistant host genuinely leaves this
   device's own process boundary — but it never leaves the household's
   own network the way `web.search`/`web.fetch` do. RFC-0003 doesn't
   contemplate this middle case, and nothing else in this project has
   needed to before (Pi-hole is a loopback-only container on the same
   device; SearXNG/llama.cpp are also device-local containers). This RFC
   has to decide how to classify a same-LAN, different-host,
   household-owned service under the existing two-value axis, not invent
   a third value unilaterally.
3. **No allowlist mechanism.** The roadmap says "allowlisted entities"
   twice without specifying where that allowlist lives, who populates it,
   or how a capability's `entity_id` argument gets checked against it.
   Without this, a naive implementation would either expose every Home
   Assistant entity (locks, cameras, presence/person trackers — a real
   privacy and safety miss for a household product) or hardcode a
   household-specific list at build time, which is not renewable
   configuration.
4. **No credential storage decision.** Reading Home Assistant's state
   requires a bearer token (its own long-lived access token mechanism,
   confirmed directly against Home Assistant's REST API documentation —
   see Context and Evidence). This project already has an established,
   qualified pattern for exactly this class of problem
   (`pihole-admin-password`), and a naive implementation would either
   reinvent it worse or skip the question entirely.

## Goals

- Register `home_assistant.list_entities` and `home_assistant.get_history`
  against RFC-0003's contract: schemas, classification, and bounds.
- Decide how a same-LAN, different-host, household-owned service is
  classified under RFC-0003's existing `local`/`external` axis, without
  silently amending that Accepted RFC's structural model.
- Fix the entity allowlist: where it's stored, its shape, and exactly
  which pipeline stage rejects a non-allowlisted `entity_id` and why that
  stage (before or after the confirmation prompt).
- Fix where the Home Assistant base URL and access token are stored,
  matching this project's existing secret-storage precedent
  (`pihole-admin-password`) rather than inventing a new one.
- Resolve [RFC-0017](0017-web-search-and-fetch-capability-mapping.md)'s
  own deferred Unresolved Question — "whether
  `/data/sovereign/capabilities/policy.json` should hold other future
  opt-in toggles... deferred until Milestone 5 or another feature needs
  its own toggle" — since that moment is now.
- Reuse RFC-0017's confirmation pause/resume wire format unchanged,
  confirming in practice the generality that RFC's own Compatibility
  section already claimed for it.

## Non-Goals

- **Allowlisted mutating actions** ("propose allowlisted actions; require
  confirmation according to risk" — roadmap items 3–4). This is
  explicitly the roadmap's *next* slice after the one this RFC covers,
  matching RFC-0006's own precedent of shipping Pi-hole read-only first
  and naming mutation as separate future work. A service-call capability
  (`POST /api/services/<domain>/<service>` in Home Assistant's own REST
  API) genuinely changes physical household state (locks, switches,
  climate) and deserves its own RFC once this slice is stable, not a
  bundled afterthought here.
- **Amending RFC-0003's `network` classification axis** to add a
  distinct "local-network" tier between `local` and `external`. Real
  tension with that binary is named directly below (Proposal,
  Classification, and Drawbacks) but resolving it is a structural change
  to an Accepted RFC's contract, out of this mapping RFC's scope —
  exactly the posture RFC-0017 already took toward a different tension in
  the same table (see RFC-0017's Alternatives Considered, "auto-approve
  after first opt-in").
- **Deploying, installing, or managing Home Assistant itself.** Unlike
  Pi-hole, SearXNG, and llama.cpp — all embedded in Sovereign's own base
  image and lifecycle-managed by `sovereign-update` — Home Assistant is a
  third-party, household-provided system this project does not run,
  version, or update. This RFC assumes a reachable instance already
  exists on the household LAN; provisioning one is entirely outside
  Sovereign's control and this RFC's scope.
- **The WebSocket API**, Home Assistant's other real-time interface.
  RFC-0003's executor model is per-invocation request/response
  (`invoke()` returns once); a persistent subscribed connection doesn't
  map onto that shape without a structural change to the executor itself,
  which this RFC doesn't propose. The REST API's `/api/states` and
  `/api/history/period` already answer the roadmap's "state and history
  questions" scope without it.
- **Console's actual settings UI** (the page where a household enters
  the base URL/token and picks allowlisted entities) — this RFC fixes the
  API contract that UI depends on, matching how RFC-0006/RFC-0017 fixed
  their own API contracts without building Console UI themselves.
  Necessary follow-up implementation, named in Acceptance Criteria, not
  designed here.
- Re-deriving the confirmation *architecture* or wire format — both
  already fixed by RFC-0004 and RFC-0017 respectively. This RFC only
  confirms both capabilities land on RFC-0003's existing
  `read_only`/`external`/`required` row, reusing the mechanism as-is.

## Context and Evidence

- [docs/roadmap/01-2-local-conversation-capabilities.md](../roadmap/01-2-local-conversation-capabilities.md)
  §11 and [ROADMAP.md](../../ROADMAP.md) Milestone 5 — the direct source
  of this RFC's scope, quoted in Problem above.
- [RFC-0003](0003-capability-contract.md) (Accepted): the six-stage
  executor, the Confirmation Model table, and its own explicit
  anticipation of Home Assistant as a future capability reusing this
  contract, without specifying how.
- [RFC-0017](0017-web-search-and-fetch-capability-mapping.md) (Draft, not
  yet formally accepted at the time of writing, but already implemented
  and hardware-smoke-tested per its own Acceptance Criteria strikethrough
  notes): the confirmation pause/resume wire format
  (`pending_confirmation`/`confirmation` fields on
  `POST /api/v1/conversation/message`) this RFC reuses unchanged, and its
  own deferred question about `policy.json`'s scope, resolved here.
- `image-builder/sovereign/appliance/lib/sovereign_pihole.py`, read
  directly: `PIHOLE_PASSWORD_PATH =
  /data/sovereign/secrets/pihole-admin-password`, read by
  `sovereign-conversation.service` itself (not a separate root-run
  script) at call time — the direct precedent for how a `DynamicUser`
  service in this project reads a credential.
- `image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/etc/systemd/system/sovereign-conversation.service`,
  read directly: `SupplementaryGroups=sovereign-pihole-secrets` is how
  that credential read access is actually granted — a sysusers.d group
  created by a root-owned bootstrap step, not something the service
  grants itself. `ReadWritePaths=/data/sovereign/capabilities` is the
  existing, already-granted writable path `policy.json` and the audit log
  already use.
- Home Assistant's REST API, confirmed directly against its own developer
  documentation (`developers.home-assistant.io/docs/api/rest/`):
  bearer-token authentication (`Authorization: Bearer <token>`), a
  long-lived access token created by the household through their own
  Home Assistant profile page (Sovereign never generates or manages this
  token, only stores what the household pastes in — the same posture
  this project already takes toward not touching signing/production keys
  it doesn't own, per [ADR-0006](../adrs/0006-production-signing-key-custody.md)'s
  precedent for a different secret); `GET /api/states` (all entities,
  each with `entity_id`/`state`/`attributes`/`last_changed`);
  `GET /api/states/<entity_id>` (one entity); `GET
  /api/history/period/<timestamp>?filter_entity_id=<id>` (history, ISO
  timestamp, entity-scoped); `POST /api/services/<domain>/<service>`
  (service calls — the mutating-action surface this RFC explicitly does
  not map). Default port `8123`; base URL shape
  `http://<host>:8123/api/`.
- Home Assistant's own local-network discovery: it advertises itself via
  Zeroconf/mDNS under the `_home-assistant._tcp.local.` service type
  (confirmed via Home Assistant's developer network-discovery
  documentation and community references), the same class of mechanism
  this project already relies on for its own device (`sovereign.local`,
  via `avahi-daemon`/`libnss-mdns`, per the Phase 01 image's own package
  set). This RFC treats discovery as a Console-UI convenience
  (pre-filling a base URL, not authenticating or trusting anything by
  itself) rather than a capability-executor concern — see Proposal.
- Entity ID format (`domain.object_id`, e.g. `light.kitchen`,
  `sensor.living_room_temperature`) is a stable, long-documented Home
  Assistant convention this RFC relies on for allowlist and argument
  validation.

## Proposal

### Classification

Both capabilities are `read_only` — neither changes Home Assistant state.
For `network`, this RFC classifies them **`external`**, taking RFC-0003's
existing definition at its word ("`local` capabilities never leave the
device") rather than reading a same-household-LAN exception into it. A
request to Home Assistant genuinely leaves this device's own process and
network-namespace boundary to reach a different physical host — the same
fact pattern RFC-0003's definition describes, even though the destination
never leaves the household's own network the way `web.search`/`web.fetch`
do. Per RFC-0003's Confirmation Model table, `read_only`/`external` is
`required` confirmation — structurally derived, not a choice this RFC
makes independently.

This is a deliberate, disclosed tradeoff, not an oversight: it means
"what's the temperature in the living room," a fully local,
household-owned, ambient query, costs the same per-invocation
confirmation click as a query that reaches the public internet. The
Alternatives Considered and Drawbacks sections below name this tension
directly rather than resolving it by quietly stretching RFC-0003's
`local` definition to cover a case it wasn't written for.

### `home_assistant.list_entities`

- **Purpose:** answer "what is it" and "what's it doing right now"
  questions ("discover and read allowlisted entities") by returning the
  current state of every entity the household has allowlisted.
- **Arguments:** none. The full allowlisted set is small by construction
  (see Entity Allowlist below) and returning all of it in one call avoids
  needing a second "discover the allowlist" round trip before a "read
  state" round trip — the same reasoning RFC-0017 gave for not splitting
  `web.search`'s query and result-count into separate capabilities.
- **Result:** `{ "entities": [ { "entity_id": string, "friendly_name":
  string, "domain": string, "state": string, "unit_of_measurement":
  string | null, "last_changed": timestamp } ], "retrieved_at": timestamp
  }`. Fields mirror what `GET /api/states` already returns per entity,
  narrowed to what a conversation needs — no raw `attributes` blob passed
  through unfiltered, since Home Assistant's own `attributes` object can
  contain fields well beyond what a household intends to expose
  conversationally (e.g. device identifiers, supported-feature bitmasks).
- **Classification:** `read_only`, `external`, `required` confirmation.
- **Bounds:** `timeout_seconds=8` (a same-LAN request to a real second
  host — meaningfully faster than the public internet round trip
  `web.fetch` budgets for, but not the near-zero latency of a loopback
  container `pihole.summary` assumes), `max_result_bytes` left at
  `DEFAULT_MAX_RESULT_BYTES` (64KiB — comfortably enough for a
  reasonably-sized allowlist; a household approaching this limit has an
  allowlist large enough to warrant its own review, not a bigger byte
  budget), `max_invocations_per_turn=1`, matching every other registered
  capability's default.

### `home_assistant.get_history`

- **Purpose:** answer "what happened" and "when did X last change"
  questions for one specific allowlisted entity.
- **Arguments:** `{ "entity_id": string (required, must be in the
  allowlist), "period": "hour" | "day" | "week" (required) }`. A bounded
  enum, not a free-form date range — the same "bounded, enumerated
  argument set" precedent RFC-0006 established for Pi-hole's own `period`
  argument and RFC-0017 explicitly cited for `web.search`'s `time_range`.
  A free-form range would need its own parsing/validation surface and
  could request an unbounded amount of history from Home Assistant's own
  database for no scope benefit this milestone's actual questions need.
  (`period` maps to `/api/history/period/<timestamp>`'s required
  timestamp by computing "now minus one hour/day/week" at invocation
  time — an implementation detail, not an architectural one, the same
  class of deferral RFC-0017 already made for its own extraction-method
  specifics.)
- **Result:** `{ "entity_id": string, "period": string, "changes": [ {
  "state": string, "changed_at": timestamp } ], "retrieved_at": timestamp
  }`. `changes` is capped at 50 entries — plenty for a conversational
  answer ("it's changed state 4 times today") without becoming a raw data
  export, the same "summary endpoint by design, not an export" bound
  RFC-0006 and RFC-0017 both already applied to their own list-shaped
  results.
- **Classification:** `read_only`, `external`, `required` confirmation.
- **Bounds:** `timeout_seconds=10` (a real database query on the Home
  Assistant side, not a simple in-memory state read — deliberately longer
  than `list_entities`'s budget), `max_result_bytes` left at
  `DEFAULT_MAX_RESULT_BYTES`, `max_invocations_per_turn=1`.

### Entity Allowlist

- A new persisted file, `/data/sovereign/capabilities/home-assistant.json`,
  holds `{ "enabled": bool, "base_url": string, "allowlisted_entities": [
  string ] }`. Kept **separate** from `policy.json` — this directly
  resolves RFC-0017's own deferred Unresolved Question. `policy.json`
  stays a flat single-flag file (`web_search_enabled`); Home Assistant's
  configuration is structurally bigger (a connection endpoint and a list,
  not one bool) and belongs in its own file rather than growing
  `policy.json` into a general, ever-expanding device-config blob. Both
  files live under the same already-granted, already-lazily-created
  `/data/sovereign/capabilities/` directory (`ReadWritePaths=` unchanged
  from today) — no new systemd grant needed for this file.
- **Default: `enabled: false`, empty allowlist.** Matching every other
  `external` capability's conservative default in this project
  (`web_search_enabled` defaults `false`) and the milestone plan's own
  "allowlisted" framing — a fresh device exposes nothing until the
  household explicitly configures it.
- **Allowlist membership is checked at RFC-0003's stage 3 (policy check),
  before any confirmation is generated and before any request reaches
  Home Assistant.** This is a deliberate, different choice from
  `web.fetch`'s SSRF check, which happens at stage 5 (execute) because it
  needs a live DNS resolution to prevent a rebinding race between check
  and connect. Allowlist membership needs no network call at all — it's a
  pure comparison against already-loaded local configuration — so
  checking it as early as possible gives the best user experience: a
  proposal for a non-allowlisted `entity_id` is rejected immediately with
  a specific `ENTITY_NOT_ALLOWLISTED` error, the model can tell the user
  why, and no confirmation prompt is ever generated for a request that
  was always going to fail. This mirrors `web.search`'s own "policy off →
  rejected before confirmation" precedent exactly, applied to a
  per-argument check instead of a whole-capability toggle.
- **Populating the allowlist is a Console-settings concern, not a
  capability.** The model never sees Home Assistant's full, unfiltered
  entity list — only whatever the household has already allowlisted.
  Building that allowlist requires a household member to browse the full
  set once, in Console's own settings UI, which needs its own
  authenticated proxy endpoint
  (`GET /api/v1/conversation/home-assistant/entities`, forwarding
  `GET /api/states` with the stored token) distinct from the two
  model-facing capabilities above — named in Acceptance Criteria as
  necessary follow-up, not built here, matching how RFC-0006 and RFC-0017
  both fixed their own settings-adjacent API shape without building the
  settings page itself.

### Credential Storage

- The Home Assistant long-lived access token is stored at
  `/data/sovereign/secrets/home-assistant/access-token`, **not** inside
  `home-assistant.json` alongside the non-sensitive `base_url`/allowlist
  fields — the same separation-of-secret-from-config this project already
  applies to `policy.json` vs. `pihole-admin-password`.
- Unlike `pihole-admin-password` (generated by a root-run `start-pihole`
  script, then read by `sovereign-conversation.service` via the
  `sovereign-pihole-secrets` sysusers.d group), Home Assistant's token is
  not something Sovereign generates — the household creates it themselves
  in their own Home Assistant instance and submits it through Console.
  Since `sovereign-conversation.service` is therefore both the writer
  (accepting the household's submission through its own authenticated
  endpoint) and the only reader, this needs no new sysusers.d group or
  root-run bootstrap step — a new `ReadWritePaths=/data/sovereign/secrets/home-assistant`
  entry on the existing unit is sufficient, and the directory is lazily
  self-created the same way `/data/sovereign/capabilities/` already is
  (RFC-0017's own precedent, cited there against inventing a
  `tmpfiles.d` entry). This is deliberately a **separate** directory from
  `/data/sovereign/secrets/pihole-admin-password`'s own — scoping this
  service's new write access to only its own subdirectory, so a
  compromised `sovereign-conversation.service` process gains no new
  ability to overwrite Pi-hole's credential, which it does not need
  write access to today and still won't.
- `GET /api/v1/conversation/home-assistant` (the config-read endpoint)
  never echoes the token value back — only
  `{ "enabled": bool, "base_url": string, "has_access_token": bool,
  "allowlisted_entities": [string] }`. The same "never log or return a
  secret verbatim" posture this project's audit-log design already
  applies to capability arguments.
- `POST /api/v1/conversation/home-assistant` accepts `base_url`,
  `access_token` (optional — omitted means "leave the stored token
  unchanged," so re-saving the allowlist doesn't require re-pasting the
  token every time), and `allowlisted_entities`, authenticated identically
  to `/message` and `/policy` (delegating to console-auth's
  `verify-mutating`).

## Interfaces and Data Flow

```text
Model proposes home_assistant.list_entities({})       [RFC-0004 flow]
    -> RFC-0003 executor stages 1-3: resolve, validate arguments
       (no arguments to validate for list_entities),
       check policy (enabled must be true, read fresh from
       /data/sovereign/capabilities/home-assistant.json each request)
    -> stage 3 fails (disabled) -> rejection appended to context
    -> stage 3 passes, confirmation required (structural, both
       capabilities) -> confirmation_store.issue() -> round halts,
       pending_confirmation returned [RFC-0017's existing wire format,
       unchanged]
    -> Console prompts using the same confirmation card RFC-0017 already
       built: "home_assistant.list_entities wants to read your allowlisted
       Home Assistant entities — this leaves your device. Approve?"
    -> user approves -> client resubmits with
       {"confirmation": {"token": "...", "approve": true}}
    -> confirmation_store.consume() -> invoke() proceeds through stages
       5-6: GET <base_url>/api/states with the stored bearer token,
       filtered to allowlisted_entities, shaped to the declared
       result_schema -> appended to context

home_assistant.get_history({"entity_id": "...", "period": "day"}):
    -> stage 2 validates entity_id/period against their argument schema
       (shape only, no allowlist knowledge)
    -> stage 3 additionally checks entity_id against the allowlist
       (ENTITY_NOT_ALLOWLISTED if absent) -- before stage 4's confirmation
       gate is ever reached, so an out-of-allowlist request never
       generates a prompt
    -> stage 5: GET <base_url>/api/history/period/<timestamp>
       ?filter_entity_id=<entity_id>, shaped to the declared result_schema
```

## Security and Privacy

- **Every** invocation of either capability requires per-invocation user
  confirmation, structurally, per RFC-0003's table — there is no
  automatic path, matching `web.search`/`web.fetch`'s own posture. A
  prompt-injected model can cause a proposal, never an execution.
- The entity allowlist is the primary privacy control: a household that
  has a Home Assistant `person`/`device_tracker` entity (presence,
  location), a `lock`/`alarm_control_panel` entity, or a camera entity
  simply never adds it to the allowlist, and the model can never
  discover, name, or query it — not merely "the model is asked not to,"
  but structurally absent from every result this capability can ever
  return.
- The allowlist check happening before confirmation (see Entity Allowlist
  above) means a proposal for a non-allowlisted entity never even
  discloses that entity's existence in a confirmation prompt — the
  rejection is generic (`ENTITY_NOT_ALLOWLISTED`), not "entity X exists
  but isn't allowlisted," which would itself leak information about the
  household's device inventory to anything reading the conversation
  transcript.
- The access token is a real credential (bearer access to whatever the
  household's own Home Assistant instance permits, potentially much
  broader than the specific allowlisted entities this RFC's capabilities
  ever query) — stored outside conversation context entirely, never
  passed to or visible from the model, matching `pihole-admin-password`'s
  own handling.
- Audit events follow RFC-0003 unchanged: the fact of invocation,
  classification, outcome, and which stage was reached — never entity
  state values or history content, which is real household activity data
  at least as sensitive as the search-query content RFC-0017 already
  refused to log.
- Unlike `web.fetch`, the destination (`base_url`) is household-configured
  and never model-influenced, so no SSRF-style resolve-then-check policy
  is needed here — the only untrusted, model-supplied input is
  `entity_id`/`period`, both closed, bounded values checked against
  server-held state before any request is made.

## Failure and Recovery

- Home Assistant unreachable or returning a non-2xx response: fails
  through RFC-0003's normal bounded-execution failure path, audited like
  any other capability failure, narrated by the model as a failure
  ("I couldn't reach Home Assistant right now") — not a fabricated
  empty-state answer.
- `enabled: true` but `base_url`/`access_token` not yet configured (a
  household turned the feature on before finishing setup, or Console
  hasn't been used yet): rejected at stage 3 with a distinct
  `CAPABILITY_NOT_CONFIGURED` code, separate from `CAPABILITY_DISABLED`,
  so the model can narrate the actual situation ("Home Assistant isn't
  set up yet") instead of a generic "disabled" message that would be
  misleading once the household believes they've turned it on.
- An `entity_id` that was allowlisted but has since been removed or
  renamed on the Home Assistant side (a real, expected drift case — Home
  Assistant entities can be deleted or renamed independent of Sovereign)
  surfaces as a normal bounded-execution failure (Home Assistant's own
  404 from `/api/states/<entity_id>`) once past the allowlist check —
  Sovereign's allowlist does not attempt to stay synchronized with Home
  Assistant's own entity registry in real time; this is a disclosed,
  accepted limitation of a locally-cached allowlist rather than a live
  query against Home Assistant on every check.
- A confirmation token that expires while genuinely pending, or a
  `sovereign-conversation` process restart invalidating an in-memory
  token, behaves identically to RFC-0017's own already-implemented and
  qualified handling — no new behavior, reusing the same mechanism.

## Compatibility and Migration

No existing Home Assistant capability to migrate from. Both new
capabilities and the `home-assistant.json`/credential-directory additions
are purely additive: no change to `POST /api/v1/conversation/message`'s
wire format beyond what RFC-0017 already shipped (the
`pending_confirmation`/`confirmation` fields), verified by the existing
`test_conversation_service.py` suite continuing to pass unmodified. A
future allowlisted-actions RFC can reuse this RFC's allowlist storage
shape and confirmation reuse pattern rather than needing a third design.

## Operations and Observability

- `home-assistant.json`'s `enabled`/`base_url`/`allowlisted_entities`
  (never the token) should be inspectable the same way `policy.json`
  already is — a future Console settings panel reads and writes it, not
  a separate config path, per RFC-0003's own Operations precedent.
- The capability audit log records how often each Home Assistant
  capability is proposed, approved, denied, or rejected by policy or
  allowlist — the same operational signal RFC-0017 already named for
  judging whether a confirmation-gated capability's UX is actually
  working in practice, applicable here without change.

## Testing Strategy

- Contract-level tests mirroring RFC-0006/RFC-0017's pattern: argument
  validation rejects a malformed `entity_id` (wrong `domain.object_id`
  shape) and an invalid `period` value, both before any allowlist or
  network concern is reached.
- Allowlist tests: an `entity_id` absent from `allowlisted_entities` is
  rejected with `ENTITY_NOT_ALLOWLISTED` at stage 3, before a
  confirmation is generated — verified directly, the same structural
  proof RFC-0017 required for `external_enabled: false` rejecting before
  confirmation.
- Policy-gate tests: `enabled: false` (the real default) rejects both
  capabilities before confirmation; `enabled: true` with an unset
  `base_url`/token produces `CAPABILITY_NOT_CONFIGURED`, distinctly from
  `CAPABILITY_DISABLED`.
- Confirmation wire-format tests confirming RFC-0017's existing mechanism
  is reused correctly for a second pair of capabilities — no new
  wire-format code path is exercised, only a second registration
  consuming the same one.
- Fixture-backed tests for both capabilities' Home Assistant-calling
  happy path (a stub HTTP server returning realistic `/api/states`/
  `/api/history/period` shapes) without requiring a live Home Assistant
  instance for every test run — mirroring RFC-0006/RFC-0017's own
  testing strategy.
- Credential-handling tests: `GET /api/v1/conversation/home-assistant`
  never includes the token value in its response body, verified
  directly against the raw JSON, not merely against a client that
  happens not to render it.
- Real-hardware qualification is explicitly **dependent on a real Home
  Assistant instance being reachable on the project's own household
  network** — unlike Pi-hole/SearXNG/llama.cpp, this is not something
  Sovereign provisions itself as part of qualification, so this RFC
  cannot commit to a qualification timeline the way RFC-0017 could for a
  capability backed by an embedded, Sovereign-managed service.

## Alternatives Considered

- **Classify Home Assistant as `local`**, reasoning that "same household
  network" is functionally equivalent to "same device" for privacy
  purposes. Rejected: RFC-0003's own text defines `local` as "never
  leaves the device," not "never leaves the household" — stretching that
  definition here would be an undisclosed, ad hoc amendment to an
  Accepted RFC's structural contract, exactly the kind of scattered
  judgment call RFC-0003 itself rejected as an alternative during its own
  drafting ("let each capability define its own confirmation
  requirement"). If this classification proves too conservative in
  practice, RFC-0003 names its own Drawbacks section as the place to
  revisit it deliberately — not this mapping RFC.
- **Auto-approve after a first per-conversation opt-in**, rather than
  per-invocation confirmation, to reduce the UX cost of the `external`
  classification above. Rejected for the identical reason RFC-0017
  rejected it for `web.search`: RFC-0003's confirmation model already
  fixed "freshly-obtained... never a standing blanket approval" as
  structural.
- **Store the access token inside `home-assistant.json`** alongside the
  non-sensitive configuration, for a simpler single-file design. Rejected:
  this project already treats secrets and config as separately-stored,
  separately-permissioned classes of data (`policy.json` vs.
  `pihole-admin-password`); mixing them here would be a regression from
  established practice for no real simplification benefit.
- **Use the WebSocket API for a live-updating entity view.** Considered,
  since it's Home Assistant's more idiomatic real-time interface, but
  rejected for this RFC: RFC-0003's executor is a per-invocation
  request/response model, and a persistent subscription doesn't fit it
  without a structural executor change this RFC doesn't propose. The REST
  API fully answers "discover and read" and "answer state and history
  questions" without needing a live connection.
- **A free-form date-range argument for `get_history`** instead of a
  bounded `period` enum. Rejected for the same reason RFC-0006 and
  RFC-0017 both chose bounded enums over free-form ranges: it's real
  additional parsing/validation surface and an unbounded-size result risk
  for a milestone whose actual questions ("what happened today," "when
  did it last change") are all satisfied by a small closed set.

## Drawbacks and Maintenance Cost

- The `external` classification (see Alternatives Considered) means even
  the most mundane, fully-local, household-owned query — "what's the
  temperature" — costs the same confirmation round trip as a query that
  genuinely reaches the public internet. This is the single biggest,
  disclosed UX cost of this RFC's design, inherited directly from
  RFC-0003's existing structural model rather than introduced by this
  RFC. If real usage after this ships shows this makes the read-only
  slice too friction-heavy to be useful — the exact tension RFC-0003's
  own Drawbacks section already flagged in the abstract for "read-only
  external capabilities used often" — the right fix is a deliberate
  RFC-0003 amendment informed by that real evidence, not a workaround
  invented here.
- A second, separate persisted-config file (`home-assistant.json`) and a
  second, separate secrets directory add real, ongoing surface area
  beyond what `policy.json`/`pihole-admin-password` already established
  — justified here by genuinely different data shapes (a connection
  endpoint and a list, not one bool; a household-submitted token, not a
  Sovereign-generated one), not by convenience.
- The locally-cached allowlist can drift from Home Assistant's own
  entity registry (see Failure and Recovery) — an accepted, disclosed
  limitation rather than building live allowlist-registry
  synchronization this milestone's actual scope doesn't need.
- Real-hardware qualification depends on external infrastructure
  (a household's own Home Assistant instance) this project doesn't
  control, unlike every prior capability's qualification path — a real,
  disclosed schedule risk, not a defect of this RFC's design.

## Unresolved Questions

None of the following block acceptance of the mapping and design fixed
above:

- Whether the `external` classification (see Alternatives Considered)
  should eventually motivate a genuine RFC-0003 amendment introducing a
  distinct "local-network" tier — explicitly named as a candidate future
  revisit, not decided here, and not blocking this RFC.
- The exact Console settings-page flow for building the allowlist
  (a live-browsed picker vs. a manually-entered list of entity IDs) is UI
  design, not architecture.
- Whether `home-assistant.json` should eventually support more than one
  Home Assistant instance (some households run more than one, e.g. a
  separate test instance) — no evidence this milestone's actual scope
  needs it; single-instance is the smallest design that answers the
  roadmap's real questions.
- Real behavior when Home Assistant's own long-lived token expires or is
  revoked by the household from their own Home Assistant UI — expected to
  surface as a normal bounded-execution authentication failure, but
  unverified against a real instance.
- **TLS certificate verification for `base_url`, found during review and
  not addressed in the Proposal above.** A household running Home
  Assistant with `https://` (its own self-signed certificate, or a
  LAN-internal CA — both common for local installs, unlike `web.fetch`'s
  targets, which are public and hold ordinary publicly-trusted certs) may
  fail to connect under ordinary certificate verification, or — if the
  implementation instead disables verification to route around that —
  quietly lose any protection against a spoofed on-LAN response. Neither
  half of that tradeoff is decided here. This is implementation-level,
  not a change to this RFC's classification, allowlist, or credential
  design, so it does not block acceptance, but it must be resolved
  (most likely: support a plain `http://` default matching Home
  Assistant's own common local-network configuration, and require normal
  certificate verification if a household opts into `https://`, never a
  blanket bypass) before `POST /api/v1/conversation/home-assistant`
  ships.

## Acceptance Criteria

- `home_assistant.list_entities` and `home_assistant.get_history` are
  registered against RFC-0003's contract with the schemas above,
  classified `read_only`/`external`/`required`.
- `/data/sovereign/capabilities/home-assistant.json` is read fresh per
  request (not cached at process start), matching `policy.json`'s
  existing freshness behavior — verified by a test that toggling the
  file's content between requests changes the outcome without a service
  restart.
- A proposal for an `entity_id` outside `allowlisted_entities` is
  rejected with `ENTITY_NOT_ALLOWLISTED` before any confirmation is
  generated and before any Home Assistant request is attempted —
  verified directly, mirroring RFC-0017's own proof pattern for
  `external_enabled: false`.
- `enabled: false` (the real default on a device that has never touched
  this configuration) rejects both capabilities at the policy stage —
  verified directly, confirming the milestone's allowlist/opt-in
  requirement is structurally true on a fresh device.
- `enabled: true` with no stored `base_url`/token produces
  `CAPABILITY_NOT_CONFIGURED`, distinct from `CAPABILITY_DISABLED` —
  verified directly.
- The confirmation pause/resume flow for both capabilities reuses
  RFC-0017's existing `pending_confirmation`/`confirmation` fields with
  no new wire-format code path — verified by extending
  `test_conversation_service.py`'s existing confirmation tests to a
  second capability pair rather than writing a parallel mechanism.
- `GET /api/v1/conversation/home-assistant` never returns the stored
  access token value — verified directly against the raw response body.
- Existing tests (`test_conversation_service.py`, `test_capabilities.py`,
  RFC-0017's own web-search/fetch tests) continue to pass unmodified,
  confirming this RFC's additions are additive to the existing turn loop
  and executor.

Explicitly **not** required for acceptance, named as necessary follow-up
implementation matching this project's precedent of separating proposal
from build-out:

- The capability implementation itself (`sovereign_homeassistant.py` or
  equivalent), the `home-assistant.json`/credential-directory reading and
  writing, and the two new HTTP endpoints
  (`GET`/`POST /api/v1/conversation/home-assistant`, plus the
  entity-browsing proxy endpoint for the settings page).
- Console's settings UI for entering the base URL/token and building the
  allowlist, and the confirmation-card copy for these two specific
  capabilities (the card mechanism itself is already built, per
  RFC-0017's Acceptance Criteria).
- Real-hardware qualification against an actual Home Assistant instance
  — dependent on one being available on the project's household network,
  per Testing Strategy's disclosed schedule risk.

## Decision

**Accepted (2026-08-21, project creator, reviewed by Claude at the
project creator's direction).** The `home_assistant.list_entities`/
`home_assistant.get_history` mapping, the `external` classification of
Home Assistant traffic, the entity allowlist mechanism (checked at
stage 3, before confirmation), and the credential-storage design are
accepted as this milestone's platform contract. Review before acceptance
found and fixed one real internal inconsistency (the Interfaces and Data
Flow diagram misstated the allowlist check as stage 2 instead of stage 3,
contradicting the Entity Allowlist section's own prose) and one genuine
gap not previously addressed (TLS certificate verification behavior for
`base_url`, now recorded as a named, non-blocking Unresolved Question with
a concrete direction: support plain `http://` for the common local
case, and real certificate verification — never a blanket bypass — if a
household opts into `https://`). Both are fixed in this revision. The
Unresolved Questions above, including whether RFC-0003's `network` axis
should eventually grow a distinct local-network tier, are accepted as
non-blocking follow-ups, not gating conditions, matching RFC-0003's own
precedent for its Unresolved Questions.
