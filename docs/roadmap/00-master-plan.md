# Sovereign OS

## Master Plan

**Status:** Draft  
**Version:** 0.1  
**Purpose:** Internal planning source for the public project roadmap  
**Primary target:** Raspberry Pi 5, 16 GB  
**Project model:** Independent monorepo  
**Development model:** Human-directed, AI-assisted, specification-driven development

---

# 1. Purpose of This Document

This document defines the complete plan for turning the Sovereign OS concept into a working, sustainable product.

It is broader than a software roadmap.

It includes every major area of work required to make the project real:

- Product definition
- Engineering
- System architecture
- User experience
- Research
- Hardware validation
- Security
- Documentation
- Release infrastructure
- Community
- Governance
- Business sustainability

The root `ROADMAP.md` should remain a concise index of the project's current direction, phases, and progress.

This document is the detailed planning source from which that public roadmap is derived.

---

# 2. Planning Principles

## 2.1 Build for One Real User First

The first user is the project creator.

The earliest versions should solve real problems in a real home rather than attempt to satisfy an imagined mass market.

The first success criterion is not public adoption.

It is:

> Sovereign OS is useful enough to remain installed and actively used on the Raspberry Pi.

---

## 2.2 Build Complete Vertical Slices

The project should avoid building many disconnected foundations without delivering a usable experience.

Each major milestone should create a complete flow:

```text
User action
    ↓
Interface
    ↓
Core platform
    ↓
Capability
    ↓
Plugin or service
    ↓
Useful result
```

A small complete feature is more valuable than a large collection of unfinished components.

---

## 2.3 Validate Before Generalizing

The initial implementation may support only one:

- Hardware target
- User
- Plugin
- AI provider
- Installation method
- Interface

Generalization should happen after the real constraints are understood.

---

## 2.4 Document Before Implementing Major Systems

Major systems should begin with one of the following:

- Request for Comments
- Research note
- Experiment plan
- Design brief
- Architecture Decision Record
- Implementation plan

AI agents should implement approved specifications rather than loosely defined ideas.

---

## 2.5 Maintain Independence From Other Projects

Sovereign OS may share:

- Development practices
- Documentation patterns
- AI workflows
- Design principles
- Lessons learned

with other projects maintained by the same creator.

It must not require another project to:

- Build
- Install
- Run
- Update
- Authenticate
- Distribute
- Recover
- Operate

From an external perspective, Sovereign OS is an independent product with its own:

- Repository
- Brand
- Website
- Documentation
- Release pipeline
- Packages
- Infrastructure
- Community
- Roadmap

---

## 2.6 Prefer Reversible Decisions

During the preview stage, the project should prefer decisions that are easy to change.

Premature commitments to:

- Complex distributed systems
- Custom hardware
- Proprietary protocols
- Multi-repository structures
- Public APIs
- Marketplace contracts

should be avoided until there is evidence that they are necessary.

---

## 2.7 Protect the Core Principles

Every roadmap item should be evaluated against the project's core principles:

- User ownership
- Privacy first
- Local first
- AI as an interface
- Open ecosystem
- Modularity
- Simplicity

Features that violate these principles should be rejected or redesigned.

---

# 3. Planning Hierarchy

The project uses the following planning structure:

```text
Concept Paper
    ↓
Master Plan
    ↓
Public Roadmap
    ↓
Phase Documents
    ↓
RFCs, Research Notes, Experiments and Design Briefs
    ↓
Implementation Plans
    ↓
Issues
    ↓
Pull Requests
    ↓
Releases
    ↓
Retrospectives
```

## Concept Paper

Explains:

- Why the project exists
- What problem it solves
- Its principles
- Its long-term vision
- Its non-goals

## Master Plan

Defines all major actionable work required to realize the concept.

## Public Roadmap

Provides a concise view of:

- Current phase
- Upcoming phases
- Major deliverables
- Overall progress

## Phase Documents

Describe:

- Objectives
- Deliverables
- Workstreams
- Dependencies
- Risks
- Exit criteria

## Supporting Documents

Different tasks require different document types.

### RFC

Used for proposed architecture, interfaces, protocols, and major technical systems.

### ADR

Records an important architectural decision and the reasoning behind it.

### Research Note

Summarizes investigation into technologies, standards, products, or approaches.

### Experiment

Defines a hypothesis, method, measurements, and outcome.

### Design Brief

Defines the user problem, experience, constraints, and expected design outcome.

### Implementation Plan

Converts an approved proposal into concrete engineering tasks.

---

# 4. Roadmap Overview

The proposed development path consists of eight phases. Two bounded milestones
bridge the appliance proof and the broader core-platform phase so the project
continues delivering complete vertical slices.

