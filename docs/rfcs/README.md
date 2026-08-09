# RFC Index

RFCs are proposals, not decisions. Start with the [RFC template](../templates/rfc.md), use zero-padded sequential identifiers, and do not mark an RFC Accepted without project-owner approval.

## Initial Preview Backlog

- RFC-0001: Monorepo structure
- [RFC-0002: Local conversation and inference runtime architecture](0002-local-conversation-and-inference-runtime.md) - Accepted
- [RFC-0003: Capability contract](0003-capability-contract.md) - Draft
- [RFC-0004: AI capability invocation](0004-ai-capability-invocation.md) - Draft
- [RFC-0010: Raspberry Pi image deployment](0010-raspberry-pi-image-deployment.md) - Proposed
- [RFC-0006: Pi-hole capability mapping](0006-pihole-capability-mapping.md) - Draft
- [RFC-0014: Appliance update system](0014-appliance-update-system.md) - Implemented
- [RFC-0015: Update discovery - channel metadata and device-side checking](0015-update-discovery.md) - Accepted
- [RFC-0016: Full base-OS updates (A/B root filesystem)](0016-full-base-os-updates.md) - Accepted

RFC-0001 refers to earlier platform work and remains unwritten; create it
only when its problem and evidence are mature enough for a concrete
proposal. Later proposals for authentication, configuration, logging,
backup, general plugin lifecycle, and voice follow the same rule.

RFC-0002 through RFC-0004 and RFC-0006 are the proposal set required for
[Milestone 01.2](../roadmap/01-2-local-conversation-capabilities.md), and
all four are now written. RFC-0002 (runtime and conversation
architecture) is Accepted; RFC-0003 (capability contract), RFC-0004 (AI
capability invocation), and RFC-0006 (Pi-hole capability mapping) are
drafted and pending review. Implementation must preserve the accepted
appliance and update boundaries, and per RFC-0006, still depends on
completing [docs/research/pihole-api-assessment.md](../research/pihole-api-assessment.md)'s
empirical investigation against the real pinned Pi-hole version before
the Pi-hole capabilities can be implemented.
