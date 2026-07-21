# Milestone 01.2 - Local Conversation and Capabilities

**Status:** Planned

**Priority:** After the appliance update foundation; research and RFC work may proceed in parallel

**Depends on:** A qualified Phase 01 image and a stable appliance update boundary

**Target:** Raspberry Pi 5 with 16 GB RAM

## 1. Objective

Deliver the smallest complete Sovereign assistant experience: a user asks a
question in a Sovereign-owned local interface, a local model may propose a
registered capability call, the platform validates and executes it, and the
user receives a grounded response.

The milestone proves the conversation and capability architecture. It does not
attempt to ship a general agent, a full plugin marketplace, or the final
dashboard.

## 2. User Promise

```text
Open Sovereign locally
    -> ask a supported question
    -> see whether processing is local or uses the internet
    -> review capability activity and sources
    -> receive a grounded answer
```

Initial questions cover Sovereign health, read-only Pi-hole information, and
queries that explicitly require web search.

## 3. Architectural Commitments

- Sovereign owns the conversation API, user experience, capability policy, and
  model catalog.
- Inference is accessed through a provider-neutral adapter. No product contract
  depends directly on Ollama, llama.cpp, or an external model API.
- Model output is untrusted. It may propose a capability invocation but cannot
  execute shell commands, contact arbitrary services, or bypass validation.
- The deterministic executor validates capability name, schema, permission,
  side-effect classification, timeout, and result limits.
- Local inference is the default path. Remote inference is a later explicit and
  replaceable option, not a dependency.
- Web search is opt-in per request and visibly leaves the device through the
  configured search engines.
- SearXNG is the initial `web.search` provider and runs locally. Its local
  deployment does not make upstream search-engine requests private from those
  engines; the interface and documentation must explain that boundary.

## 4. Functional Components

### Conversation Service

- Accept and stream local conversations.
- Construct bounded model context.
- Expose model, runner, and degraded-state information.
- Store no conversation longer than the documented retention policy.
- Return citations and capability results as structured data rather than
  embedding them only in generated prose.

### Inference Provider Boundary

The initial contract must support:

- chat or text generation;
- streamed tokens;
- structured JSON output;
- capability or tool-call proposals;
- cancellation, timeout, and health status; and
- model identity and runtime metadata.

Embeddings are intentionally optional until a retrieval use case requires them.

### Sovereign Model Management

Sovereign, not the selected runner, owns:

- model identity and compatibility metadata;
- source, license, digest, size, quantization, and chat template;
- download or offline import and checksum verification;
- activation, rollback, health, and storage lifecycle; and
- persistent storage beneath `/data/sovereign/models/`.

### Capability Registry and Executor

- Register typed, versioned capabilities.
- Distinguish read-only and mutating operations.
- Validate model-proposed arguments independently.
- Apply bounded output, network, and execution-time policies.
- Produce privacy-safe audit events.
- Require user confirmation for sensitive actions when mutating capabilities
  are introduced.

### Initial Capabilities

- `system.health`
- read-only Pi-hole health and summary capabilities
- `web.search`, backed by SearXNG
- `web.fetch`, restricted by URL and content safety policy

Home Assistant follows in a subsequent vertical slice: read-only entity/status
capabilities first, then allowlisted actions with explicit confirmation.

### Minimal Sovereign Conversation Interface

- Responsive local chat.
- Streaming responses and clear failure states.
- Local/remote and offline status.
- Search-in-progress state and linked citations.
- Capability proposal, execution, and result state.
- Model/runner health.
- Conversation deletion.

Open WebUI may be packaged as an optional development and evaluation tool. It is
not the product interface or an authority for Sovereign identity, permissions,
capabilities, or conversation policy.

## 5. Runner Evaluation

The first benchmark compares llama.cpp and Ollama behind the same provider
contract on the target Raspberry Pi. llama.cpp is the preferred production
candidate because it offers a lean ARM64 runtime, direct GGUF control, and an
OpenAI-compatible server. Ollama remains a supported candidate because it
simplifies model acquisition and development workflows.

The decision must use measurements rather than integration convenience alone:

- time to first token and generation rate;
- peak and steady-state memory;
- startup and model-load time;
- CPU temperature, throttling, and sustained operation;
- structured-output and capability-selection accuracy;
- cancellation and crash recovery;
- storage overhead and reproducibility; and
- impact on Pi-hole DNS latency while inference is active.

The benchmark records the exact model, GGUF digest, quantization, context size,
runtime version, parameters, cooling arrangement, and power mode.

## 6. Web Search and Privacy

SearXNG provides aggregation and a stable local API; it does not provide a local
copy of the web. Search terms are still sent to configured upstream engines, and
opening a result contacts its publisher.

The initial policy is therefore:

- search only when the user requests it or the user approves a proposed search;
- show the exact query before or while it is sent;
- identify that external engines will receive it;
- do not silently mix private household context into search queries;
- strip capability secrets and unnecessary identifiers;
- return source URLs and distinguish fetched evidence from model knowledge; and
- support disabling web search entirely.

## 7. Non-Scope

- Voice input or speech output
- Autonomous background agents
- Arbitrary shell or unrestricted HTTP tools
- Mutating Pi-hole operations
- Home Assistant control in the first slice
- General plugin installation
- Multi-user collaboration
- Public internet exposure
- Mandatory remote inference or search service
- Full document retrieval or RAG platform
- Open WebUI as the Sovereign product shell

## 8. Required Documents and Evidence

Before implementation crosses each boundary, prepare and approve:

1. Runtime and conversation architecture RFC.
2. Capability contract and invocation RFCs.
3. Pi-hole capability mapping.
4. SearXNG deployment and `web.search` privacy design.
5. Raspberry Pi inference benchmark report.
6. Minimal conversation experience design brief.
7. Conversation, search, and model data-inventory update.
8. Threat-model update covering prompt injection and external content.

## 9. Delivery Sequence

1. Freeze the provider-neutral inference and model-manifest contracts.
2. Build the reproducible runner/model benchmark harness.
3. Select and package the initial local runner and model.
4. Implement conversation streaming without capabilities.
5. Implement the registry and deterministic executor.
6. Add read-only system and Pi-hole capabilities.
7. Package SearXNG and add `web.search` plus restricted `web.fetch`.
8. Add citations, privacy indicators, audit events, and failure states.
9. Qualify the vertical slice on real Raspberry Pi hardware.

## 10. Exit Criteria

- A fresh supported device can install the milestone through the appliance
  update path without reflashing persistent storage.
- The assistant operates locally when the internet is unavailable for supported
  offline questions.
- At least three Pi-hole/system questions invoke the correct read-only
  capability reliably against a versioned evaluation corpus.
- Unsupported, malformed, and prompt-injected capability proposals fail safely.
- Web search is disabled by default or explicitly enabled during onboarding,
  clearly signals external communication, and returns inspectable citations.
- No model output can directly invoke shell, Docker, Pi-hole, Home Assistant, or
  unrestricted network access.
- Inference does not violate the defined Pi-hole DNS latency and thermal budgets.
- Conversations, search queries, capability events, and model artifacts follow
  documented storage, retention, deletion, and backup rules.
- The selected runner can be replaced without changing the conversation or
  capability contracts.

## 11. Following Vertical Slice

After this milestone is stable, introduce Home Assistant through the same
capability executor:

1. discover and read allowlisted entities;
2. answer state and history questions;
3. propose allowlisted actions;
4. require confirmation according to risk; and
5. preserve deterministic authorization outside the model.

Voice remains later. It should consume the same conversation API rather than
creating a separate assistant architecture.
