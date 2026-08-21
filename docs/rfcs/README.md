# RFC Index

RFCs are proposals, not decisions. Start with the [RFC template](../templates/rfc.md), use zero-padded sequential identifiers, and do not mark an RFC Accepted without project-owner approval.

## Initial Preview Backlog

- RFC-0001: Monorepo structure
- [RFC-0002: Local conversation and inference runtime architecture](0002-local-conversation-and-inference-runtime.md) - Accepted
- [RFC-0003: Capability contract](0003-capability-contract.md) - Accepted
- [RFC-0004: AI capability invocation](0004-ai-capability-invocation.md) - Accepted
- [RFC-0010: Raspberry Pi image deployment](0010-raspberry-pi-image-deployment.md) - Proposed
- [RFC-0006: Pi-hole capability mapping](0006-pihole-capability-mapping.md) - Accepted
- [RFC-0014: Appliance update system](0014-appliance-update-system.md) - Implemented
- [RFC-0015: Update discovery - channel metadata and device-side checking](0015-update-discovery.md) - Accepted
- [RFC-0016: Full base-OS updates (A/B root filesystem)](0016-full-base-os-updates.md) - Accepted
- [RFC-0017: web.search and web.fetch capability mapping](0017-web-search-and-fetch-capability-mapping.md) - Accepted
- [RFC-0018: Home Assistant read-only capability mapping](0018-home-assistant-read-only-capability-mapping.md) - Accepted

RFC-0001 refers to earlier platform work and remains unwritten; create it
only when its problem and evidence are mature enough for a concrete
proposal. Later proposals for authentication, configuration, logging,
backup, general plugin lifecycle, and voice follow the same rule.

RFC-0002 through RFC-0004 and RFC-0006 are the proposal set required for
[Milestone 01.2](../roadmap/01-2-local-conversation-capabilities.md), and
all four are now Accepted (2026-08-09, project creator). Implementation
must preserve the accepted appliance and update boundaries.
[docs/research/pihole-api-assessment.md](../research/pihole-api-assessment.md)'s
empirical investigation against the real pinned Pi-hole version,
RFC-0006's remaining prerequisite, concluded 2026-08-09 with a real,
live-verified authenticated round trip on the qualification device.
Implementation begins next.

RFC-0017 is the milestone's remaining required document (`web.search`
privacy design), drafted 2026-08-21 against
[docs/research/searxng-deployment-assessment.md](../research/searxng-deployment-assessment.md)
and the confirmation-flow/policy-state gaps already visible in
`sovereign_conversation.py`. Implemented and hardware-qualified before
formal review (this project's own precedent), then reviewed and accepted
2026-08-21 — the review found and fixed one real piece of drift (a
resolved Unresolved Question that was still marked open) rather than
re-approving the text unchanged.

RFC-0018 is Milestone 5's first document (Home Assistant read-only entity/
history capability mapping), drafted 2026-08-21 against RFC-0017's
already-shipped confirmation wire format and Home Assistant's own REST API
documentation, and accepted the same day after review found and fixed a
stage-numbering inconsistency and a disclosed, non-blocking TLS gap.
Implementation (capability, executor generalization, and Console settings
UI) shipped the same day, real-hardware qualification blocked on no Home
Assistant instance existing on the household network yet.