```text
Phase 00 — Project Foundation
Phase 01 — Flashable Pi-hole Image POC
Milestone 01.0 — Sovereign Console Foundation
Milestone 01.1 — Appliance Update Foundation
Milestone 01.2 — Local Conversation and Capabilities
Phase 02 — Core Platform
Phase 03 — Personal Daily Driver
Phase 04 — Voice Interface
Phase 05 — Plugin Ecosystem
Phase 06 — Public Preview
Phase 07 — Version 1.0
```

The phases are sequential at the objective level, but some workstreams may overlap.

The project should not advance to a new phase merely because development has begun on it.

A phase is complete only when its exit criteria are met.

---

# 5. Phase 00 — Project Foundation

## Objective

Create a clear, disciplined, AI-friendly project environment before substantial implementation begins.

## Desired Outcome

The project has:

- A clear purpose
- A coherent repository
- Defined planning practices
- Document templates
- Basic automation
- An initial technical direction
- A controlled scope for the preview

## Product Work

- Finalize the concept paper.
- Define the initial target user.
- Define the first real household use cases.
- Define project terminology.
- Define the project's relationship to existing self-hosted ecosystems.
- Establish explicit non-goals.
- Define the preview experience.
- Create and maintain an idea icebox.

## Repository Work

- Create the monorepo.
- Add the root `README.md`.
- Add the concept paper.
- Add the root `ROADMAP.md`.
- Add this master plan.
- Establish the initial directory structure.
- Add contribution and conduct documents when public participation begins.
- Define code ownership conventions even if there is only one maintainer.

## Planning and Documentation Work

Create templates for:

- Phase documents
- RFCs
- ADRs
- Research notes
- Experiments
- Design briefs
- Implementation plans
- Retrospectives

Define:

- Document naming conventions
- Status values
- Review workflow
- Approval workflow
- Superseding and deprecation rules

## AI Development Workflow

- Create repository-level instructions for AI coding agents.
- Define the human's role as product owner and architect.
- Define agent roles such as:
  - Architect
  - Implementer
  - Reviewer
  - Tester
  - Security reviewer
  - Documentation reviewer
- Create shared project context.
- Establish a single development log.
- Define how agents record assumptions and unresolved questions.
- Define minimum evidence required before an agent marks work complete.
- Require agents to update documentation when behavior changes.

## Engineering Foundations

- Select initial implementation languages.
- Select package and workspace tooling.
- Establish formatting and linting.
- Establish unit and integration test conventions.
- Establish configuration conventions.
- Define environment variable and secret-handling rules.
- Set up basic continuous integration.
- Define versioning conventions.
- Define commit and pull request conventions.

## Architecture Work

Draft initial proposals for:

- System boundaries
- Application runtime
- Core API
- Plugin model
- Capability model
- Configuration model
- Service supervision
- Local networking
- Data directories
- Logging
- Backup expectations

These proposals do not need to be final before the preview.

They must be clear enough to prevent accidental architectural chaos.

## Branding and Communication

- Confirm the working product name.
- Define a temporary visual identity.
- Create a one-sentence product description.
- Create a short project description for GitHub.
- Reserve relevant domains and organization names where appropriate.
- Define whether the earliest repository is public or private.

## Exit Criteria

Phase 00 is complete when:

- The concept paper is approved.
- The master plan is approved.
- The monorepo exists.
- The repository structure is established.
- The preview scope is documented.
- The AI development workflow is usable.
- The initial architecture proposals are sufficient to begin implementation.
- The first implementation plan is ready.

---

# 6. Phase 01 — Raspberry Pi Preview

> **Scope amendment (2026-07-19):** The active Phase 01 has been narrowed to the [Flashable Pi-hole Image POC](01-preview-poc.md). It validates the Raspberry Pi OS Lite image, Docker-based Pi-hole appliance, `/dns/*` routing, first boot, and release pipeline. The dashboard, AI orchestration, and capability integration described in the original phase below are deferred until the image foundation is complete. See [ADR-0001](../adrs/0001-phase-01-appliance-architecture.md).

> **Immediate next priority:** After the POC release, deliver the [Appliance Update Foundation](01-1-update-foundation.md) so installed devices can receive signed Pi-hole and appliance updates without reflashing. Phase 01 must create the dedicated persistent data partition required by that milestone. See [ADR-0002](../adrs/0002-install-images-and-update-artifacts.md).

> **Current bounded slice:** Introduce the [Sovereign Console Foundation](01-console-foundation.md) before update controls or AI features. The local entry point moves to `/console/`; its first page is a read-only health overview backed by `/api/v1/health`. It must remain available when Pi-hole is degraded, expose no secrets or household activity, and perform no privileged or mutating operation. See [ADR-0005](../adrs/0005-sovereign-console-and-health-boundary.md) and the [design brief](../design/console-health.md).

