# Deployment Model Comparison

**Status:** Planned

## Question

Should the preview use native system services, containers, or a hybrid deployment on Raspberry Pi OS?

## Alternatives

- Native packages and system services
- Containerized application components
- Hybrid model with selected host services

## Evaluation Criteria

- Installation and removal simplicity
- ARM64 compatibility
- Resource and storage overhead
- Startup ordering and supervision
- Networking and Pi-hole coexistence
- Secret and data handling
- Updates, rollback, backup, and recovery
- Debugging and support burden
- Reproducibility for AI-assisted development
- Path from preview to public distribution

## Required Output

A comparison backed by a minimal prototype where documentation alone cannot settle the tradeoff. The conclusion should recommend one primary preview method without implying that every technically possible method is supported.

## Decision Informed

Runtime architecture and Raspberry Pi deployment RFCs.

