# RFC-0003: Capability Contract

**Status:** Accepted (2026-08-09, project creator)
**Author:** Project creator and Claude
**Created:** 2026-08-09
**Reviewers:** Project creator
**Target phase:** [Milestone 01.2, Local Conversation and Capabilities](../roadmap/01-2-local-conversation-capabilities.md)
**Supersedes:** None

## Summary

Define what a "capability" is in Sovereign, how it is registered, and how
the deterministic executor validates and runs one — independent of who or
what is asking. [RFC-0002](0002-local-conversation-and-inference-runtime.md)
(Accepted) already established that a model's capability proposal is
untrusted data the executor validates independently, and named the
executor as a component without specifying it. This RFC specifies it.
RFC-0004 (AI capability invocation, reserved in
[docs/rfcs/README.md](README.md)) then defines the narrower question of
how a model's proposal specifically maps onto the contract this RFC
defines — prompt-side tool-call shaping, disambiguation, and the
model-invocation confirmation flow. RFC-0006 (Pi-hole capability mapping)
defines the specific Pi-hole capabilities' data shape using this
contract. This RFC is the platform primitive all three build on; it does
not itself specify any capability's business logic beyond classifying
the milestone's four named ones.

## Problem

Milestone 01.2's plan
([docs/roadmap/01-2-local-conversation-capabilities.md](../roadmap/01-2-local-conversation-capabilities.md))
names the Capability Registry and Executor as a required functional
component, with explicit requirements (typed/versioned registration,
read-only/mutating distinction, independent argument validation, bounded
output/network/execution-time policy, privacy-safe audit events, and
confirmation for sensitive actions). Nothing yet specifies the schema a
capability is defined with, the validation pipeline an invocation must
pass, or how "mutating" and "external network" are distinguished as
separate risk axes — a capability can be read-only with respect to
Sovereign's own state (`web.search`) while still making real contact
with the outside world, which is not the same risk `system.health`
(read-only, fully local) carries.

Without this contract fixed before RFC-0004 and RFC-0006 are written,
each would have to invent its own validation and audit shape, and a
later capability (Home Assistant, Milestone 5) would either duplicate
that work or retrofit onto whatever RFC-0004/0006 happened to assume.

## Goals

- Define a capability's schema: name, version, typed arguments, typed
  result, side-effect classification, network classification, and
  execution bounds.
- Define the deterministic executor's validation pipeline: the fixed
  sequence every invocation passes through regardless of caller, before
  anything executes.
- Define the confirmation requirement model: which classifications
  require explicit user confirmation before execution, and which may
  execute without it.
- Define the audit event shape produced for every invocation attempt,
  successful or not.
- Classify this milestone's four named capabilities (`system.health`,
  read-only Pi-hole capabilities, `web.search`, `web.fetch`) against this
  contract, without specifying their individual argument/result schemas.
- Establish that capabilities are a fixed, Sovereign-authored registry —
  not a dynamically loadable or user-installable plugin system — matching
  the milestone's explicit non-scope.

## Non-Goals

- How a model proposes a capability call, disambiguates between
  candidates, or is asked to confirm a mutating action — RFC-0004.
- Pi-hole's specific capability arguments, result shape, and which
  Pi-hole data is exposed at all — RFC-0006.
- `web.search`/`web.fetch`'s specific privacy design (query disclosure,
  SearXNG deployment, result-fetch content-safety policy) — named as its
  own required document in the milestone plan, tracked separately; this
  RFC only fixes that both are capabilities with an external-network
  classification.
- Mutating capabilities' actual behavior. None ship in this milestone
  (Pi-hole mutation and Home Assistant control are explicit non-scope);
  this RFC defines the classification and confirmation model mutating
  capabilities will use in Milestone 5, so that milestone doesn't need to
  redesign this contract, but does not introduce any mutating capability
  now.
- A general plugin system, third-party capability installation, or
  runtime capability registration. The registry this RFC defines is
  fixed at build/deploy time, the same way the appliance's file
  allowlist is (see
  [the appliance file-set finding](../research/appliance-file-set-update-ceiling-finding.md)
  for why an unbounded, runtime-extensible allowlist is a real hazard
  this project has already hit once, in a different subsystem).

## Context and Evidence

- [docs/roadmap/01-2-local-conversation-capabilities.md](../roadmap/01-2-local-conversation-capabilities.md),
  "Capability Registry and Executor" and "Initial Capabilities" sections,
  is the direct source for this RFC's requirements and the four
  capabilities classified below.