> **Following vertical slice:** After the update boundary is reliable, deliver
> [Local Conversation and Capabilities](01-2-local-conversation-capabilities.md).
> Architecture, privacy design, and Raspberry Pi inference benchmarks may
> proceed in parallel. This slice introduces a Sovereign-owned conversation UI,
> provider-neutral local inference, deterministic capability execution,
> read-only Pi-hole operations, and opt-in SearXNG-backed web search. Home
> Assistant follows through the same capability boundary; voice remains later.

## Objective

Build the smallest compelling version of Sovereign Home OS and install it on a Raspberry Pi 5 with 16 GB of memory.

## Purpose

The preview exists to:

- Prove that the idea can run on real hardware
- Create personal motivation
- Demonstrate the concept to potential collaborators
- Identify architectural mistakes early
- Establish a complete build and installation path
- Produce the first genuinely useful local experience

It is not intended to be:

- Production-ready
- Secure for hostile internet exposure
- Multi-user
- Hardware-independent
- A polished public release
- A complete operating system image
- A general-purpose plugin ecosystem

## Preview Experience

The user should be able to:

1. Prepare a Raspberry Pi.
2. Install the preview using documented steps.
3. Open Sovereign Home OS from another device on the local network.
4. Complete minimal setup.
5. Open the dashboard.
6. Use a chat interface.
7. Ask the assistant a supported question.
8. Have the system invoke one local capability.
9. Receive a useful and understandable response.
10. Inspect basic system health.

## Recommended First Vertical Slice

```text
Browser
    ↓
Sovereign Home dashboard
    ↓
Chat interface
    ↓
Local or configurable AI service
    ↓
Capability invocation
    ↓
Pi-hole integration
    ↓
Structured result
    ↓
Natural-language explanation
```

Example questions:

- Why is this domain blocked?
- Is Pi-hole working?
- How many requests were blocked today?
- Which clients are making the most DNS requests?

## Product Work

- Define the exact preview user journey.
- Define supported commands and questions.
- Define what the preview deliberately does not support.
- Define onboarding copy.
- Define error and unsupported-action messages.
- Define basic privacy disclosures.
- Define a feedback collection method.

## Engineering Work

### Core Runtime

- Create the main backend service.
- Create health endpoints.
- Add configuration loading.
- Add structured logging.
- Add error handling.
- Add process startup and shutdown behavior.

### Dashboard

- Create a responsive local web interface.
- Provide:
  - Home screen
  - Chat screen
  - System status
  - Basic settings
- Show clear states for:
  - Loading
  - Offline services
  - Unsupported requests
  - Failed capability calls
- Own the conversation, citations, privacy indicators, confirmation, and
  capability-result experience within Sovereign. Open WebUI may be used for
  development evaluation but is not the product shell.

### AI Integration

- Establish a provider-neutral inference boundary owned by Sovereign.
- Benchmark llama.cpp and Ollama on the Raspberry Pi 5 and select one initial
  local runner/model pair using resource, latency, reliability, and structured
  capability-call evidence.
- Keep remote providers explicit, optional, and replaceable.
- Keep model manifests, verification, activation, and storage independent of
  the selected runner.
- Implement tool or capability invocation.
- Restrict the AI to explicitly registered operations.
- Log tool calls without exposing secrets.
- Define safe behavior when the model produces invalid requests.

### Capability Layer

- Define a minimal capability contract.
- Implement capability registration.
- Implement capability discovery.
- Implement typed input and output validation.
- Implement error responses.
- Create one example capability.
- Implement web retrieval as explicit `web.search` and constrained `web.fetch`
  capabilities rather than giving the model general network access.
- Use a locally operated SearXNG instance as the initial replaceable search
  provider and disclose upstream query transmission.

### Pi-hole Integration

- Research supported Pi-hole APIs and authentication.
- Build a Pi-hole adapter.
- Implement read-only operations first.
- Avoid direct shell access.
- Add connection tests.
- Add graceful handling when Pi-hole is unavailable.
- Document compatible Pi-hole versions.

### Local Access

- Make the service available on the local network.
- Define an initial local hostname strategy.
- Support direct IP access as a fallback.
- Add basic local authentication or a clearly documented preview-only access model.
- Avoid public internet exposure.

### Raspberry Pi Deployment

- Select the base operating system.
- Define required packages.
- Create a repeatable installation script.
- Create system services.
- Define application data locations.
- Define log locations.
- Define update and uninstall steps.
- Test fresh installation from a clean device.

