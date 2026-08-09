# RFC-0002: Local Conversation and Inference Runtime Architecture

**Status:** Draft
**Author:** Project creator and Claude
**Created:** 2026-08-09
**Reviewers:**
**Target phase:** [Milestone 01.2, Local Conversation and Capabilities](../roadmap/01-2-local-conversation-capabilities.md)
**Supersedes:** None

## Summary

Define the architecture for Sovereign's own local conversation experience
and the provider-neutral inference boundary underneath it: what the
Conversation Service owns, the contract every model runner must speak
through, and how Sovereign manages model artifacts independently of
whichever runner is active. This RFC does not define the capability
registry, the AI capability invocation schema, or any specific
capability (those are RFC-0003, RFC-0004, and RFC-0006, reserved in
[docs/rfcs/README.md](README.md) for this same milestone) — it defines
the runtime those capabilities will be proposed and executed through.

## Problem

Milestone 2 (Production Update Operations) is now complete: the appliance
update boundary — signed manifests, health-gated activation, rollback,
persistent-data backup/restore, retention, and trust rotation — is
implemented and hardware-qualified (see
[RFC-0014](0014-appliance-update-system.md), Accepted). Milestone 4
(Local Conversation and Capabilities) depends on exactly that stable
boundary and is otherwise unblocked, but nothing in this milestone has an
approved architecture yet. Direction research exists
([docs/research/local-ai-options.md](../research/local-ai-options.md))
and the milestone plan
([docs/roadmap/01-2-local-conversation-capabilities.md](../roadmap/01-2-local-conversation-capabilities.md))
names eight required documents before implementation may cross each
boundary; this RFC is the first of those.

Without a defined boundary now, an implementation would naturally couple
itself to whichever runner (llama.cpp, Ollama) is easiest to integrate
first, the way `docs/research/local-ai-options.md` already warns against.
That coupling would be expensive to undo later: model management,
capability-call parsing, and conversation persistence would all need to
assume one runner's idioms instead of a contract Sovereign controls.

## Goals

- Define what the Conversation Service is responsible for, independent of
  any runner or model.
- Define the inference provider contract every runner (local or, later,
  remote) must implement, so the runner is a replaceable implementation
  detail rather than an architectural dependency.
- Define what Sovereign's own model management owns versus what it
  delegates to the runner.
- Define the resource, privacy, and safety boundaries inference must
  respect on the Raspberry Pi 5 target, including coexistence with
  Pi-hole's DNS-latency requirements.
- Establish the runner-selection method (benchmark criteria and pass/fail
  budgets) without prejudging the result before real hardware
  measurement.

## Non-Goals

- The capability registry, executor, or any specific capability's schema
  (RFC-0003, RFC-0004).
- Pi-hole capability mapping specifics (RFC-0006).
- The `web.search`/`web.fetch` privacy design in full detail (named as a
  required document in the milestone plan, tracked separately, though
  the architectural boundary — inference has no generic outbound network
  access — is established here).
- The actual runner/model selection. That is an ADR made after a real
  Raspberry Pi 5 benchmark, not a decision this RFC can make on paper.
- Voice input/output, autonomous background agents, multi-user
  collaboration, or a general plugin marketplace — all explicitly out of
  scope for the whole milestone per the milestone plan's Non-Scope
  section.
- Remote/hosted inference as anything but a later, explicitly configured,
  replaceable option. Local inference is the only default path this RFC
  designs for.

## Context and Evidence

- [docs/research/local-ai-options.md](../research/local-ai-options.md)
  (Direction selected; hardware benchmark pending) already establishes
  that Sovereign must own a provider-neutral inference boundary and
  model lifecycle, names llama.cpp as the preferred benchmark candidate
  and Ollama as the comparison candidate, and specifies the benchmark
  method (time-to-first-token, memory, thermal, structured-output
  accuracy, DNS-latency impact) this RFC's runner-evaluation section
  reuses rather than re-deriving.
- [docs/roadmap/01-2-local-conversation-capabilities.md](../roadmap/01-2-local-conversation-capabilities.md)
  is the accepted milestone plan; its Architectural Commitments,
  Functional Components, and Exit Criteria sections are the direct
  source for this RFC's Proposal section. Where this RFC repeats
  language from that plan, it is making the plan's commitments
  RFC-concrete rather than introducing new scope.
