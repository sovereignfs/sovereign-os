# ADR-0004: Provider-Neutral Assistant and Web Search

**Status:** Accepted

**Date:** 2026-07-22

**Decision owner:** Project creator

**Related milestone:** [Milestone 01.2](../roadmap/01-2-local-conversation-capabilities.md)

## Context

Sovereign OS needs local conversation, capability orchestration, current web
information, and later home automation. Ollama, llama.cpp, Open WebUI, and
SearXNG can provide useful parts of that system, but making any third-party
product the Sovereign contract would couple identity, data, updates, permissions,
or user experience to an implementation that may change.

Self-hosting an inference runner keeps prompts local. Self-hosting a metasearch
service has a different privacy boundary: SearXNG still submits queries to its
configured upstream engines and result pages remain external content.

## Decision

- Sovereign owns a normalized inference-provider contract and the model
  manifest, verification, storage, activation, and rollback lifecycle.
- llama.cpp and Ollama will be benchmarked behind that contract on the target
  Raspberry Pi. The initial runner and model will be recorded separately after
  evidence is available.
- Sovereign owns the product conversation interface. Open WebUI may be an
  optional development/evaluation service but is not the product shell.
- Models may only propose registered capability calls. A deterministic Sovereign
  executor validates and authorizes every call.
- SearXNG is the initial replaceable provider for `web.search`.
- `web.search` and constrained `web.fetch` are separate capabilities. The model
  receives no generic network tool.
- Web search is explicitly enabled or approved, visibly communicates the query
  and external boundary, and must not silently incorporate private household
  context.

## Consequences

### Positive

- The runner, model, search provider, and development UI remain replaceable.
- Sovereign can enforce one privacy and capability policy across local and
  optional remote providers.
- Model artifacts can participate in signed releases and reproducible updates.
- Search citations and external communication can be represented directly in
  the product experience.
- Home Assistant and future integrations can reuse the same executor instead of
  granting the model direct service access.

### Negative

- Sovereign must implement adapters, model lifecycle, and a minimal conversation
  interface instead of delegating those product responsibilities to Ollama or
  Open WebUI.
- Model/tool compatibility requires a maintained evaluation corpus.
- SearXNG requires operation and upstream-engine maintenance and cannot promise
  that search queries stay local.
- A constrained fetcher requires SSRF, content-size, timeout, redirect, and
  prompt-injection controls.

## Required Follow-up

- Define the inference and model-manifest contracts in an RFC.
- Benchmark llama.cpp and Ollama on the Raspberry Pi 5.
- Define capability schemas, authorization, confirmation, and auditing.
- Document SearXNG deployment, upstream configuration, retention, and failure
  behavior.
- Update the data inventory and threat model before processing real
  conversations or external content.
- Record the selected runner and initial model in a later ADR.

## Rejected Alternatives

### Make Ollama the product API

Ollama is useful operationally but its API and model lifecycle would become a
platform dependency rather than a replaceable implementation.

### Use Open WebUI as the Sovereign interface

This would accelerate a demo but duplicate or displace Sovereign identity,
permission, capability, citation, and privacy responsibilities.

### Use a hosted search API by default

It would introduce a mandatory third-party processor for user queries and
conflict with the local-first default.

### Give the model general outbound HTTP access

This would make authorization, private-context control, SSRF protection, and
auditability substantially weaker than explicit typed capabilities.