## Research Work

Conduct and document experiments for:

- Local model performance on Raspberry Pi 5
- Memory usage
- Response latency
- Thermal behavior
- Storage requirements
- Model quality for tool use
- ARM64 package compatibility
- Container versus native deployment
- Pi-hole API reliability
- Browser compatibility
- Local hostname discovery

## Design Work

- Create a basic interface design system.
- Define:
  - Typography
  - Spacing
  - Icons
  - Component patterns
  - Status indicators
- Design the preview onboarding flow.
- Design the chat experience.
- Design capability confirmation patterns.
- Design system health presentation.
- Ensure the dashboard works well on mobile and desktop browsers.

## Security Work

The preview does not need full production security, but it must avoid reckless defaults.

- Do not store secrets in source control.
- Do not permit arbitrary shell commands.
- Do not expose services publicly by default.
- Validate capability inputs.
- Restrict plugin permissions.
- Document known security limitations.
- Define a basic threat model.
- Scan dependencies.
- Establish a process for reporting security issues.

## Documentation Work

Create:

- Preview installation guide
- Raspberry Pi preparation guide
- Configuration guide
- Pi-hole integration guide
- Troubleshooting guide
- Developer setup guide
- Architecture overview
- Known limitations
- Demo script

## Demonstration Work

- Create a repeatable live demonstration.
- Record screenshots.
- Record a short demonstration video.
- Prepare a concise explanation of:
  - The problem
  - The system
  - Why local execution matters
  - What remains unfinished
- Collect structured feedback from early viewers.

## Operations Work

- Define backup requirements for the preview.
- Define log rotation.
- Define service restart behavior.
- Add basic system monitoring.
- Establish a manual release process.
- Tag preview releases.
- Publish checksums.
- Maintain release notes.

## Exit Criteria

Phase 01 is complete when:

- A clean Raspberry Pi can be prepared using documented instructions.
- Sovereign Home OS starts automatically after reboot.
- The dashboard is accessible on the local network.
- The assistant can invoke the Pi-hole integration.
- At least three supported questions work reliably.
- Unsupported actions fail safely.
- The system can run continuously for a defined test period.
- Resource usage is documented.
- A demonstration can be performed without editing code.
- Known limitations are clearly documented.
- At least one person other than the creator can understand the concept from the demo.

---

# 7. Phase 02 — Core Platform

## Objective

Turn the preview implementation into a coherent, reusable local application platform.

## Desired Outcome

The project moves from a hard-coded demonstration to an architecture that can support multiple capabilities and integrations without becoming tightly coupled.

## Core Platform Work

### Identity

- Define local user identity.
- Implement secure authentication.
- Define sessions.
- Support password recovery appropriate for a local system.
- Define administrator roles.
- Prepare for multiple users without necessarily enabling them immediately.

### Permissions

- Define user permissions.
- Define plugin permissions.
- Define capability permissions.
- Introduce confirmation requirements for sensitive actions.
- Create an audit trail for meaningful actions.

### Plugin Lifecycle

- Define the plugin manifest.
- Define installation.
- Define enabling and disabling.
- Define configuration.
- Define health reporting.
- Define updates.
- Define removal.
- Define data retention behavior after removal.
- Define rollback expectations.

### Capability Registry

- Formalize capability naming.
- Define versions.
- Define schemas.
- Define discovery.
- Define conflicts when multiple plugins provide the same capability.
- Define permission metadata.
- Define read-only and mutating operations.
- Define human-readable descriptions for AI and user interfaces.

### Secrets

- Define secret storage.
- Define plugin access to secrets.
- Prevent secrets from appearing in logs.
- Provide secret rotation.
- Define export and backup behavior.

### Configuration

- Define global configuration.
- Define plugin configuration.
- Define validation.
- Define migrations.
- Define defaults.
- Define environment-specific overrides.

### Events and Jobs

- Define internal events.
- Define background jobs.
- Define scheduling.
- Define retries.
- Define failure handling.
- Define idempotency expectations.

### Observability

- Add structured logs.
- Add metrics.
- Add health checks.
- Add diagnostic bundles.
- Add a user-facing activity history.
- Define privacy-safe diagnostics.

## System Work

- Improve service supervision.
- Establish reliable startup ordering.
- Improve local hostname support.
- Define storage layout.
- Define system update boundaries.
- Add backup and restore foundations.
- Define factory reset behavior.
- Define recovery behavior after failed updates.

## Developer Experience

- Create a plugin SDK.
- Create a plugin template.
- Create a local development environment.
- Add contract tests.
- Add integration test helpers.
- Add mocked platform services.
- Create API documentation.
- Create an example plugin.

