# Design Brief: Sovereign Console Health

**Status:** Accepted for the initial read-only slice

**Owner:** Project creator

**Target phase:** Console Foundation

## User Problem

After flashing Sovereign OS, a user lands directly in Pi-hole and cannot see
whether the appliance, storage, network, or dependent services are healthy.
Command-line diagnostics expose implementation details and require SSH.

## Users and Context

The initial user operates one Raspberry Pi on a trusted household LAN from a
desktop or mobile browser. They need a fast answer to “Is Sovereign working?”
and a clear path to the first installed service.

## Desired Outcome

Opening `http://sovereign.local/` leads to a calm, responsive Console that
reports overall health, essential resource state, and Pi-hole availability, then
offers a direct “Open Pi-hole” action.

## Scope

- `/console/` overview
- `/console/health/` stable health route
- Overall Healthy, Degraded, or Unavailable state
- Sovereign version and device identity at a non-sensitive level
- Uptime, memory, DATA storage, temperature, and network summary
- DNS and Pi-hole health
- Check timestamp
- Link to `/dns/admin/`
- Loading, degraded, and API-unavailable states

## Non-Scope

- Authentication and multiple users
- Settings or state changes
- Service restart, update, backup, or recovery controls
- Logs, terminal, file browser, container details, or DNS query history
- Wi-Fi configuration
- Charts and historical metrics
- Assistant or search interface

## Experience Requirements

- Lead with the user outcome, not process/container terminology.
- Display the last check time and never silently present stale health as live.
- Preserve the page shell when the health API is unavailable.
- Explain degraded checks without exposing secrets or raw internal errors.
- Keep the Pi-hole interface one deliberate action away.
- Work without external fonts, scripts, analytics, or internet resources.
- Render effectively on small mobile screens and desktop browsers.

## States and Failure Cases

- **Loading:** Console shell appears immediately with a clear checking state.
- **Healthy:** Required storage, DNS, Pi-hole, and local routing checks pass.
- **Degraded:** The page remains usable and identifies each unavailable outcome.
- **Unavailable:** API failure is explicit and offers a retry action.
- **Partial:** Optional measurements may be reported as unknown without making
  the entire appliance unavailable.

## Accessibility

- Semantic headings and landmarks
- Keyboard-operable links and retry action
- Visible focus treatment
- Status conveyed through text and iconography, never color alone
- Sufficient contrast and responsive text without horizontal scrolling
- Reduced-motion preference respected

## Privacy and Trust

The unauthenticated preview response may expose only bounded operational data:
version, model family, uptime, aggregate memory/storage, temperature, interface
names and addresses, and named service health. It must not expose passwords,
keys, serial numbers, complete environment/configuration, client identities,
queries, logs, or browsing history.

## Constraints

- Nginx is the sole LAN listener on port 80.
- Health collection runs without root and without Docker socket access.
- All assets ship in the image.
- Pi-hole and DNS must continue operating if the Console fails.
- The implementation must fit the current Raspberry Pi OS image and use minimal
  additional dependencies.

## Acceptance Criteria

- `/` redirects to `/console/`.
- `/console/` and `/console/health/` render without internet access.
- `/api/v1/health` returns a versioned bounded JSON document.
- A healthy preview.5-class device is represented as healthy.
- Stopping or degrading Pi-hole produces a degraded response without breaking
  the Console page.
- `/dns/admin/` remains functional and linked from the Console.
- No secret or DNS-history field is present in HTML, JavaScript, or JSON.
- The health process is loopback-only, unprivileged, and systemd-hardened.
