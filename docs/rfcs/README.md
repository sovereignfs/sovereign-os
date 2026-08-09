# RFC Index

RFCs are proposals, not decisions. Start with the [RFC template](../templates/rfc.md), use zero-padded sequential identifiers, and do not mark an RFC Accepted without project-owner approval.

## Initial Preview Backlog

- RFC-0001: Monorepo structure
- [RFC-0002: Local conversation and inference runtime architecture](0002-local-conversation-and-inference-runtime.md) - Draft
- RFC-0003: Capability contract
- RFC-0004: AI capability invocation
- [RFC-0010: Raspberry Pi image deployment](0010-raspberry-pi-image-deployment.md) - Proposed
- RFC-0006: Pi-hole integration
- [RFC-0014: Appliance update system](0014-appliance-update-system.md) - Implemented
- [RFC-0015: Update discovery - channel metadata and device-side checking](0015-update-discovery.md) - Accepted
- [RFC-0016: Full base-OS updates (A/B root filesystem)](0016-full-base-os-updates.md) - Accepted

RFC-0001 and RFC-0003/RFC-0004/RFC-0006 refer to the later platform and AI
capability work; RFC-0002 is now written (see above). The Phase 01 image
foundation and appliance/base-OS update boundary are both complete, so this
work is now unblocked. Later proposals for authentication, configuration,
logging, backup, general plugin lifecycle, and voice should be created only
when their problem and evidence are mature enough for a concrete proposal.

RFC-0002 through RFC-0004 and RFC-0006 are the proposal set required for
[Milestone 01.2](../roadmap/01-2-local-conversation-capabilities.md).
RFC-0002 (runtime and conversation architecture) is drafted; RFC-0003
(capability contract), RFC-0004 (AI capability invocation), and RFC-0006
(Pi-hole capability mapping) remain to be written. Implementation must
preserve the accepted appliance and update boundaries.