## AI Orchestration

- Separate conversation handling from capability execution.
- Add deterministic validation around tool calls.
- Define context boundaries.
- Define per-capability instructions.
- Add model abstraction.
- Add fallback behavior.
- Add transparent indications when remote AI is used.
- Define conversation storage and deletion.
- Add user controls over retained context.

## Exit Criteria

Phase 02 is complete when:

- Plugins can be installed and removed through a defined lifecycle.
- Capabilities are formally registered and validated.
- Permissions are enforced.
- Secrets are handled safely.
- At least two independent plugins operate through the same platform interfaces.
- Core services have stable boundaries.
- The system can be backed up and restored.
- A developer can build an example plugin from documentation.

---

# 8. Phase 03 — Personal Daily Driver

## Objective

Make Sovereign Home OS valuable enough for consistent personal use.

## Purpose

The platform should become part of ordinary home and personal workflows rather than remain a technical demonstration.

## Product Work

Select a limited set of high-value integrations based on real use.

Potential candidates include:

- Home Assistant
- Pi-hole
- Shopping list
- Calendar
- Document search
- Personal knowledge
- System status
- Notifications

Selection should be based on frequency and usefulness, not novelty.

## User Experience

- Improve dashboard navigation.
- Add global search.
- Add activity history.
- Add notifications.
- Add plugin settings.
- Add user-friendly permission controls.
- Add clear explanations of AI actions.
- Improve empty, error, and offline states.
- Add responsive and installable PWA behavior where useful.

## Reliability

- Establish continuous runtime testing.
- Test power-loss recovery.
- Test network outages.
- Test internet outages.
- Test plugin failure isolation.
- Test storage pressure.
- Test model unavailability.
- Add safe degraded modes.

## Data Ownership

- Add straightforward exports.
- Add backup scheduling.
- Add restore validation.
- Document where all user data is stored.
- Define plugin data portability expectations.
- Add data deletion controls.

## Home Assistant Integration

If selected:

- Treat Home Assistant as a plugin or integration.
- Avoid reimplementing device integrations.
- Start with read-only state access.
- Add controlled actions.
- Require confirmation for sensitive actions.
- Map Home Assistant operations to platform capabilities.
- Document compatibility and limitations.

## Daily-Driver Evaluation

Maintain a usage journal containing:

- Tasks attempted
- Successful interactions
- Failed interactions
- Slow interactions
- Repeated manual work
- Missing capabilities
- Trust concerns
- Privacy concerns
- Reliability incidents

Use this evidence to drive priorities.

## Exit Criteria

Phase 03 is complete when:

- The creator uses the system regularly.
- It provides repeatable value in multiple real workflows.
- Core operations remain available during internet outages.
- Backups run successfully.
- Failed plugins do not take down the platform.
- The user can understand what actions the AI performed.
- The system has survived an extended daily-use period.
- Major usability and reliability problems are documented and prioritized.

---

# 9. Phase 04 — Voice Interface

## Objective

Add voice as an optional interface to the existing platform without changing the core architecture.

## Principles

- Voice is a client, not the platform.
- The web interface remains complete.
- Core functionality must not depend on microphones.
- Satellites remain lightweight.
- Protocols should be open.
- Physical mute controls are mandatory for official hardware designs.
- Users should understand when audio is being captured.

## Research Work

Evaluate:

- Wake-word engines
- Speech-to-text options
- Text-to-speech options
- Raspberry Pi audio performance
- Satellite hardware
- Echo cancellation
- Noise suppression
- Local network audio transport
- Multi-room latency
- Privacy indicators
- Physical mute designs

## Voice Protocol

Define an open protocol supporting events such as:

- Device registration
- Wake-word detection
- Audio stream start
- Audio chunks
- Audio stream end
- Playback start
- Playback stop
- LED state
- Mute state
- Volume state
- Health status

## Voice Server

- Accept satellite connections.
- Authenticate devices.
- Process audio.
- Invoke existing assistant flows.
- Stream or return responses.
- Manage timeouts.
- Handle interrupted speech.
- Support cancellation.
- Provide diagnostics.

## Satellite

Create an initial implementation for one target, potentially:

- Raspberry Pi Zero
- ESP32-S3
- Desktop client
- Mobile client

The first version should prioritize development simplicity over final hardware cost.

## Voice User Experience

- Define wake indicators.
- Define listening indicators.
- Define processing indicators.
- Define speaking indicators.
- Define error sounds or states.
- Support cancel and stop.
- Support physical mute.
- Make cloud usage visible when applicable.

## Exit Criteria

Phase 04 is complete when:

- A voice satellite can be paired locally.
- Audio handling is clearly indicated.
- A supported spoken request can invoke an existing capability.
- The same action works through both chat and voice.
- The physical mute state is trustworthy and visible.
- Voice failure does not affect the web experience.
- The protocol is documented.

---

# 10. Phase 05 — Plugin Ecosystem

## Objective

Enable third parties to create, distribute, and maintain plugins without compromising platform security or user control.

## Plugin Development

- Stabilize the plugin SDK.
- Publish plugin documentation.
- Publish examples.
- Add validation tools.
- Add local testing tools.
- Add compatibility checks.
- Define semantic versioning expectations.
- Define platform API stability promises.

## Distribution

- Define a plugin package format.
- Define signing.
- Define provenance.
- Define repository metadata.
- Define installation sources.
- Support manual installation.
- Avoid making the official marketplace mandatory.

## Trust and Security

Define plugin trust states such as:

- Local development
- Community
- Verified publisher
- Certified
- Privacy reviewed
- Offline ready

Trust labels must have precise meanings.

## Review Process

- Define automated checks.
- Define security review criteria.
- Define privacy review criteria.
- Define permission review.
- Define update review.
- Define removal and revocation processes.

## Community Work

- Create plugin author documentation.
- Create contribution channels.
- Create issue templates.
- Create discussion categories.
- Establish contributor recognition.
- Publish an ecosystem governance proposal.

## Exit Criteria

Phase 05 is complete when:

- An external developer can create a plugin from documentation.
- Plugins can be installed from outside the core repository.
- Users can inspect requested permissions.
- Plugins can be signed and verified.
- Manual installation remains possible.
- The platform can disable or remove an unsafe plugin.
- At least one non-core plugin has been built independently.

---

# 11. Phase 06 — Public Preview

## Objective

Release Sovereign Home OS to a limited public audience for real-world testing.

## Product Readiness

- Define supported hardware.
- Define supported installation paths.
- Define supported upgrade paths.
- Define known limitations.
- Define user support expectations.
- Add first-run onboarding.
- Add diagnostics and support bundles.
- Add clear backup guidance.

## Installation

Potential supported methods:

- Installer on a supported Linux distribution
- Prebuilt Raspberry Pi image
- Container-based development installation

One method should be considered primary.

Others should not be labeled supported until they are tested continuously.

## Release Engineering

- Automate builds.
- Sign release artifacts.
- Publish checksums.
- Generate release notes.
- Add update channels.
- Support rollback.
- Test upgrades from previous releases.
- Define release cadence.
- Define long-term support expectations later.

## Security

- Complete a broader threat model.
- Conduct external review where possible.
- Establish vulnerability disclosure.
- Publish a security policy.
- Define response procedures.
- Audit default network exposure.
- Audit update integrity.
- Audit secrets and authentication.

## Documentation

Publish:

- Installation
- Configuration
- Backups
- Restore
- Updates
- Security
- Privacy
- Troubleshooting
- Plugin development
- Architecture
- Frequently asked questions

## Community

- Launch project website.
- Publish demonstration videos.
- Open public discussions.
- Establish a code of conduct.
- Define contribution workflow.
- Define maintainer responsibilities.
- Create a public feedback process.
- Avoid creating too many communication channels initially.

## Evaluation

Collect:

- Installation success rates
- Hardware configurations
- Common failures
- Performance data submitted voluntarily
- Feature usage feedback
- Support burden
- Security reports
- Plugin developer feedback

No mandatory telemetry should be introduced.

## Exit Criteria

Phase 06 is complete when:

- External users can install the system using public documentation.
- Updates work reliably.
- Backups and restore are tested.
- Security reporting is established.
- Support boundaries are clear.
- Multiple households have used the system.
- Critical failure patterns are understood.
- The project has enough evidence to define Version 1.0 accurately.

---

# 12. Phase 07 — Version 1.0

## Objective

Deliver a stable, trustworthy release suitable for sustained personal use.

## Product Requirements

Version 1.0 should provide:

- Reliable installation
- Reliable updates
- Reliable rollback or recovery
- Local authentication
- Plugin lifecycle management
- Capability-based AI orchestration
- Backup and restore
- Clear data ownership
- At least one strong everyday integration
- A polished web experience
- Documented hardware support
- Safe defaults
- Optional voice support if mature enough

Version 1.0 does not need to include every long-term feature.

It needs to establish a trustworthy foundation.

## Quality Requirements

- Defined compatibility policy
- Stable data migration
- Upgrade testing
- Recovery testing
- Security review
- Documented support window
- Documented known limitations
- Reproducible release process
- Appropriate test coverage
- Performance baselines
- Accessibility review

## Governance