- Every appliance-update RFC and ADR to date (RFC-0014, RFC-0015,
  RFC-0016, ADR-0006, ADR-0011) establishes the pattern this RFC
  follows: a signed, versioned, health-gated boundary that treats the
  underlying mechanism (runner, in this case) as replaceable. The
  inference provider contract below is deliberately shaped the same
  way appliance releases and base-OS releases are — a stable interface
  the platform depends on, with a swappable implementation behind it.
- This project has exactly one physical qualification device (a
  Raspberry Pi 5) and one maintainer. Nothing here proposes
  infrastructure (a model registry service, GPU offload, multi-tenant
  serving) that this project's actual scale would not use.

## Proposal

### Conversation Service

Sovereign owns the conversation API, user experience, capability policy,
and model catalog — never delegated to a runner or a third-party UI
(Open WebUI is explicitly a development/evaluation tool only, per the
milestone plan; it is not the product interface and is not authoritative
for identity, permissions, capabilities, or conversation policy).

The Conversation Service is responsible for:

- accepting and streaming local conversations over Sovereign's own API,
  loopback-scoped the same way `sovereign-console-auth` is
  ([ADR-0007](0007-console-authentication.md) — the equivalent auth
  boundary should be reused, not redesigned, once this RFC is
  implemented);
- constructing bounded model context (message history, capability
  results, and any retrieved evidence), with an explicit, documented
  bound rather than an unbounded context window;
- exposing model, runner, and degraded-state information to the client
  (which model, which runner, healthy or degraded, local or would-be
  remote) so the interface can honestly represent what answered the
  question;
- returning citations and capability results as structured data
  alongside generated prose, not embedded only in free text a client
  would have to re-parse; and
- storing no conversation beyond a documented retention policy (the
  policy itself is deferred to the data-inventory update named in the
  milestone plan's required-documents list, not fixed by this RFC).

### Inference Provider Boundary

Every runner — local now, remote later if ever added — implements the
same contract. No component outside the provider adapter itself may
depend on a specific runner's API shape. The contract must support:

- chat/text generation, given bounded context;
- streamed token output;
- structured JSON output;
- capability/tool-call proposals, returned as structured data the
  executor (RFC-0003/0004) validates independently — the provider
  boundary's job is to surface a proposal, never to execute one;
- cancellation and timeout, with a bounded worst-case resource hold; and
- health status and model/runtime identity (model digest, quantization,
  runtime version), so a response can always be attributed to exactly
  what produced it.

Embeddings are intentionally excluded from the initial contract, per the
milestone plan, until a retrieval use case actually requires them —
adding an unused capability now would be speculative.

The provider boundary must not expose an inference HTTP port to the LAN.
Local inference is the default and only path this RFC designs an
implementation for; remote inference is named only as a future,
explicitly configured option so today's contract doesn't foreclose it
without committing any engineering effort to it now.

### Sovereign Model Management

Sovereign — not the runner — owns model identity and lifecycle,
independent of which runner is active. This mirrors the same ownership
principle the appliance updater already applies to appliance releases:
the mechanism executing an artifact does not get to define the artifact's
trust or lifecycle rules. Concretely, Sovereign owns:

- model identity and compatibility metadata (which runner(s) a given
  model artifact is valid for);
- source, license, digest, size, quantization, and chat-template
  metadata;
- download or offline import with checksum verification before a model
  is ever loaded;
- activation, rollback, health, and storage lifecycle; and
- persistent storage beneath `/data/sovereign/models/` — inside the same
  persistent-data boundary the backup/restore contract in
  [BACKUP_AND_JOURNAL.md](../../update/BACKUP_AND_JOURNAL.md) already
  protects, though model artifacts are large, replaceable-by-redownload
  data and a later decision may reasonably exclude them from the backup
  archive roles that document defines — that inclusion/exclusion
  decision is left to the data-inventory update, not fixed here.

### Runner Evaluation

This RFC does not select a runner. It commits to the evaluation method
`local-ai-options.md` already specifies: llama.cpp and Ollama run behind
the same provider contract on the actual Raspberry Pi 5 qualification
device, measuring time-to-first-token, generation rate, peak/steady
memory, load time, thermal behavior under sustained load, structured-
output and capability-selection accuracy, cancellation/crash recovery,
storage overhead, and — critically for this device, which also serves
DNS — Pi-hole DNS latency and failure rate with and without active
inference. A runner passes only inside explicit resource and DNS budgets
recorded at benchmark time; convenience is not a selection criterion by
itself. The result is recorded in an ADR after real measurement, per
`local-ai-options.md`'s own Follow-up Decisions — this RFC only commits
to the method existing and being followed.

### Safety Boundary

Model output — generated text and any proposed capability call — is
always untrusted. This RFC establishes the boundary the provider adapter
and Conversation Service must respect regardless of which capability
system (RFC-0003/0004) eventually validates a proposal in detail:

- the runner process has no shell access, no Docker socket access, no
  service credentials, and no unrestricted network access;
- a capability proposal from a model is data, never a command — nothing
  in the Conversation Service or provider adapter executes a proposal
  itself; only the (separately specified) deterministic executor does,
  after independent schema and permission validation; and
- inference must not degrade Pi-hole DNS responsiveness beyond the
  budget the runner-evaluation benchmark records — if a runner cannot
  stay inside that budget under realistic load, it fails qualification
  regardless of model quality.

## Interfaces and Data Flow

```text
Client (Sovereign conversation UI)
    <-> Conversation Service (auth, context construction, streaming,
         retention, structured citations/capability results)
            <-> Inference Provider Adapter (contract defined above;
                 implementation is the selected runner, behind this
                 boundary only)
            <-> Capability Executor (RFC-0003/0004; validates and
                 executes proposals the model surfaced as data, never
                 trusted or auto-executed)
Sovereign Model Management (identity, lifecycle, storage) is consulted
by the Conversation Service when selecting/activating a model, and by
the Inference Provider Adapter when loading one — it is not on the
per-request conversation path.
```

No component upstream of the Inference Provider Adapter ever depends on
a runner-specific API shape. No component downstream of a capability
proposal treats that proposal as anything but unvalidated input.

## Security and Privacy

- The Conversation Service's HTTP surface is loopback-only, matching the
  existing Console-auth precedent (ADR-0007) rather than introducing a
  second, differently-shaped local auth boundary.
- The inference provider's HTTP port (if the selected runner exposes
  one, as `llama-server` does) is never exposed to the LAN — only
  reachable from the Conversation Service itself.
