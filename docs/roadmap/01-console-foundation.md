# Console Foundation

**Status:** Implemented; Raspberry Pi image qualification pending

**Priority:** Immediate product slice after physical appliance qualification

**Depends on:** Qualified image boot, persistent storage, DNS, and local routing

## Objective

Establish Sovereign Console as the durable UI entry point and deliver the first
read-only health experience without introducing premature administration or
identity systems.

## User Promise

```text
Open sovereign.local
    -> see whether Sovereign OS is healthy
    -> understand any degraded outcome
    -> open the installed Pi-hole service
```

## Deliverables

- `/console/` and `/console/health/` UI routes
- `/api/v1/health` versioned health resource
- Loopback-only unprivileged health service
- Overall health aggregation with bounded checks
- Responsive, dependency-free Console assets
- Pi-hole deep link
- Nginx and systemd integration
- Offline, failure, privacy, and physical-image tests

## Health Contract

Required top-level fields:

```json
{
  "schema_version": "1",
  "status": "healthy",
  "checked_at": "2026-07-22T19:00:00Z",
  "system": {},
  "checks": {}
}
```

Statuses are `healthy`, `degraded`, or `unknown`. Required checks initially
cover persistent storage, DNS, Pi-hole, and local access. Measurements include
uptime, memory, DATA storage, temperature, and network addresses when safely
available.

The endpoint returns HTTP 200 for a valid health document, including degraded
state. Transport/service failure is represented by an unavailable HTTP response,
not a fabricated health document.

## Security Boundary

- Read-only LAN access during preview
- No credentials, logs, DNS history, client identifiers, or hardware serials
- No Docker socket, D-Bus mutation, sudo, or arbitrary command execution
- Fixed health probes with strict timeouts and bounded output
- Loopback backend; Nginx is the only LAN HTTP listener
- Authentication required before adding any mutation

## Delivery Sequence

1. Accept route, experience, data, and privilege boundaries.
2. Implement the loopback health API and systemd sandbox.
3. Implement local static Console assets.
4. Route Console and API through Nginx and move `/` to `/console/`.
5. Add regression and degraded-state tests.
6. Build, flash, and qualify on Raspberry Pi 5.

## Exit Criteria

- Console routes and API meet the accepted contracts.
- Healthy and degraded states are physically demonstrated.
- Pi-hole remains independently available under `/dns/*`.
- Console failure does not interrupt DNS.
- Required information is understandable without infrastructure terminology.
- Security and data review finds no secret or household-history disclosure.
- The release checklist includes Console routing and health verification.

## Relationship to Later Work

The appliance update system may consume the same health contract for update
gates. The assistant later invokes a typed `system.health` capability backed by
the same model. Neither consumer receives authority merely by reading health.