- Define maintainership.
- Define decision-making.
- Define release authority.
- Define contribution acceptance.
- Define project licensing.
- Define plugin ecosystem governance.
- Define trademark usage.
- Define official and community-supported components.

## Sustainability

Before Version 1.0, clarify:

- Ongoing hosting costs
- Release infrastructure costs
- Hardware testing costs
- Support expectations
- Potential funding models
- Commercial boundaries
- Community expectations

## Exit Criteria

Version 1.0 is ready when:

- The project is safe and useful for its defined audience.
- A failed update can be recovered.
- User data can be backed up and restored.
- Supported hardware and software are explicitly documented.
- Core features have stable interfaces.
- Security and privacy expectations are clear.
- The project can be maintained without unsustainable manual work.
- The release does not depend on unannounced future work to be useful.

---

# 13. Cross-Cutting Workstreams

Some responsibilities span every phase.

## 13.1 Product Management

Maintain:

- Product principles
- Target users
- Use cases
- Feature definitions
- Non-goals
- Success metrics
- Feedback records
- Prioritization criteria
- Idea icebox

Every feature should answer:

- Which user problem does it solve?
- Why does it belong in the platform?
- Why is it needed now?
- How will success be observed?
- What is explicitly out of scope?

---

## 13.2 Architecture

Maintain:

- System overview
- Component boundaries
- Data flows
- Trust boundaries
- Capability model
- Plugin model
- Storage model
- Networking model
- Update model
- Backup model
- Security model

Architecture documentation should describe the current system, not only the desired future.

---

## 13.3 Security and Privacy

Security and privacy are continuous workstreams.

Maintain:

- Threat model
- Data inventory
- Secret inventory
- Network exposure inventory
- Dependency scanning
- Vulnerability reporting
- Security advisories
- Permission reviews
- Update integrity
- Backup confidentiality
- Privacy documentation

Every integration should document:

- Data accessed
- Data stored
- Data transmitted
- Required permissions
- Cloud dependencies
- Failure behavior

---

## 13.4 User Experience

Maintain consistency across:

- Onboarding
- Dashboard
- Chat
- Settings
- Plugin installation
- Permissions
- Notifications
- Errors
- Offline behavior
- Updates
- Backup and restore
- Voice

The system should explain complex behavior without requiring infrastructure expertise.

---

## 13.5 Documentation

Documentation is part of the product.

Maintain:

- User guides
- Developer guides
- Architecture
- API references
- Operations
- Security
- Privacy
- Troubleshooting
- Release notes
- Migration guides
- Known limitations

Documentation changes should be included in the same work item as behavior changes.

---

## 13.6 Testing

Maintain a layered test strategy:

- Unit tests
- Contract tests
- Integration tests
- End-to-end tests
- Installation tests
- Upgrade tests
- Backup and restore tests
- Failure tests
- Security tests
- Hardware tests
- Long-running stability tests

Real hardware testing should not be replaced entirely by emulation or CI.

---

## 13.7 Release Engineering

Maintain:

- Versioning
- Build automation
- Artifact signing
- Checksums
- Release notes
- Update channels
- Rollback
- Compatibility testing
- Migration testing
- Release checklists
- Incident response

---

## 13.8 Community

Community work should begin carefully.

Maintain:

- Contribution guide
- Code of conduct
- Discussion channels
- Issue templates
- Roadmap transparency
- Decision transparency
- Contributor recognition
- Maintainer expectations

Do not build a community program before there is something useful to contribute to.

---

## 13.9 Business and Sustainability

The project should remain sustainable without monetizing user data.

Potential future work includes:

- Official hardware
- Support services
- Optional convenience services
- Plugin marketplace
- Certification
- Enterprise features
- Sponsorship
- Grants
- Consulting

Commercial work must not create a mandatory dependency for core local functionality.

---

# 14. Initial Document Backlog

The following documents should be created during the earliest phases.

## Product

- Concept Paper
- Master Plan
- Preview Scope
- Target User
- Core Use Cases
- Non-Goals
- Product Terminology

## Architecture

- System Overview
- Core Service Boundaries
- Capability Model
- Plugin Model
- Data and Storage Model
- Networking Model
- AI Orchestration Model
- Security Model
- Backup and Restore Model
- Update Model

## Research

- Raspberry Pi 5 Capability Assessment
- Local LLM Benchmark
- Deployment Model Comparison
- Pi-hole Integration Research
- Local Hostname Discovery
- Voice Technology Landscape
- Home Assistant Integration Assessment

## Operations

- Development Environment
- Raspberry Pi Installation
- Release Process
- Backup Procedure
- Restore Procedure
- Troubleshooting
- Incident Handling

