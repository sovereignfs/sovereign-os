# Product Terminology

**Status:** Draft  
**Version:** 0.1

## Sovereign Home OS

The complete independent product: a local-first platform that provides a coherent interface, AI orchestration, permissions, capabilities, and lifecycle management around user-owned services.

It is not dependent on the separate Sovereign project, even when both projects share development practices or organizational ownership.

## Core Platform

The trusted services responsible for configuration, identity, permissions, capability registration, plugin lifecycle, secrets, diagnostics, and other platform-wide concerns.

## AI Orchestration

The bounded process that interprets a user request, selects from registered capabilities, validates proposed inputs, invokes allowed operations, and presents results. It is not unrestricted agency over the host.

## Capability

A named, typed operation exposed to platform clients and AI orchestration. A capability defines inputs, outputs, permissions, side effects, errors, and a human-readable purpose. Example: `dns.stats.read`.

## Capability Provider

A component that implements one or more capabilities. Multiple providers may eventually implement the same capability contract.

## Plugin

An independently managed package that integrates a domain or service with the platform. A plugin declares its capabilities, permissions, configuration, health, and lifecycle metadata.

## Integration

The connection between Sovereign Home OS and an external or separately managed service. During the preview, the Pi-hole integration may be built into the monorepo before a general plugin lifecycle exists.

## Adapter

Implementation code that translates a service-specific API into platform capability inputs, outputs, and errors.

## Local-First

Core useful behavior runs on user-owned hardware and remains available without an internet connection wherever reasonably possible. Optional remote services must be explicit and replaceable.

## Privacy-First

The system minimizes collection, storage, and transmission by default. Privacy is a design constraint, not a paid feature.

## Preview

The first constrained proof on the project's target Raspberry Pi. It validates a complete experience but is not a production-ready public release.

## Voice Satellite

A future lightweight endpoint for audio capture, playback, mute controls, and status indication. Reasoning and service integrations remain centralized on the home server.

## Supported

Continuously tested, documented, and included within stated compatibility and support boundaries. Merely being technically possible does not make a configuration supported.

## Local Network

The household network from which a user accesses the platform. It reduces exposure but is not automatically considered fully trusted.

