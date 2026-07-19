# Specification-Driven Development Workflow

**Status:** Draft  
**Version:** 0.1

## Purpose

Sovereign Home OS is human-directed and AI-assisted. AI agents can research, propose, implement, review, test, and document work, but the project owner remains responsible for product direction, risk acceptance, and approval of major decisions.

## Planning Chain

```text
Concept
  -> master plan
  -> phase plan
  -> research or experiment
  -> RFC
  -> decision/ADR
  -> implementation plan
  -> issue
  -> code and tests
  -> release
  -> retrospective
```

Not every change requires every document. Every change requires enough context to be independently reviewed and tested.

## Roles

### Project Owner

- Sets product priorities and scope.
- Approves phase plans and major RFCs.
- Accepts security, privacy, maintenance, and business tradeoffs.
- Decides when evidence is sufficient.

### Researcher

- States the question and evaluation criteria before investigating.
- Distinguishes evidence from inference.
- Records sources, environment, limitations, and unanswered questions.
- Does not present a recommendation as an accepted decision.

### Architect

- Converts needs and evidence into proposals.
- Defines boundaries, alternatives, tradeoffs, security, and migration effects.
- Keeps proposals consistent with the concept and active phase.

### Implementer

- Works from an approved proposal or sufficiently bounded task.
- Records assumptions rather than silently changing scope.
- Adds tests, error handling, and documentation with behavior.

### Reviewer

- Checks correctness, scope, architecture, security, privacy, operability, and maintainability.
- Verifies claims against code and tests rather than trusting generated summaries.

### Tester

- Verifies success, failure, recovery, resource, and real-hardware behavior.
- Records commands, environment, results, and unresolved defects.

One person or agent may perform several roles, but architect/implementer output should receive an independent review pass.

## Choosing the Right Document

- **Research note:** What is true or feasible?
- **Experiment:** Does a measurable hypothesis hold in a specified environment?
- **RFC:** What should the project build or standardize?
- **ADR:** What important choice was accepted, and why?
- **Design brief:** What user experience should be produced?
- **Implementation plan:** How will an accepted, bounded change be delivered?

## Work Item Readiness

Implementation may begin when:

- the problem and user outcome are clear;
- scope and non-scope are explicit;
- acceptance criteria are testable;
- dependencies and affected boundaries are known;
- required decisions are accepted;
- security and privacy implications are considered;
- unresolved questions do not make the implementation direction ambiguous;
- the work can be reviewed independently.

## AI Agent Context

Every implementation request should provide or link:

- the active phase plan;
- relevant product use cases and terminology;
- accepted RFCs and ADRs;
- affected architecture documents;
- security and data-handling constraints;
- acceptance criteria and required verification;
- files or components in scope;
- explicit non-scope.

Agents must label assumptions, preserve unrelated work, and avoid making hidden product or architecture decisions inside code.

## Change Workflow

1. Define the problem and success criteria.
2. Decide whether research, an experiment, design work, or an RFC is needed.
3. Review and accept the necessary decision.
4. Write a bounded implementation plan.
5. Implement the smallest complete vertical slice.
6. Run proportionate automated and manual verification.
7. Review security, privacy, documentation, and operational effects.
8. Update current-state architecture and user/operations documentation.
9. Record remaining limitations and follow-up work.

## Definition of Done

Applicable completion requirements must be selected before implementation. They may include:

- implementation and migrations;
- unit, contract, integration, end-to-end, and hardware tests;
- negative and failure-path tests;
- documentation and examples;
- security and privacy review;
- configuration and deployment changes;
- diagnostics and monitoring;
- backup, restore, update, and removal behavior;
- release notes and demonstration;
- retrospective or recorded follow-up work.

Code existing is not, by itself, completion.

## Document Review and Lifecycle

1. Author marks a document Draft.
2. Author resolves major unknowns and marks it Proposed.
3. Project owner accepts, rejects, or requests changes.
4. Accepted technical decisions may receive an ADR.
5. Implementation status is tracked separately from proposal acceptance.
6. Replacement documents link both directions and mark earlier work Superseded.
7. Historical reasoning is preserved rather than rewritten to make decisions appear inevitable.

