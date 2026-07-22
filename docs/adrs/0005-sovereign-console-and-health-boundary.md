# ADR-0005: Sovereign Console Namespace and Health Boundary

**Status:** Accepted

**Date:** 2026-07-22

**Decision owner:** Project creator

**Related plan:** [Console Foundation](../roadmap/01-console-foundation.md)

## Context

The appliance currently sends `/` directly to Pi-hole. That proves the first
service but presents Sovereign OS as a Pi-hole image rather than a platform.
Upcoming updates, model management, search, conversation, and home automation
need one coherent product entry point without absorbing the independent service
namespaces.

The first interface only needs read-only health. It must remain useful when
Pi-hole is degraded and must not require broad root, systemd, or Docker access.

## Decision

- The product is named **Sovereign Console**.
- `/console/` is the canonical human interface namespace.
- `/` redirects to `/console/`.
- `/console/health/` is the stable detailed health page; the initial Console
  overview may render the same experience.
- `/api/v1/health` is the machine-readable Sovereign health resource.
- Existing services keep independent namespaces such as `/dns/*`.
- The initial Console is read-only and available on the trusted LAN under the
  preview security model.
- A dedicated unprivileged loopback service produces bounded health data.
- Nginx remains the only LAN-facing HTTP service.
- The Console does not receive the Docker socket, service credentials, raw DNS
  history, unrestricted logs, or mutating operations.
- Authentication is required before settings, restarts, updates, credential
  changes, detailed logs, or other state-changing operations are added.

## Consequences

### Positive

- Sovereign gains a durable product entry point independent of Pi-hole.
- Updates, diagnostics, the assistant, and future services can reuse one health
  vocabulary and API.
- Third-party applications remain modular and directly addressable.
- The first implementation can remain small and privilege-minimized.

### Negative

- Sovereign now owns and must maintain a web interface and health API.
- LAN-visible health data requires an explicit minimal-disclosure policy.
- Root routing changes, so documentation and physical qualification must verify
  the new entry point.

## Rejected Alternatives

### `/control/`

This implies privileged mutation even on read-only status and ordinary product
pages.

### `/dashboard/`

This describes one presentation rather than a durable platform interface.

### `/admin/`

This is overly generic, implies elevated authority, and remains reserved from
the Pi-hole namespace.

### Use a container-management dashboard

Infrastructure objects are not the Sovereign product model and exposing them
would broaden privileges and confuse service health with user outcomes.