## Governance

- Contribution Guide
- Security Policy
- Licensing Decision
- Decision-Making Process
- Plugin Review Principles

---

# 15. Initial RFC Backlog

Potential early RFCs include:

- RFC-0001: Monorepo Structure
- RFC-0002: Core Runtime Architecture
- RFC-0003: Capability Contract
- RFC-0004: Plugin Manifest and Lifecycle
- RFC-0005: AI Capability Invocation
- RFC-0006: Configuration Model
- RFC-0007: Local Networking and Hostname
- RFC-0008: Application Data Layout
- RFC-0009: Authentication for the Preview
- RFC-0010: Raspberry Pi Deployment Model
- RFC-0011: Pi-hole Plugin
- RFC-0012: Logging and Diagnostics
- RFC-0013: Backup and Restore
- RFC-0014: Update and Rollback
- RFC-0015: Voice Satellite Protocol

This list is provisional.

An RFC should be created only when the subject is ready for a concrete proposal.

---

# 16. Initial Experiment Backlog

Potential experiments include:

- EXP-0001: Local LLM Latency on Raspberry Pi 5
- EXP-0002: Tool-Calling Reliability Across Small Models
- EXP-0003: Native Versus Container Deployment
- EXP-0004: Memory Usage Under Concurrent Services
- EXP-0005: Thermal Stability Under AI Workloads
- EXP-0006: Power-Loss Recovery
- EXP-0007: Local Network Discovery
- EXP-0008: Pi-hole API Compatibility
- EXP-0009: Browser-Based Voice Capture
- EXP-0010: Speech Recognition on Raspberry Pi 5

Each experiment should produce a documented conclusion.

Experiments should not become permanent half-finished branches.

---

# 17. Prioritization Framework

When deciding what to do next, score work according to:

## User Value

Does this make the current system more useful?

## Risk Reduction

Does this test an important assumption or remove uncertainty?

## Dependency Value

Does this unblock multiple future tasks?

## Demonstration Value

Does this help explain or prove the concept?

## Reliability Value

Does this make the system safer to depend on?

## Maintenance Cost

Will this create significant long-term complexity?

## Principle Alignment

Does it strengthen user ownership, privacy, local operation, openness, modularity, or simplicity?

High-value, high-risk-reduction, low-complexity items should be prioritized.

Novelty alone is not a reason to prioritize work.

---

# 18. Work Item Readiness

A task is ready for implementation when:

- The problem is clearly defined.
- The expected outcome is defined.
- Success criteria are testable.
- Dependencies are known.
- Relevant architecture is documented.
- Security and privacy implications are considered.
- Scope and non-scope are explicit.
- Required design work is complete.
- The implementation can be reviewed independently.

Not every small task requires an RFC.

Every task requires enough context to prevent accidental improvisation.

---

# 19. Definition of Done

A work item is not complete merely because code exists.

Depending on the task, completion may require:

- Implementation
- Tests
- Documentation
- Migration
- Error handling
- Security review
- Accessibility consideration
- Deployment changes
- Monitoring
- Release notes
- Demonstration
- Retrospective

The applicable completion requirements should be defined before implementation.

---

# 20. Progress Tracking

The master plan should not become a task tracker.

Detailed work belongs in issues and implementation plans.

This document tracks:

- Phase status
- Major deliverables
- Major decisions
- Dependencies
- Risks
- Exit criteria

The root `ROADMAP.md` should be updated when:

- A phase begins
- A phase completes
- A major deliverable changes
- A major scope decision is made
- A significant risk affects the public direction

---

# 21. Current Priority

The immediate priority is:

> Deliver a small, stable, demonstrable Sovereign Home OS preview on the Raspberry Pi 5.

The first work sequence is:

```text
Finalize project documents
    ↓
Create monorepo
    ↓
Define preview scope
    ↓
Research Raspberry Pi deployment and local AI
    ↓
Approve initial architecture
    ↓
Implement the smallest vertical slice
    ↓
Install on real hardware
    ↓
Measure and improve
    ↓
Produce a repeatable demonstration
```

The preview should remain the active priority until its exit criteria are met.

Voice, custom hardware, marketplaces, enterprise features, and broad plugin ecosystems remain outside the immediate scope.

---

# 22. Ultimate Success Condition

The long-term project succeeds when an ordinary person can operate useful digital services in their own home without surrendering ownership of their data or becoming the administrator of a collection of disconnected servers.

The platform should make self-hosted computing feel coherent, understandable, and trustworthy.

The earliest proof of that vision is much smaller:

> A Raspberry Pi running Sovereign Home OS provides one useful, reliable, privacy-respecting experience that the creator chooses to keep using.
