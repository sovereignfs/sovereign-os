# System Overview

**Status:** Draft  
**Version:** 0.1  
**Scope:** Long-term platform direction; not the active Phase 01 image architecture

> The active Phase 01 architecture is defined by [ADR-0001](../adrs/0001-phase-01-appliance-architecture.md) and [RFC-0010](../rfcs/0010-raspberry-pi-image-deployment.md). Phase 01 does not implement the platform components described below.

## Purpose

Sovereign Home OS is a local application platform that presents independently managed home services through a coherent user experience. AI is one interface to this platform, not a privileged replacement for platform controls.

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
    +--> capability registry and executor
                 |
                 v
          Pi-hole adapter
                 |
                 v
          Pi-hole v6 API
```

The preview may package some boundaries together in one process. Logical boundaries should still be explicit so they can be tested and separated later if evidence requires it.

## Components

### Web Interface

Provides onboarding, dashboard, chat, status, and minimum settings. It must render clear degraded states and must not contain Pi-hole credentials or provider secrets.

### Local API

Accepts requests from the web interface, enforces the preview access-control model, validates inputs, and returns structured results. Public internet access is outside preview scope.

### Core Runtime

Owns startup, configuration, health, structured logging, error handling, and coordination between platform components. The runtime should remain small during the preview.

### AI Orchestration

Converts a user request into a proposal to invoke a registered capability. The model can select only capabilities provided in its current tool context. Model output is untrusted and must be validated before execution.

### Capability Registry and Executor

Maintains named operations and their typed contracts. It validates capability identity, input, permissions, side-effect classification, timeout, and output independently of the model.

### Pi-hole Adapter

Maps Pi-hole API operations into stable platform capabilities and error types. Preview operations are read-only and use the least privilege available from the supported Pi-hole API.

### AI Provider

Supplies language-model inference. It may be local or explicitly configured as remote; that decision is unresolved. Provider choice must not change capability safety boundaries.

## Request Flow

1. The local user submits a question.
2. The API creates a bounded orchestration request containing only relevant capability descriptions.
3. The model either proposes a registered capability invocation or produces a non-tool response.
4. The executor treats the proposal as untrusted data.
5. The executor validates name, schema, permissions, limits, and preview side-effect policy.
6. The Pi-hole adapter invokes an allowlisted API operation.
7. The adapter returns typed data or a typed error.
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
    | package and lifecycle boundary (future)
Plugins
```

- The browser is not trusted merely because it is on the local network.
- Model output is always untrusted.
- Pi-hole data may reveal household browsing patterns and is sensitive.
- Plugins will eventually be less trusted than the core platform; the preview must avoid designing implicit unlimited plugin authority.

## Data Categories

- Platform configuration
- Authentication or preview access-control data
- Pi-hole connection secret
- Optional AI-provider secret
- Conversation content
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
- No unsupported operation represented as successful.
- No mandatory telemetry.

## Current Unknowns

- Runtime language and web framework
- Process and package boundaries
- Native versus container deployment
- AI-provider default and model abstraction
- Authentication mechanism
- Capability schema format and naming convention
- Configuration and secret storage
- Data directory layout
- Local hostname mechanism
- Pi-hole API compatibility boundary
- Log and diagnostic retention

These unknowns should be resolved through research, RFC review, experiments, and ADRs rather than silently in implementation.
