# RFC-0019: Home Assistant Allowlisted-Action Capability Mapping

**Status:** Accepted (2026-08-21, project creator)
**Author:** Project creator and Claude
**Created:** 2026-08-21
**Reviewers:** Project creator
**Target phase:** [Milestone 01.2, Local Conversation and Capabilities](../roadmap/01-2-local-conversation-capabilities.md) §11, Following Vertical Slice; [ROADMAP.md](../../ROADMAP.md) Milestone 5, Home Automation Integration
**Supersedes:** None

## Summary

Registers one mutating Home Assistant capability, `home_assistant.set_entity_state`,
against [RFC-0003](0003-capability-contract.md)'s contract — the roadmap's
second Home Assistant slice ("propose allowlisted actions... require
confirmation according to risk"), building on
[RFC-0018](0018-home-assistant-read-only-capability-mapping.md) (Accepted)'s
read-only slice rather than replacing it. Structurally this is
`mutating`/`external`, which RFC-0003's table already fixes as
`confirmation: required` — the same tier `read_only`/`external`
capabilities already sit at, since RFC-0003's table has no tier above
`required`. This RFC does not invent one. Instead it answers "confirmation
according to risk" the way RFC-0018 answered its own hardest question:
by being deliberately conservative about *scope*, not by inventing a new
confirmation *mechanism* RFC-0003 doesn't have. Concretely: this slice
covers exactly two Home Assistant domains, `light` and `switch` — the
lowest-consequence, fully-reversible, no-numeric-range action domains
Home Assistant exposes — and explicitly excludes locks, climate, covers,
cameras, and every other domain as out of scope for a future RFC once
this narrower slice has real usage behind it, mirroring how RFC-0018
itself shipped read-only before any mutating capability at all.

This RFC also has to resolve two things RFC-0018 didn't need to: a
second, independent allowlist and policy toggle for *control*, distinct
from the *read* allowlist and toggle RFC-0018 already built (so enabling
reading never silently enables controlling — the same principle RFC-0018
itself used to keep Home Assistant separate from `web.search`); and the
mutating-capability confirmation UX RFC-0003 and RFC-0004 both explicitly
named as this project's first real design question in that area, since no
mutating capability has existed until now.

## Problem

[docs/roadmap/01-2-local-conversation-capabilities.md](../roadmap/01-2-local-conversation-capabilities.md)
§11 names this slice directly: "3. propose allowlisted actions; 4. require
confirmation according to risk; and 5. preserve deterministic
authorization outside the model." [ROADMAP.md](../../ROADMAP.md)'s
Milestone 5 entry: "Later slices may propose allowlisted actions, but
deterministic policy outside the model must authorize them and require
confirmation according to risk. The model never receives unrestricted
Home Assistant, shell, Docker, or network access."
[docs/roadmap/00-master-plan.md](../roadmap/00-master-plan.md)'s Home
Assistant Integration section adds: "Add controlled actions. Require
confirmation for sensitive actions." Both [RFC-0003](0003-capability-contract.md)
and [RFC-0004](0004-ai-capability-invocation.md) explicitly deferred the
one open question standing between "read-only Home Assistant exists" and
"allowlisted actions exist" to whichever RFC ships the first mutating
capability — RFC-0003's own Unresolved Questions: "The exact
mutating-capability confirmation UX (beyond 'required') is deferred to
Milestone 5, when a mutating capability first actually ships." RFC-0004's
own Non-Goals: "Mutating-capability confirmation UX beyond what RFC-0003
already deferred to Milestone 5 — no mutating capability exists yet for
this RFC to design a flow around." That capability is this RFC's.

Three concrete gaps block a Home Assistant action capability from being
buildable, none hypothetical:

1. **No mutating capability has ever been registered in this project.**
   `system.health`, both Pi-hole capabilities, `web.search`/`web.fetch`,
   and RFC-0018's own `home_assistant.list_entities`/`get_history` are
   all `read_only`. RFC-0003's Confirmation Model table already has a
   `mutating`/`external` row (`required`, same as `read_only`/`external`)
   but nothing has ever exercised it — the executor's stage-4 confirmation
   gate is unit-tested against synthetic fixture capabilities
   (`tests/test_capabilities.py`), never a real mutating capability's real
   implementation.
2. **No control-specific authorization exists.** RFC-0018's entity
   allowlist (`allowlisted_entities` in `home-assistant.json`) governs
   what the model may *read* — it says nothing about what it may
   *change*, and reusing it directly for control would mean a household
   opting into "the assistant can tell me the kitchen light is on" also
   silently grants "the assistant can turn it off," collapsing two
   different consent decisions into one. RFC-0018's own `policy_key`
   generalization (`sovereign_capabilities.Capability`) was built
   specifically to keep independent toggles independent (that RFC's own
   words: "enabling web search must not silently also enable Home
   Assistant") — the same principle now applies one level deeper, within
   Home Assistant itself.
3. **No mutating-capability confirmation UX exists**, by RFC-0003/RFC-0004's
   own explicit, on-the-record deferral quoted above. A confirmation
   prompt that discloses "will read `light.kitchen`'s state" and one that
   discloses "will turn `light.kitchen` **off**, in your actual home,
   right now" are not the same kind of decision, even though RFC-0003's
   structural table classifies both as `required`. Nothing in this
   project has designed what that disclosure should say, whether a
   successful action needs a different receipt than a successful read, or
   how a no-op (proposing to turn on a light that's already on) should be
   represented.

## Goals

- Register `home_assistant.set_entity_state` against RFC-0003's contract:
  schema, classification (`mutating`/`external`/`required`, structural),
  and bounds.
- Scope this slice to exactly the domains whose actions are fully
  reversible and carry no numeric, safety, or privacy risk — deferring
  every other domain to a named future RFC rather than attempting a
  general Home Assistant control surface in one pass.
- Design the control-specific allowlist and its relationship to RFC-0018's
  existing read allowlist (a subset, never a superset), and the
  control-specific policy toggle's relationship to RFC-0018's existing
  read toggle (independent, not shared).
- Design the mutating-capability confirmation disclosure and receipt —
  the concrete answer to RFC-0003/RFC-0004's shared deferral — reusing
  RFC-0017's confirmation wire format unchanged, the same way RFC-0018
  already proved that format capability-agnostic.
- Define idempotent behavior for a proposal that requests a state the
  entity is already in, so "turn off the kitchen light" when it's already
  off is a normal, narrated success, not an error or a wasted Home
  Assistant request.

## Non-Goals

- **Every Home Assistant domain except `light` and `switch`.** Locks,
  climate, covers (garage doors, blinds), cameras, alarm control panels,
  and every other domain are explicitly out of scope. This is the
  concrete, scope-level answer to "confirmation according to risk" — see
  Summary and Proposal, Domain Scope. A future RFC can extend this
  capability's domain set (or add domain-specific capabilities) once this
  narrower slice has real usage and audit-log evidence behind it, the
  same "revisit once real usage exists" posture RFC-0017 already took
  toward SearXNG's upstream engine list.
- **Any service call beyond on/off.** No brightness, color, temperature,
  position, or other numeric/enumerated service data — `state: "on" |
  "off"` is the entire action surface this RFC defines. Dimming and color
  control are real, anticipated future work, not designed here.
- **A generic `call_service` passthrough** taking `domain`/`service`/
  `service_data` as free arguments. Rejected outright, not merely
  deferred: RFC-0004/the milestone plan's own Exit Criteria bar
  ("no model output can directly invoke... Home Assistant... or
  unrestricted network access") already rules this out, and this
  project's own precedent (RFC-0006, RFC-0017, RFC-0018) is small, named,
  bounded capabilities per real use case, never one parameterized
  general-purpose tool.
- **Amending RFC-0003's Confirmation Model table** to add a tier above
  `required`, or any per-capability confirmation strength. Real tension
  is named directly (Proposal, Confirmation Disclosure) but resolving it
  the way this RFC does — narrowing *scope*, not inventing a new
  *mechanism* — is deliberately chosen over an RFC-0003 amendment, for
  the same reason RFC-0018 declined to amend RFC-0003's `local`/`external`
  axis rather than resolve its own tension in scope/design instead.
- **Console's actual settings UI** for the control toggle and the
  controllable-entities picker — this RFC fixes the API contract (an
  extension of RFC-0018's existing `home-assistant.json`/
  `/api/v1/conversation/home-assistant` surface) that UI depends on,
  matching how RFC-0018 fixed its own API contract before its Console UI
  was built in a separate follow-up pass. Named in Acceptance Criteria as
  necessary follow-up, not built here.
- Real-hardware qualification — depends on the same external dependency
  RFC-0018 already disclosed (a real Home Assistant instance reachable on
  the household network), unresolved as of this RFC's writing.

## Context and Evidence

- [docs/roadmap/01-2-local-conversation-capabilities.md](../roadmap/01-2-local-conversation-capabilities.md)
  §11 and [ROADMAP.md](../../ROADMAP.md) Milestone 5, and
  [docs/roadmap/00-master-plan.md](../roadmap/00-master-plan.md)'s Home
  Assistant Integration section — the direct source of this RFC's scope,
  quoted in Problem above.
- [RFC-0003](0003-capability-contract.md) (Accepted): the
  `mutating`/`external` → `required` row already exists in the
  Confirmation Model table (derived structurally, same as
  `read_only`/`external`); its own Unresolved Questions explicitly name
  "the exact mutating-capability confirmation UX" as this RFC's job.
- [RFC-0004](0004-ai-capability-invocation.md) (Accepted): the
  confirmation flow's architecture (pending decision surfaced, single-use
  time-bounded token, model never sees the token, denial is a normal
  audited outcome) is fixed and reused unchanged; its own Non-Goals name
  the same deferral RFC-0003 does.
- [RFC-0017](0017-web-search-and-fetch-capability-mapping.md) (Accepted):
  the confirmation pause/resume wire format
  (`pending_confirmation`/`confirmation` fields on
  `POST /api/v1/conversation/message`), already proven capability-agnostic
  once by RFC-0018's own reuse, reused unchanged again here.
- [RFC-0018](0018-home-assistant-read-only-capability-mapping.md)
  (Accepted): the entity allowlist and `policy_key`/`policy_check`
  generalization this RFC builds directly on; `home-assistant.json`'s
  existing shape (`enabled`, `base_url`, `allowlisted_entities`) and the
  credential-storage design, both extended rather than replaced here.
- `image-builder/sovereign/appliance/lib/sovereign_homeassistant.py`,
  read directly: `read_config()`/`write_config()`/`policy_fields()`,
  `fetch_all_states()`, and the `_get()` HTTP client this RFC's own
  implementation would extend with a `_post()` counterpart for Home
  Assistant's service-call endpoint.
- Home Assistant's REST API, confirmed directly against its own developer
  documentation (`developers.home-assistant.io/docs/api/rest/`):
  `POST /api/services/<domain>/<service>` accepts a JSON body (commonly
  `{"entity_id": "..."}`, plus service-specific fields this RFC doesn't
  use) and returns a list of entities whose state changed while the
  service executed (each with `entity_id`/`state`/`attributes`/
  `last_changed`) — HTTP 200 on success, 400 if `return_response`
  semantics are used incorrectly (this RFC never sets `return_response`).
  `light.turn_on`/`light.turn_off` and `switch.turn_on`/`switch.turn_off`
  are Home Assistant's own standard, long-documented services for exactly
  the on/off action this RFC defines — no service discovery or per-install
  service-catalog lookup is needed for a fixed, known service pair per
  domain.
- Console's existing Home Assistant page
  (`image-builder/sovereign/appliance/console/index.html`), read
  directly: the pre-existing "Capability scope" preview panel already
  models authorization as per-domain grants (Lights/Climate shown
  granted, Locks/Cameras shown not granted) — evidence this project's own
  earlier design work already anticipated domain-level risk
  differentiation for actions, which this RFC's Domain Scope section
  makes real for exactly two of those domains.

## Proposal

### Domain Scope

This slice's action surface is `light` and `switch` only, enforced at
three independent points (config write, policy check, and service-call
construction — see below), not merely by convention:

- **Why these two domains and no others.** Both are binary (`on`/`off`),
  immediately and fully reversible (turning a light back on undoes
  turning it off, with no partial or accumulating state), carry no
  numeric range to validate or misconfigure, and have no safety
  implication beyond ordinary light/appliance use. Locks and alarm
  panels are safety- and security-critical (RFC-0018's own Security and
  Privacy section already named `lock`/`alarm_control_panel` as entities
  a household would reasonably never even allowlist for *reading*, let
  alone controlling). Climate has a numeric range that's genuinely
  risky to get wrong (a mis-set target temperature is a real comfort/
  equipment-wear problem) and household-specific bounds this RFC has no
  evidence to set safely. Covers (garage doors) and cameras carry
  physical-security and privacy implications neither reading nor a
  simple on/off model addresses. All are real, anticipated future
  capabilities — deliberately not designed here.
- **Enforced independently at three separate points, not derived once
  and trusted downstream — found to matter concretely, not just in
  principle, during this RFC's own review (see below).**
  1. `write_config()` (extended below) rejects any `controllable_entities`
     entry whose domain (the `entity_id`'s own dot-prefix, e.g. `light`
     in `light.kitchen` — the same derivation RFC-0018's
     `fetch_all_states`/`make_list_entities_implementation` already use)
     is not `light` or `switch`, regardless of how the entry was
     submitted — a raw API call bypassing any future Console picker gets
     the identical rejection, not just a UI that happens not to offer the
     option.
  2. The executor's stage-3 `policy_check` for this capability re-derives
     the domain from the proposed `entity_id` and independently confirms
     it is `light`/`switch` before proceeding — not merely checking list
     membership and trusting that membership implies a safe domain.
  3. The implementation itself, immediately before constructing the
     `POST /api/services/<domain>/...` URL, performs the identical
     independent check a third time and refuses to proceed if it ever
     fails — see Idempotent No-Ops.

     Points 2 and 3 are not redundant paranoia: this RFC's own review
     found that Home Assistant's `climate` domain has real, valid
     `climate.turn_on`/`climate.turn_off` services (confirmed against
     Home Assistant's own documentation) — meaning if a non-light/switch
     entity ever reached the service-call construction step (a write-time
     validation bug, direct config-file corruption, or a future code
     change that weakens `write_config()`'s check), deriving `domain`
     from `entity_id` and calling that domain's `turn_on`/`turn_off`
     would not fail loudly by accident the way an obviously-wrong service
     name might. `lock` entities (`lock.lock`/`lock.unlock`, not
     `turn_on`/`turn_off`) happen to fail safely if this ever occurred;
     `climate` does not. Relying on that asymmetry — safe for some
     domains, not others, and never by design — is exactly the kind of
     incidental, unverified safety property this project's own precedent
     (RFC-0017's SSRF policy: "resolve before connecting," never trust a
     one-time earlier check) already rejects. The independent re-check at
     both stage 3 and inside the implementation closes this for real,
     rather than relying on write-time validation never having a bug.

### `home_assistant.set_entity_state`

- **Purpose:** turn an allowlisted light or switch entity on or off.
- **Arguments:** `{ "entity_id": string (required, must be in
  `controllable_entities`), "state": "on" | "off" (required) }`. No
  `toggle` option — an explicit target state is a clearer instruction for
  a model to reason about and for a household to review in a confirmation
  prompt than a relative flip, which requires the reader to already know
  current state to judge the effect. `toggle`'s only advantage (not
  needing to know current state) is not a real constraint here: this
  capability's own implementation already reads current state to
  determine whether the request is a no-op (see Idempotent No-Ops below),
  so nothing is saved by supporting it.
- **Result:** `{ "entity_id": string, "domain": "light" | "switch",
  "previous_state": string, "new_state": string, "changed": bool,
  "applied_at": timestamp }`. `changed: false` with `previous_state ==
  new_state == state` represents a successful no-op (already in the
  requested state) — a real, narratable outcome ("the kitchen light was
  already off"), not an error and not indistinguishable from a state
  change that actually happened.
- **Classification:** `mutating`, `external` (fixed by RFC-0003),
  `required` confirmation (derived, not chosen — RFC-0003's table has no
  higher tier for this RFC to reach for).
- **Bounds:** `timeout_seconds=10` (a same-LAN request plus, for a
  non-no-op call, a real Home Assistant service execution — matching
  `home_assistant.get_history`'s own budget for a real backend operation,
  longer than `list_entities`'s simple state read), `max_result_bytes`
  left at `DEFAULT_MAX_RESULT_BYTES`, `max_invocations_per_turn=1`,
  matching every other registered capability's default — deliberately not
  raised for this capability despite a household plausibly wanting to
  control several lights in one request; RFC-0004's per-turn round budget
  (`MAX_ROUNDS_PER_TURN = 3`) already lets a model propose a second
  action in a later round of the same turn once the first is resolved, so
  the real constraint is "one confirmed action at a time," not "one
  action per conversation."

### Idempotent No-Ops

The implementation reads the entity's current state (via the same
`GET /api/states/<entity_id>` this module's read-only capabilities
already use) before deciding whether to call Home Assistant's
service-call endpoint at all:

- **Current state already matches the requested `state`:** returns
  `changed: false` immediately, without calling
  `POST /api/services/<domain>/turn_<state>` — a proposal to turn off an
  already-off light does not generate an unnecessary Home Assistant
  request, and the model gets an accurate, narratable answer ("already
  off") rather than a generic success that implies something happened.
- **Current state differs:** first re-derives `domain` from `entity_id`'s
  own prefix and independently asserts it is `light` or `switch` — see
  Domain Scope's third enforcement point above, not merely trusted from
  the allowlist membership check — then calls
  `POST /api/services/<domain>/turn_on` or `.../turn_off` with
  `{"entity_id": entity_id}`, then verifies the response's changed-states
  list actually contains `entity_id` with the expected new state before
  reporting `changed: true` — Home Assistant returning 200 with an empty
  or unexpected changed-states list (a real possible outcome: the entity
  went unavailable between the state read and the service call, or the
  specific device didn't actually respond) is treated as a distinct
  failure (`HOME_ASSISTANT_ACTION_NOT_CONFIRMED`), not a false success.
  Reporting "done" for a light that didn't actually turn off would be a
  household trusting a receipt that isn't true — worse than a visible
  failure the model can narrate honestly.
- This state-then-act sequence is not perfectly race-free (something else
  could change the entity's state between the read and the write — a
  household member using a physical switch, or Home Assistant's own
  automations) — disclosed as a known, accepted limitation in Failure and
  Recovery, not a gap this RFC pretends to close. The verification step
  above (checking the service call's own response, not just trusting
  the read-then-act sequence blindly) is what actually matters for
  correctness; the no-op check is a request-avoidance optimization, not
  itself a safety mechanism.

### Control Allowlist and Policy Toggle

Extends RFC-0018's existing `home-assistant.json` (not a new file — this
is the same connection's config, a further permission dimension on it,
unlike the earlier `policy.json`-vs-`home-assistant.json` split, which
was about genuinely unrelated features):

- Two new fields: `control_enabled: bool` (default `false`) and
  `controllable_entities: [string]` (default `[]`).
- **`write_config()` (extended) validates, and rejects the whole write if
  violated:** every entry in `controllable_entities` must already be
  present in `allowlisted_entities` (control is a subset of read — you
  cannot grant control over something not even opted into reading), and
  every entry's domain (derived from its own `entity_id` prefix) must be
  `light` or `switch` (Domain Scope, enforced here specifically). Both
  checks are independent of whichever UI or API caller submitted the
  request.
- **A second, distinct executor policy key: `home_assistant_control_enabled`**,
  not a reuse of RFC-0018's `home_assistant_enabled`. Registered via
  `sovereign_capabilities.Capability`'s existing `policy_key` parameter
  (RFC-0018's own generalization) — enabling Home Assistant *reading*
  must not silently enable Home Assistant *control*, the identical
  principle RFC-0018 already established one level up (enabling
  `web.search` must not silently enable Home Assistant at all).
- **`policy_fields()` (extended)** returns
  `home_assistant_control_enabled` and `home_assistant_controllable_entities`
  alongside RFC-0018's existing three fields, for the executor's
  stage-3 `policy_key` gate and this capability's own `policy_check` to
  read.
- **A second, distinct `policy_check` function — not a literal reuse of
  RFC-0018's `_policy_check`.** RFC-0018's own `_policy_check` validates
  against `home_assistant_allowlist` and raises `ENTITY_NOT_ALLOWLISTED`;
  this capability needs to validate against a *different* policy field
  (`home_assistant_controllable_entities`) and raise a *different* code
  (`ENTITY_NOT_CONTROLLABLE`), so it cannot literally be the same
  function passed to both registrations the way `policy_key` mechanically
  can be a shared default. The only piece genuinely shared between the
  two is the `home_assistant_configured` check (the connection itself
  being reachable/set up is a prerequisite for both reading and
  controlling) — naturally factored into one small helper both
  `policy_check` functions call, rather than duplicated, but that's an
  implementation-level structuring choice, not an architectural one this
  RFC needs to fix. Concretely, `set_entity_state`'s own `policy_check`:
  1. Checks `home_assistant_configured` (shared helper, unchanged from
     RFC-0018).
  2. Checks `entity_id in home_assistant_controllable_entities` — rejects
     with `ENTITY_NOT_CONTROLLABLE` (distinct from RFC-0018's
     `ENTITY_NOT_ALLOWLISTED`, even though the underlying shape of "not on
     the right list" is similar — a household reading the audit log or a
     denied-proposal narration should be able to tell "not readable" apart
     from "readable but not controllable," since they imply different
     next steps).
  3. **Defensively also checks `entity_id in home_assistant_allowlist`**
     (RFC-0018's own read allowlist field) even though `write_config()`
     already enforces `controllable_entities ⊆ allowlisted_entities` at
     write time — a mutating, physical-effect capability's authorization
     path re-verifying an invariant that's supposed to already hold,
     rather than trusting it silently, is proportionate to what this
     capability can actually do if the invariant is ever wrong.
  4. Independently re-derives and checks the entity's domain is
     `light`/`switch` — see Domain Scope's three-point enforcement above.

### Confirmation Disclosure and Receipt

Reuses RFC-0017's `pending_confirmation`/`confirmation` wire format on
`POST /api/v1/conversation/message` completely unchanged — no new fields,
no new halting behavior, the same mechanism RFC-0018 already proved
generalizes to a second capability pair without modification. What this
RFC fixes is what a *client* does with that same generic shape when the
pending capability happens to be mutating:

- `pending_confirmation.arguments` already discloses the literal
  `entity_id`/`state` (RFC-0017's existing "arguments included verbatim
  and unredacted" behavior — no change needed). What changes is
  presentation: a mutating proposal's disclosure copy should name the
  real-world effect, not just the capability — "Turn `light.kitchen`
  **off**? This changes something in your home right now, not just what
  the assistant reads." — distinct from RFC-0018's read-only framing
  ("wants to read your allowlisted Home Assistant entities — this leaves
  your device"), since the risk being disclosed is materially different
  (a physical-world effect vs. data leaving the device). This is UI copy,
  not a wire-format change — Console's confirmation card (already generic
  over capability name/arguments per RFC-0018's own implementation)
  needs a small, capability-name-keyed copy branch, not new state.
- A successful execution's receipt (in Console's chat log, via the same
  `capability_events` array every capability already populates) should
  read as an action completed, not a query answered — e.g. "Turned off
  the kitchen light" rather than a generic "ran." `changed: false`
  (Idempotent No-Ops) narrates distinctly too — "The kitchen light was
  already off" — so a household isn't left wondering whether a no-op
  silently failed.
- Denial and expiry behave identically to RFC-0017/RFC-0018's existing
  handling — a denied or expired mutating proposal is recorded as a
  denial, never retried automatically, the physical world left exactly
  as it was (nothing executes until stage 5, unchanged).

## Interfaces and Data Flow

```text
Model proposes home_assistant.set_entity_state(
    {"entity_id": "light.kitchen", "state": "off"})    [RFC-0004 flow]
    -> RFC-0003 executor stage 2: validate arguments (state in {on, off})
    -> stage 3: check policy_key (home_assistant_control_enabled must be
       true) -> policy_check (home_assistant_configured, entity_id in
       controllable_entities AND in allowlisted_entities, entity_id's own
       domain independently re-derived and confirmed light/switch)
    -> stage 3 fails at any check -> rejection appended to context
       (CAPABILITY_DISABLED or ENTITY_NOT_CONTROLLABLE), no confirmation
       ever generated
    -> stage 3 passes, confirmation required (structural, mutating +
       external) -> confirmation_store.issue() -> round halts,
       pending_confirmation returned [RFC-0017's existing wire format,
       unchanged]
    -> Console discloses the real-world effect and prompts for approval
    -> user approves -> client resubmits with
       {"confirmation": {"token": "...", "approve": true}}
    -> confirmation_store.consume() -> invoke() proceeds through stage 5:
       GET /api/states/light.kitchen (current state) -> already "off"?
       return changed: false without contacting Home Assistant again |
       differs -> re-derive and re-confirm domain is light/switch (third
       independent check, see Domain Scope) -> POST /api/services/light/
       turn_off {"entity_id": "light.kitchen"} -> verify light.kitchen
       appears in the response's changed-states list with the expected
       state -> changed: true
    -> result appended to context as a structured, narratable receipt
```

## Security and Privacy

- **Every** invocation requires per-invocation user confirmation,
  structurally, per RFC-0003's table — no automatic path exists or could
  exist without an RFC-0003 amendment. A prompt-injected model can cause
  a proposal, never an execution — identical framing to every prior
  external/mutating capability this project has shipped.
- Control authorization is strictly narrower than read authorization by
  construction (`controllable_entities ⊆ allowlisted_entities`, enforced
  at write time, not by convention) — a household can never end up able
  to control an entity it hasn't already chosen to let the assistant see.
- Domain restriction is enforced independently at three points (write
  time, policy check, and immediately before the service call itself —
  Domain Scope), not derived once and trusted downstream. This matters
  concretely, not just defensively: `climate.turn_on`/`climate.turn_off`
  are real Home Assistant services, so a `climate.*` entity that ever
  reached service-call construction would not fail safely by accident —
  unlike, say, `lock.*`, which happens to use different service names
  entirely. A raw, hand-crafted API call attempting to add a `lock.*` or
  `climate.*` entity to `controllable_entities` is rejected at write
  time; even a hypothetical bypass of that check is still caught before
  any request reaches Home Assistant.
- The two independent policy toggles (`home_assistant_enabled` for
  reading, `home_assistant_control_enabled` for acting) mean a household
  that wants Sovereign to answer "what's the temperature" without ever
  being able to act on anything can configure exactly that — read-only
  access was never a stepping-stone to control access by default.
- Audit events follow RFC-0003 unchanged: the fact of invocation,
  classification, outcome, and stage reached — never the entity's
  before/after state values, which (unlike Pi-hole's aggregate stats or a
  search query) directly describes real, currently-observable conditions
  inside the household's home. Recording "an action on `light.kitchen`
  was proposed and executed" is the operationally useful fact; recording
  "the kitchen light was on, now off, at 22:14" is real-time household
  activity data this project's existing audit-log discipline (RFC-0003,
  reaffirmed by RFC-0006/RFC-0017/RFC-0018) already declines to persist
  for less sensitive capabilities than this one.
- This is the first capability whose *execution* has a real, physical,
  observable effect on the household, not just an information disclosure.
  RFC-0004's untrusted-forever boundary and RFC-0003's confirmation gate
  both already exist for exactly this reason (RFC-0002's original Safety
  Boundary commitment: "a capability proposal is data, never a command");
  this RFC does not add a new safety mechanism so much as it is the first
  capability where that existing mechanism is actually load-bearing in
  the way it was designed for.

## Failure and Recovery

- Home Assistant unreachable, or the pre-action state read fails: fails
  through RFC-0003's normal bounded-execution path, audited, narrated as
  a failure ("I couldn't reach Home Assistant to check the light") — the
  same posture RFC-0018's own read-only capabilities already take, since
  this capability's first step is itself a read.
- The service call succeeds (HTTP 200) but the response's changed-states
  list doesn't confirm the expected entity/state: reported as
  `HOME_ASSISTANT_ACTION_NOT_CONFIRMED`, a distinct code from a network
  failure — the audit trail and any future debugging can tell "Home
  Assistant accepted the request but didn't confirm the effect" apart
  from "the request never reached Home Assistant at all." Not treated as
  a silent success under any circumstance (see Idempotent No-Ops).
- A read-then-act race (something else changes the entity's state between
  this capability's own state read and its service call) is a disclosed,
  accepted limitation, not one this RFC's design closes — the
  service-call response verification (above) is what actually catches
  the case where the intended effect didn't happen, regardless of why.
- Confirmation token expiry, denial, and a `sovereign-conversation`
  process restart while a confirmation is pending all behave identically
  to RFC-0017/RFC-0018's existing, already-implemented handling — no new
  behavior for this capability to define.

## Compatibility and Migration

No existing Home Assistant action capability to migrate from.
`home-assistant.json`'s two new fields
(`control_enabled`/`controllable_entities`) are additive — an existing
device with RFC-0018's three-field config (from before this RFC) reads
`read_config()`'s new fields as their safe defaults (`false`/`[]`) via
the same fail-safe-to-disabled pattern RFC-0018 already established for
a missing/malformed file, not a schema migration. No change to
`POST /api/v1/conversation/message`'s wire format beyond what RFC-0017
already shipped, verified by the existing confirmation-flow test suite
continuing to pass unmodified. A future domain-expansion RFC can extend
`controllable_entities`' domain check and this capability's `state`
enum (or add sibling capabilities for non-binary actions) without
redesigning the allowlist/policy-toggle relationship this RFC establishes.

## Operations and Observability

- `home-assistant.json`'s `control_enabled`/`controllable_entities`
  (like RFC-0018's own three fields) should be inspectable the same way
  `policy.json` already is — a future Console settings panel reads and
  writes it, not a separate config path.
- The capability audit log records how often `set_entity_state` is
  proposed, approved, denied, or rejected by policy/allowlist, and
  separately how often it resolves as a real state change vs. a no-op —
  useful for judging whether the confirmation flow's friction is
  proportionate for an action capability specifically (a much higher
  denial rate here than for read-only capabilities might indicate the
  disclosure copy isn't landing, or that the allowlist is broader than a
  household actually wants used).

## Testing Strategy

- Contract-level tests mirroring RFC-0018's own pattern: argument
  validation rejects a `state` outside `{"on", "off"}` and a malformed
  `entity_id`, before any allowlist or network concern is reached.
- Allowlist/domain tests: `write_config()` rejects a `controllable_entities`
  entry not present in `allowlisted_entities`; rejects an entry whose
  domain isn't `light`/`switch` even if it *is* in `allowlisted_entities`
  (proving the domain check isn't merely a consequence of the subset
  check); accepts a valid light/switch subset.
- Domain-bypass test, adversarial by design (the concrete finding from
  this RFC's own review): construct a `policy` dict directly (bypassing
  `write_config()` entirely, the same way RFC-0017's own SSRF tests mock
  DNS resolution to bypass the normal request path) with a `climate.*`
  or `lock.*` entity present in `home_assistant_controllable_entities` —
  both `policy_check` and the implementation itself must independently
  reject it, proving domain enforcement does not depend on
  `write_config()` having done its job correctly. Directly verifies the
  `climate.turn_on`/`climate.turn_off` finding above can't reach a real
  service call even if the allowlist itself is somehow wrong.
- Policy-gate tests: `home_assistant_control_enabled: false` (the real
  default) rejects the capability before confirmation, independent of
  `home_assistant_enabled`'s own value — directly verifying enabling
  reading does not enable control, the same structural proof RFC-0018
  required for `web_search_enabled` vs. `home_assistant_enabled`.
- `ENTITY_NOT_CONTROLLABLE` tests: an entity present in
  `allowlisted_entities` but absent from `controllable_entities` is
  rejected at stage 3, distinctly from `ENTITY_NOT_ALLOWLISTED`.
- Idempotency tests: a request matching current state produces
  `changed: false` without any `urlopen` call to the service-call
  endpoint (verified the same way RFC-0018's own tests proved a
  not-configured/not-allowlisted rejection never reaches the network) —
  a request differing from current state produces a real service call
  and `changed: true`.
- Service-call-not-confirmed tests: a mocked Home Assistant response
  (200, but the changed-states list omits or contradicts the target
  entity) produces `HOME_ASSISTANT_ACTION_NOT_CONFIRMED`, not a false
  `changed: true`.
- Confirmation wire-format reuse tests, HTTP-layer, mirroring RFC-0018's
  own: a `required`-confirmation proposal for `set_entity_state` produces
  `pending_confirmation` and no executed result; approval executes
  exactly once (single-use token, unchanged mechanism); denial records a
  denial without ever calling Home Assistant.
- Fixture-backed happy-path tests for the full state-check-then-act
  sequence, without requiring a live Home Assistant instance.
- Real-hardware qualification: named as necessary follow-up, explicitly
  dependent on the same unresolved external dependency RFC-0018 already
  disclosed (a real Home Assistant instance reachable on the household
  network) — this RFC cannot commit to a timeline any more than RFC-0018
  could.

## Alternatives Considered

- **Reuse RFC-0018's single `allowlisted_entities`/`home_assistant_enabled`
  for control too**, rather than a second allowlist and toggle. Rejected:
  collapses two genuinely different consent decisions ("the assistant may
  see this" vs. "the assistant may change this") into one, the exact
  mistake RFC-0018 itself avoided one level up between `web_search_enabled`
  and Home Assistant reading.
- **A generic `call_service(domain, service, entity_id, service_data)`
  capability**, deferring domain/service/argument restriction entirely to
  the allowlist. Rejected outright — see Non-Goals; this is structurally
  the "unrestricted Home Assistant access" the milestone's own Exit
  Criteria already forbids, regardless of how tightly the allowlist
  around it is drawn.
- **A `toggle` action instead of (or alongside) explicit `on`/`off`
  target states.** Rejected: relative actions are harder to reason about
  and disclose clearly in a confirmation prompt, and this capability
  already has to read current state for idempotency, so nothing is
  gained by also supporting a relative form.
- **Include `climate.set_temperature` in this same slice**, since
  thermostats are common and roughly as "everyday" as lights. Considered
  and rejected: a numeric target introduces range-validation and
  equipment-wear considerations this RFC has no household-specific
  evidence to set safely, unlike a binary on/off action — exactly the
  kind of consequential decision this project's RFC process exists to
  make deliberately once real evidence exists, not fold into a RFC whose
  own thesis is "start with the domains that don't need that judgment
  call at all."
- **Skip the pre-action state read and always call the service,
  accepting Home Assistant's own idempotent handling of "turn off an
  already-off light."** Considered, since Home Assistant's own services
  are themselves idempotent (calling `turn_off` on an off light is
  harmless). Rejected because it would make `changed` always `true` (or
  require parsing whether the changed-states list was actually empty to
  infer a no-op after the fact, which is less reliable than knowing
  beforehand) and would generate a real Home Assistant request for every
  proposal regardless of necessity — the state-read-first design gives a
  more honest `changed` value and fewer unnecessary requests, at the cost
  of one extra read call per invocation.

## Drawbacks and Maintenance Cost

- Two independent allowlists (`allowlisted_entities`,
  `controllable_entities`) and two independent policy toggles inside one
  config file is real, ongoing complexity beyond RFC-0018's simpler
  single-allowlist design — justified by genuinely wanting read and
  control to be separately, deliberately opted into, not by convenience.
- The domain restriction (`light`/`switch` only) means this capability
  answers a real but narrow slice of "control my home" — a household
  wanting thermostat or lock control gets nothing from this RFC and has
  to wait for a future domain-expansion RFC, a real, disclosed scope
  limitation, not a hidden one.
- The pre-action state read adds a second Home Assistant round trip to
  every non-no-op invocation (read, then act) — real added latency and
  request volume versus a naive always-call design, accepted for the
  correctness and idempotency benefits (Alternatives Considered).
- This is the first capability whose test suite has to prove a negative
  network property under a *mutating* classification specifically (that
  a no-op or a rejected proposal never reaches Home Assistant) — the same
  discipline RFC-0018's tests already established for reads, now with
  higher stakes if it were ever to regress.

## Unresolved Questions

None of the following block acceptance of the capability and design fixed
above:

- Whether a future domain-expansion RFC should add new capabilities
  (`home_assistant.set_climate_target`, etc.) or extend
  `set_entity_state`'s own domain/state enums — likely capability-specific
  (climate genuinely needs a numeric argument shape this one doesn't),
  but not decided here.
- Whether households will want a coarser "control everything I can
  already read" toggle instead of building `controllable_entities` one
  entity at a time — a Console UX question for the follow-up settings
  page, not an API contract question this RFC needs to resolve.
- Real behavior of the pre-action-state-read-then-act race under genuine
  concurrent use (a household member flips a physical switch mid-request)
  — expected to surface as a normal `HOME_ASSISTANT_ACTION_NOT_CONFIRMED`
  via the response-verification step, but unverified against a real
  instance under real concurrent conditions.
- Whether `max_invocations_per_turn=1` proves too restrictive in practice
  for a household wanting to control several lights in one request (see
  Proposal, Bounds, for why this RFC keeps the existing default rather
  than special-casing it) — needs real usage evidence, not speculation.

## Acceptance Criteria

- `home_assistant.set_entity_state` is registered against RFC-0003's
  contract with the schema above, classified
  `mutating`/`external`/`required`.
- `write_config()` rejects a `controllable_entities` entry not present in
  `allowlisted_entities`, and separately rejects an entry whose domain
  isn't `light`/`switch` even when it is a valid allowlisted entity —
  both verified directly, not merely documented.
- `home_assistant_control_enabled: false` (the real default on a device
  that has never touched this configuration) rejects the capability at
  the policy stage, verified independent of `home_assistant_enabled`'s
  own value.
- A proposal for an entity outside `controllable_entities` is rejected
  with `ENTITY_NOT_CONTROLLABLE` before any confirmation is generated and
  before any Home Assistant request is attempted.
- A `controllable_entities` entry whose domain is not `light`/`switch` is
  rejected at both `policy_check` and inside the implementation itself,
  even when constructed to bypass `write_config()`'s own check entirely
  — verified directly against a `climate.*` entity specifically (this
  RFC's own review finding: `climate.turn_on`/`climate.turn_off` are
  real Home Assistant services, so this domain cannot be assumed to fail
  safely by accident the way an invalid service name might).
- A proposal matching the entity's current state resolves as
  `changed: false` without any request to Home Assistant's service-call
  endpoint — verified directly.
- A proposal differing from current state calls the correct
  `light.turn_on`/`light.turn_off`/`switch.turn_on`/`switch.turn_off`
  service and reports `changed: true` only after verifying the response's
  changed-states list confirms the target entity and state.
- A service-call response that doesn't confirm the expected change
  produces `HOME_ASSISTANT_ACTION_NOT_CONFIRMED`, never a false
  `changed: true`.
- The confirmation pause/resume flow reuses RFC-0017's existing
  `pending_confirmation`/`confirmation` fields with no new wire-format
  code path — verified by extending the existing confirmation test suite
  to a mutating capability rather than writing a parallel mechanism.
- Existing tests (`test_conversation_service.py`, `test_capabilities.py`,
  RFC-0018's own Home Assistant tests) continue to pass unmodified,
  confirming this RFC's additions are additive to the existing turn loop,
  executor, and `home-assistant.json` schema.

Explicitly **not** required for acceptance, named as necessary follow-up
implementation matching this project's precedent of separating proposal
from build-out:

- The capability implementation itself
  (`make_set_entity_state_implementation` or equivalent in
  `sovereign_homeassistant.py`), the extended `write_config()`/
  `policy_fields()`, and the extended `POST /api/v1/conversation/home-assistant`
  request validation.
- Console's settings UI for the control toggle and the
  controllable-entities picker (naturally filtered to light/switch
  entities already on the read allowlist), and the confirmation-card
  copy branch for mutating proposals described in Proposal.
- Real-hardware qualification — dependent on a real Home Assistant
  instance being available on the project's household network, per
  Testing Strategy's disclosed schedule risk, unresolved since RFC-0018.

## Decision

**Accepted (2026-08-21, project creator, reviewed by Claude at the
project creator's direction).** The `home_assistant.set_entity_state`
mapping, its `light`/`switch`-only domain scope, the two-allowlist/
two-toggle authorization design, and the idempotent-no-op behavior are
accepted as this milestone's platform contract for its first mutating
capability.

This review found one substantive, safety-relevant gap and fixed it
before acceptance rather than after: the original draft claimed domain
scope was "enforced at three independent points" but only actually
specified one (config write) — the other two were asserted, not
designed. Checking whether that mattered in practice (not just in
principle) found that it does: Home Assistant's `climate` domain has
real `climate.turn_on`/`climate.turn_off` services, so a non-light/switch
entity that ever reached this capability's service-call construction
step — through a write-time validation bug, direct config-file
corruption, or a future code change — would not have failed safely by
accident the way an invalid service name might have. The design now
requires two additional, independent domain re-checks (at the executor's
`policy_check` stage and immediately before the service-call URL is
built), a defensive `entity_id in allowlisted_entities` re-check
alongside the `controllable_entities` check, and a corrected internal
cross-reference (Idempotent No-Ops pointed at Domain Scope with the wrong
direction — "below" where it needed "above"). None of this changes the
capability's external contract; all of it is now spelled out precisely
enough that Testing Strategy and Acceptance Criteria can actually hold
the implementation to it, rather than trusting a single validation layer
to never have a bug.

The Unresolved Questions above are accepted as non-blocking follow-ups,
matching this project's standing precedent for RFC Unresolved Questions
sections.
