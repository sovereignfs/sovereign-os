# Core Use Cases

**Status:** Draft  
**Version:** 0.1  
**Phase:** Deferred AI-enabled preview; not Phase 01

> These use cases remain valid for the later AI and capability milestone. Phase 01 is now limited to the [flashable Pi-hole image POC](../roadmap/01-preview-poc.md).

## UC-01: Check Pi-hole Health

**User intent:** Determine whether DNS filtering is operating normally.  
**Successful outcome:** The system reports what it can verify about Pi-hole connectivity and health, with a timestamp and clear limits.  
**Failure behavior:** Distinguish Pi-hole unavailable, authentication failed, incompatible API, and Sovereign Home OS integration failure.  
**Permissions:** Read-only Pi-hole health access.  
**Internet dependency:** None when Pi-hole and the selected AI path are local; otherwise only the AI response generation may require internet.

## UC-02: Review Blocked Request Count

**User intent:** Understand how many DNS requests Pi-hole blocked during the relevant reporting period.  
**Successful outcome:** Return the count, the reporting period, and enough context to avoid misleading interpretation.  
**Failure behavior:** Never fabricate a count; explain unavailable or incomplete data.  
**Permissions:** Read-only Pi-hole statistics access.  
**Privacy:** Avoid persisting detailed query history merely to answer the question.

## UC-03: Identify High-Volume Clients

**User intent:** See which local clients generate the most DNS traffic.  
**Successful outcome:** Return a bounded, ranked summary with the time period and naming limitations.  
**Failure behavior:** Explain when client identity is unavailable or ambiguous.  
**Permissions:** Read-only Pi-hole statistics access.  
**Privacy:** Client identifiers are sensitive household metadata and should not appear in ordinary logs.

## UC-04: Explain a Blocked Domain

**Status:** Preview stretch goal.  
**User intent:** Understand whether and why a domain is blocked.  
**Successful outcome:** Report the observed blocking state and the responsible list or rule when the API can establish it.  
**Failure behavior:** Separate “not observed,” “not blocked,” and “cannot determine.”  
**Permissions:** Read-only Pi-hole query and list inspection.  
**Safety:** The preview must not automatically allowlist the domain.

## UC-05: Check Sovereign Home OS Health

**User intent:** Determine whether the local platform and its required dependencies are operating.  
**Successful outcome:** Show core runtime, AI provider, Pi-hole integration, and relevant resource status.  
**Failure behavior:** Preserve dashboard access where possible and identify the failed dependency.  
**Permissions:** Read-only platform diagnostics.

## UC-06: Handle an Unsupported Request

**User intent:** Ask something outside the preview's capability set.  
**Successful outcome:** Explain that the action is unsupported, avoid pretending it occurred, and identify supported alternatives where helpful.  
**Safety:** The AI must not improvise shell commands, generic network requests, or unregistered tool calls.

## Evaluation Rules

Every use case should be tested for:

- successful response;
- unavailable dependency;
- invalid or incomplete input;
- unauthorized access;
- malformed model-generated tool call;
- timeout;
- privacy-safe logging;
- understandable user-facing explanation.