- [RFC-0002](0002-local-conversation-and-inference-runtime.md)'s Safety
  Boundary section already committed to: a capability proposal is data,
  never a command; only the executor this RFC specifies may execute one;
  and the runner process itself has no shell, Docker, credential, or
  unrestricted network access. This RFC is the concrete mechanism that
  commitment depends on.
- This project's existing deterministic-validation precedent —
  `sovereign-update`'s manifest/signature/trust validation, which
  simulates every operation against current state before applying
  anything and rejects atomically on any failure (see `rotate_trust` in
  the updater, and its
  [real signed-cycle qualification report](../research/rotate-trust-real-signed-cycle-qualification-report.md))
  — is the model this RFC's executor pipeline follows: validate
  everything, execute nothing, until validation fully passes.
- The append-only, non-secret audit log pattern already established for
  trust rotations (`/data/sovereign/update-state/trust-rotations.jsonl`)
  and update transactions (`events.jsonl` per transaction) is reused here
  rather than inventing a new audit shape.

## Proposal

### Capability Definition

A capability is a fixed, Sovereign-authored registry entry with:

- **`name`** — namespaced and dotted, matching the milestone plan's own
  naming (`system.health`, `pihole.*`, `web.search`, `web.fetch`).
- **`version`** — an integer, independent per capability. A breaking
  argument/result schema change is a new version, not a mutation of an
  existing one, so a previously-valid proposal never silently changes
  meaning.
- **`argument_schema`** / **`result_schema`** — typed schemas (JSON
  Schema, matching this project's existing manifest-validation style
  rather than introducing a new schema language) that the executor
  validates independently of whatever produced the arguments.
- **`side_effect`** — `read_only` or `mutating`. Read-only capabilities
  observe Sovereign or external state without changing it. No mutating
  capability is registered in this milestone.
- **`network`** — `local` or `external`. `local` capabilities never leave
  the device. `external` capabilities contact something outside it
  (`web.search`, `web.fetch`) and are classified as such regardless of
  their `side_effect` value — `web.search` is `read_only` *and*
  `external`, and both classifications apply independently, not as a
  single combined risk level.
- **`confirmation`** — `automatic` or `required`, derived from
  `side_effect` and `network` (see Confirmation Model below), not set
  independently per capability, so a capability's author cannot
  accidentally under-classify its own risk.
- **`bounds`** — timeout, maximum result size, and maximum invocations
  per conversation turn. Every capability declares these; there is no
  unbounded default.

### Registry

The registry is a static list compiled into Sovereign, not a directory
scanned at runtime and not installable by a user or a model. This
mirrors the appliance file allowlist's lesson: an open-ended, runtime-
extensible set of executable things is a real hazard this project has
already paid down elsewhere, not a design to repeat here. Adding a
capability is a Sovereign release, reviewed and shipped through the
existing signed appliance-update path — the same trust boundary that
already governs every other executable thing on the device.

### Deterministic Executor

Every invocation — regardless of caller — passes through the same fixed
pipeline before anything runs, mirroring `sovereign-update rotate_trust`'s
validate-fully-before-applying-anything discipline:

1. **Resolve.** The proposed `name`/`version` must match a registered
   capability exactly. An unknown name or version is rejected before any
   other check runs — there is no fuzzy or partial match at this layer.
2. **Validate arguments.** The proposed arguments are validated against
   `argument_schema` independently of the caller's own claims about
   their shape. A capability's implementation never receives arguments
   the schema didn't already accept.