- Model artifacts are verified by digest before load, the same
  supply-chain posture the appliance updater already applies to release
  bundles and Pi-hole images.
- Conversation content, capability-call arguments, and any retrieved
  evidence are household data. Their retention/deletion policy is
  deferred to the data-inventory update the milestone plan names, but
  this RFC establishes that no such data crosses the provider boundary
  to a remote service unless a future, explicit remote-inference option
  is configured — which is out of scope for this RFC's implementation.

## Failure and Recovery

- Provider timeout or crash must surface as a clear degraded state to
  the Conversation Service and the client, never as a silent hang or a
  fabricated answer. The contract's cancellation/timeout requirement
  exists specifically so a stuck runner cannot hold resources
  indefinitely on a single-device appliance.
- A capability proposal the executor rejects (malformed, unsupported, or
  failing permission/schema checks) must fail safely and visibly — the
  Conversation Service surfaces the rejection to the user rather than
  retrying it as a different, unvalidated action.
- Model activation failures (checksum mismatch, incompatible runner)
  must not take down an already-working model; the previous activated
  model stays active, mirroring the appliance updater's own
  stage-before-activate discipline.

## Compatibility and Migration

There is no existing conversation or inference surface to migrate from —
this is new functionality. The only compatibility constraint is the one
Milestone 4 already inherits: implementation must ship through the
existing appliance update path (RFC-0014) without requiring a reflash,
per the milestone's Exit Criteria.

## Operations and Observability

- Model/runner health and identity must be inspectable the same way
  `sovereign-update status` already exposes appliance/base-OS state —
  an operator (or the Console) should be able to see which model and
  runner are active and whether they are healthy without reading logs.
- Capability proposals and executions produce privacy-safe audit events
  (detailed schema deferred to RFC-0003/0004), consistent with how
  trust rotations and update transactions are already both journaled
  and kept free of secrets/PII in their audit trails.

