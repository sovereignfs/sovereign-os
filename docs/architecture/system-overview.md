# System Overview

**Status:** Draft  
**Version:** 0.1  
**Scope:** Long-term platform direction and Milestone 01.2 boundaries; not the active Phase 01 image architecture

> The active Phase 01 architecture is defined by [ADR-0001](../adrs/0001-phase-01-appliance-architecture.md) and [RFC-0010](../rfcs/0010-raspberry-pi-image-deployment.md). Phase 01 does not implement the platform components described below.

## Purpose

Sovereign OS is a local application platform that presents independently managed home services through a coherent user experience. AI is one interface to this platform, not a privileged replacement for platform controls.

This document records known system boundaries and constraints. Exact technology, process, packaging, and protocol decisions require research and RFC approval.

## Preview Context

```text
Local browser
    |
    v
Web interface and local API
    |
    v
Core runtime
    +--> health and configuration
    +--> AI orchestration
    +--> inference provider adapter --> local model runner
    +--> capability registry and executor
                 +--> Pi-hole adapter --> Pi-hole v6 API
                 +--> web.search --> local SearXNG --> upstream engines
                 +--> web.fetch --> allowlisted external page
```

The preview may package some boundaries together in one process. Logical boundaries should still be explicit so they can be tested and separated later if evidence requires it.

## Components

### Web Interface

Provides onboarding, dashboard, chat, status, and minimum settings. It must render clear degraded states and must not contain Pi-hole credentials or provider secrets.

The first implementation is Sovereign Console at `/console/`. It is a
dependency-free read-only health interface backed by `/api/v1/health`. Service
interfaces such as Pi-hole remain independently namespaced.

### Local API

Accepts requests from the web interface, enforces the preview access-control model, validates inputs, and returns structured results. Public internet access is outside preview scope.

The initial health service binds only to loopback, runs without root or Docker
socket access, and reads bounded system interfaces plus appliance readiness
records. Nginx exposes only its versioned health resource to the LAN.

### Core Runtime

Owns startup, configuration, health, structured logging, error handling, and coordination between platform components. The runtime should remain small during the preview.

### AI Orchestration

Converts a user request into a proposal to invoke a registered capability. The model can select only capabilities provided in its current tool context. Model output is untrusted and must be validated before execution.

### Capability Registry and Executor

Maintains named operations and their typed contracts. It validates capability identity, input, permissions, side-effect classification, timeout, and output independently of the model.

### Pi-hole Adapter

Maps Pi-hole API operations into stable platform capabilities and error types. Preview operations are read-only and use the least privilege available from the supported Pi-hole API.

### AI Provider

Supplies language-model inference through a provider-neutral contract owned by
Sovereign. The initial direction is local inference, with llama.cpp and Ollama
benchmarked behind the same adapter. Provider choice must not change
conversation, model-management, or capability safety boundaries. The runner API
binds only to a private host/container interface and is not a LAN API.

### Model Manager

Owns model manifests, license/source metadata, digest verification, import,
activation, compatibility, and storage under persistent Sovereign data. A
runner-specific model catalog is an implementation convenience, not the source
of product truth.

### Web Search Adapter

Maps the stable `web.search` capability to a locally operated SearXNG service.
SearXNG is a replaceable provider, not a capability contract. Search queries
still travel to configured upstream engines, so external communication must be
explicit and private household context must not be silently added to queries.

Fetched pages are handled by a separate constrained `web.fetch` capability.
Search does not grant the model general network access.

## Request Flow

1. The local user submits a question.
2. The API creates a bounded orchestration request containing only relevant capability descriptions.
3. The model either proposes a registered capability invocation or produces a non-tool response.
4. The executor treats the proposal as untrusted data.
5. The executor validates name, schema, permissions, limits, and preview side-effect policy.
6. The selected adapter invokes an allowlisted service operation.
7. The adapter returns bounded typed data, citations, or a typed error.
8. The system produces a user-facing explanation grounded in that result.
9. Diagnostics record the event without credentials or sensitive DNS details by default.

## Trust Boundaries

```text
User/browser
    | authenticated or preview-controlled boundary
Core platform
    | untrusted model-output boundary
AI provider

Core platform
    | credential and service API boundary
Pi-hole

Core platform
    | external-query and untrusted-content boundary
SearXNG, upstream search engines, and fetched websites

Core platform
    | package and lifecycle boundary (future)
Plugins
```

- The browser is not trusted merely because it is on the local network.
- Model output is always untrusted.
- Pi-hole data may reveal household browsing patterns and is sensitive.
- Search terms and fetched content cross an explicit external trust boundary;
  self-hosting SearXNG does not eliminate upstream disclosure.
- Plugins will eventually be less trusted than the core platform; the preview must avoid designing implicit unlimited plugin authority.

## Data Categories

- Platform configuration
- Authentication or preview access-control data
- Pi-hole connection secret
- Optional AI-provider secret
- Conversation content
- Search queries, result URLs, and fetched excerpts
- Model artifacts, licenses, manifests, and activation state
- Capability request and result metadata
- Pi-hole statistics and client identifiers
- Logs, metrics, and diagnostic data

Handling details belong in the [data inventory](../security/data-inventory.md).

## Preview Constraints

- No arbitrary shell execution.
- No direct Pi-hole database manipulation.
- No Pi-hole write operations.
- No public binding or remote access by default.
- No secrets in source control, browser payloads, or normal logs.
- No model call bypassing the capability executor.
- No model runner exposed directly to the LAN.
- No general network tool presented to the model.
- No unsupported operation represented as successful.
- No mandatory telemetry.

## Current Unknowns

- Runtime language and web framework
- Process and package boundaries
- Native versus container deployment
- Initial local runner and model, pending Raspberry Pi benchmark
- Authentication mechanism
- Capability schema format and naming convention
- Configuration and secret storage
- Data directory layout
- Local hostname mechanism
- Pi-hole API compatibility boundary
- Log and diagnostic retention
- Search-provider configuration, safe-fetch policy, and query retention

These unknowns should be resolved through research, RFC review, experiments, and ADRs rather than silently in implementation.