3. **Check policy.** The capability's classification is checked against
   current device policy — e.g., whether `web.search` is enabled at all
   (opt-in, per the milestone plan's web-search policy) — before
   proceeding. A capability disabled by policy is rejected here, not
   silently no-op'd.
4. **Gate on confirmation.** If `confirmation` is `required`, the
   executor does not proceed until an explicit, freshly-obtained user
   confirmation for *this specific proposed invocation* (not a standing
   blanket approval) is present. How that confirmation is solicited from
   a model-proposed call is RFC-0004's concern; this RFC only fixes that
   the executor itself enforces the gate and cannot be bypassed by the
   caller claiming confirmation already happened.
5. **Execute, bounded.** The capability implementation runs under its
   declared `bounds` — timeout, result-size cap, per-turn invocation
   cap — with no ambient access beyond what that specific implementation
   needs (no shared shell, no shared credential store, no network access
   for a `local` capability).
6. **Audit, always.** An audit event is produced whether the invocation
   succeeded, was rejected at any pipeline stage, or timed out. Rejection
   is not a silent non-event.

### Confirmation Model

| `side_effect` | `network` | `confirmation` |
| --- | --- | --- |
| `read_only` | `local` | `automatic` |
| `read_only` | `external` | `required` |
| `mutating` | `local` | `required` |
| `mutating` | `external` | `required` |

Only the fully local, fully read-only combination executes without
per-invocation confirmation. Every combination involving either mutation
or external network contact requires it. This is deliberately
conservative for a single-household appliance with no operator watching
most invocations in real time — matching the milestone plan's web-search
policy ("search only when the user requests it or the user approves a
proposed search") generalized to the whole contract rather than special-
cased to just `web.search`.

### Audit Events

Every invocation produces a structured, append-only, non-secret event
recording: timestamp, capability name/version, `side_effect`/`network`
classification, which pipeline stage it reached (resolved, validated,
policy-checked, confirmed, executed, or rejected-at-`<stage>`), result
size (not result content), and duration. Arguments and results are never
written to the audit log verbatim — household data (a search query, a
Pi-hole domain) is not the same class of information as the fact an
invocation happened, and the existing trust-rotation/update-transaction
logs already establish the precedent of auditing the *event* without
persisting the *sensitive content*.

### Initial Capability Classification

| Capability | `side_effect` | `network` | `confirmation` |
| --- | --- | --- | --- |
| `system.health` | `read_only` | `local` | `automatic` |
| Pi-hole read-only capabilities | `read_only` | `local` | `automatic` |
| `web.search` | `read_only` | `external` | `required` |
| `web.fetch` | `read_only` | `external` | `required` |

All four are read-only with respect to Sovereign's own state, matching
the milestone's non-scope of any mutating capability this pass. `web.search`
and `web.fetch` are classified `external` even though they don't mutate
anything Sovereign controls, because they genuinely leave the device —
the classification tracks where data goes, not just what it changes.

## Interfaces and Data Flow

```text
Caller (Conversation Service, on behalf of a model proposal per RFC-0004,
        or a future direct UI-triggered invocation)
    -> Executor.invoke(name, version, arguments, confirmation_token?)
        1. resolve            (unknown name/version -> rejected)
        2. validate arguments (schema mismatch -> rejected)
        3. check policy       (disabled by policy -> rejected)
        4. gate on confirmation (required and absent -> rejected,
                                  pending-confirmation state returned)
        5. execute, bounded   (timeout/size cap enforced)
        6. audit               (always, regardless of outcome)
    <- result | rejection, plus the audit event's identifier
```

The executor is a standalone component the Conversation Service calls
into — it is not coupled to AI invocation specifically. A future
directly-triggered UI action (a button, not a model proposal) uses the
identical pipeline, which is exactly why this contract is a separate RFC
from RFC-0004 rather than folded into it.

## Security and Privacy

- The registry being fixed at build/deploy time means no invocation can
  ever target a capability that wasn't reviewed and shipped through the
  signed appliance-update path — there is no runtime path to register or
  invoke something arbitrary.
- Argument validation happens against the schema, never against
  whatever the caller (model or otherwise) claims about its own input —
  the same "never trust the caller's own framing" posture
  `validate_release_payload` and `validate_trust_rotation_manifest`
  already apply to update artifacts.
- `external`-classified capabilities are the only ones with real network
  egress, and that classification is structural (a table lookup), not a
  per-invocation judgment call that could be prompt-injected into
  skipping confirmation.
- Audit events are privacy-safe by construction: they record that an
  invocation happened and what pipeline stage it reached, never the
  argument or result content, which may contain household data (search
  terms, Pi-hole domain queries).

## Failure and Recovery

- Rejection at any pipeline stage is a normal, expected, always-audited
  outcome — not an error state requiring recovery. The executor has no
  persistent state to roll back on rejection; nothing executes until
  stage 5.
- A capability implementation that exceeds its declared timeout or
  result-size bound is terminated and reported as a bounded failure, not
  allowed to run to completion outside its declared bounds.
- A confirmation that is requested but never given simply expires the
  pending invocation; it does not retry automatically or escalate.

## Compatibility and Migration

There is no existing capability system to migrate from. The registry's
build-time-fixed nature means adding a capability is an ordinary
appliance release through the existing update path (RFC-0014) — no new
update mechanism is required. A capability version bump is additive: an
older proposal referencing an old version either still resolves (if the
implementation kept it) or is rejected at the resolve stage exactly like
an unknown capability, never silently reinterpreted under the new
version's schema.

## Operations and Observability

- The audit log is the operational record of what capabilities have been
  invoked, how often, and how many were rejected at which stage — useful
  both for the device operator and for evaluating whether a model is
  proposing well-formed capability calls (relevant to RFC-0004's
  structured-output accuracy requirements).
- Policy state (which `external` capabilities are enabled) should be
  inspectable the same way update/trust-rotation state already is,
  rather than requiring a log search to determine current configuration.

## Testing Strategy

- Contract-level tests for the executor pipeline itself — resolution,
  schema validation, policy gating, confirmation gating, bounded
  execution, and audit emission — using fixture capabilities, so the
  pipeline is proven correct independent of any real capability's
  business logic.
- Adversarial-input tests: malformed arguments, arguments that validate
  against the schema but are semantically nonsensical, requests for
  unknown names/versions, and confirmation-bypass attempts, all of which
  must be rejected at the correct pipeline stage and audited.
- Once `system.health` and the Pi-hole read-only capabilities exist
  (RFC-0006), real-hardware qualification that the full pipeline runs
  correctly against real device state, following this project's standing
  practice of a dated report under `docs/research/` for real hardware
  passes.

## Alternatives Considered

- **Let each capability define its own confirmation requirement.**
  Rejected: this makes under-classification a per-capability author
  mistake instead of a structural property of the classification table,
  and this project's own history (the appliance file-allowlist gap) is
  a direct example of what happens when a boundary is enforced by
  scattered judgment calls instead of one central table.
- **A dynamically loadable/pluggable capability system**, closer to a
  general extension model. Rejected per the milestone's explicit
  non-scope (no general plugin installation) and this project's
  standing preference against infrastructure this single-device,
  single-maintainer project's actual scale doesn't need.
- **Audit full argument/result content for debuggability.** Rejected:
  household data (search queries, Pi-hole domains) doesn't belong in a
  durable log by default, mirroring why update/trust-rotation audit logs
  already exclude manifest contents and DNS queries.

## Drawbacks and Maintenance Cost

- A build-time-fixed registry means adding a capability always requires
  a full appliance release cycle, not a lightweight runtime registration
  — an intentional tradeoff (see Alternatives Considered), but real
  friction if capabilities need to iterate quickly during development.
- The confirmation model's default conservatism (everything but fully
  local read-only requires confirmation) may prove too aggressive in
  practice for read-only external capabilities used often
  (`web.search`); loosening it later is a contract change, not a policy
  toggle, since confirmation is derived structurally rather than
  configured per capability.

## Unresolved Questions

None of the following block acceptance of the contract below; each is
either implementation-level or explicitly deferred to RFC-0004/0006.

- Exact JSON Schema dialect and validation library — implementation
  detail, not an architectural question.
- Where policy state (which `external` capabilities are enabled) is
  stored and how it's changed — likely alongside existing device
  configuration, but not fixed here.
- Whether confirmation tokens are single-use, time-bounded, or both —
  left to RFC-0004, since it depends on how a model-proposed
  confirmation flow actually surfaces to the user.
- The exact mutating-capability confirmation UX (beyond "required") is
  deferred to Milestone 5, when a mutating capability first actually
  ships.

## Acceptance Criteria

- The capability schema (name, version, argument/result schema,
  `side_effect`, `network`, `confirmation`, `bounds`) is implemented as
  the registration format every capability uses.
- The six-stage executor pipeline (resolve, validate, policy-check,
  confirm, execute-bounded, audit) is implemented and covered by
  contract-level tests independent of any specific capability.
- The Confirmation Model table is enforced structurally — no code path
  allows a capability to declare its own `confirmation` value
  independent of its `side_effect`/`network` classification.
- Audit events are produced for every invocation outcome, verified to
  never contain argument or result content, only classification and
  outcome metadata.
- `system.health`, the Pi-hole read-only capabilities, `web.search`, and
  `web.fetch` are each registered against this contract with the
  classification this RFC assigns them.
- Adversarial-input tests (malformed arguments, unknown name/version,
  confirmation bypass attempts) are rejected at the correct pipeline
  stage, not merely rejected somewhere.

## Decision

**Accepted (2026-08-09, project creator).** The capability schema, the
six-stage executor pipeline, the structural confirmation model, and the
audit event shape are accepted as the platform contract RFC-0004 and
RFC-0006 build on. The Unresolved Questions above are non-blocking
follow-ups, not gating conditions.