## Testing Strategy

- Contract-level tests for the Inference Provider Adapter interface
  (streaming, structured output, cancellation, timeout, health
  reporting) that do not depend on a specific runner being installed —
  the same way the appliance updater's manifest/signature validation is
  tested independent of any specific release payload.
- A reproducible benchmark harness (per `local-ai-options.md`'s
  Benchmark Method) that records exact hardware, cooling, power mode,
  runtime version, and model digest — required before any runner
  selection ADR, and re-runnable if hardware or runtime versions change.
- Real Raspberry Pi 5 hardware qualification of the selected runner
  under the DNS-latency and thermal budgets this RFC requires, following
  this project's standing practice of a dated report under
  `docs/research/` for every real hardware pass.

## Alternatives Considered

- **Adopt Open WebUI (or a similar existing chat UI) as the product
  interface.** Rejected: its user, conversation, tool, and
  administration concerns overlap with responsibilities Sovereign must
  control itself (privacy indicators, capability confirmation, household
  identity) — per `local-ai-options.md`'s own comparison table. It
  remains available as an optional development/evaluation tool, not the
  architecture.
- **Couple directly to one runner (e.g., ship only an Ollama
  integration) to move faster.** Rejected for the same reason RFC-0014
  didn't couple appliance updates to `apt`/`docker pull latest`: it
  would be fast now and expensive to unwind once model management,
  capability parsing, and conversation persistence all assumed one
  runner's idioms.
- **Skip the benchmark and pick llama.cpp outright, since it's already
  the stated preference.** Rejected: `local-ai-options.md` is explicit
  that convenience or stated preference is not a selection criterion by
  itself — the runner must actually pass Pi-hole DNS-latency and thermal
  budgets on the real device, measured, not assumed.

## Drawbacks and Maintenance Cost

- A provider-neutral boundary is more work than integrating one runner
  directly, and Sovereign now owns model lifecycle logic a runner like
  Ollama would otherwise provide for free. This is an explicit,
  accepted tradeoff — see Alternatives Considered — not an oversight.
- This RFC adds a new persistent-data category (`/data/sovereign/models/`)
  whose backup/retention treatment is not yet decided, and adds a new
  local network-facing service (the Conversation API) whose auth
  boundary must be kept in sync with Console auth's as both evolve.

## Unresolved Questions

- Conversation and capability-event retention policy (deferred to the
  data-inventory update named in the milestone plan).
- Whether model artifacts under `/data/sovereign/models/` are included
  in the existing backup roles or treated as separately excluded,
  re-downloadable data.
- Exact resource/thermal/DNS-latency budget numbers — this RFC commits
  to the evaluation method, not the numbers, which only real hardware
  measurement can produce.
- Whether the Conversation Service's auth reuses `sovereign-console-auth`
  directly or is a structurally identical but separate service —
  implementation-level, but affects the Interfaces section above.
- Exact provider-adapter interface shape (request/response schema) is
  intentionally left to implementation once a runner is selected,
  rather than specified here against an unselected runner's real
  capabilities.

## Acceptance Criteria

- The Inference Provider Adapter contract (chat/generation, streaming,
  structured output, capability proposals, cancellation/timeout, health
  and identity reporting) is implemented and covered by contract-level
  tests independent of any specific runner.
- Sovereign model management (manifest, digest verification, activation,
  rollback, storage under `/data/sovereign/models/`) is implemented.
- A reproducible benchmark harness has run llama.cpp and Ollama on the
  real Raspberry Pi 5 qualification device and recorded results against
  explicit resource and DNS-latency budgets.
- A runner/model selection ADR exists, informed by that benchmark, not
  by convenience.
- The Conversation Service streams a real conversation end-to-end on
  real hardware without degrading Pi-hole DNS latency beyond the
  recorded budget.
- No component outside the Inference Provider Adapter depends on a
  runner-specific API shape, verified by the adapter being swappable
  without changing the Conversation Service or capability executor.

## Decision

Pending review. This RFC establishes the runtime and conversation
architecture; implementation and hardware qualification against the
Acceptance Criteria above follow once accepted, per this project's
standing practice of accepting an RFC's direction before implementation
races ahead of it (a lesson [RFC-0014](0014-appliance-update-system.md)'s
own history illustrates directly).
