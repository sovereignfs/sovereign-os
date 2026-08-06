# ADR-0010: Shared Console-Session Gate for Pi-hole and Future Service Panels

**Status:** Accepted
**Date:** 2026-08-06
**Decision owner:** Project creator (delegated to the assistant for this
decision, same as ADR-0008/ADR-0009 — see Decision below)
**Related ADRs:** [ADR-0007](0007-console-authentication.md), [ADR-0008](0008-console-privileged-action-invocation.md)
**Related RFCs:** None
**Related milestone:** None (raised ahead of the next service integration,
not tied to a named ROADMAP item yet)
**Supersedes:** None

## Context

ADR-0007 gave Console its own session-based login, deliberately kept as a
credential separate from Pi-hole's own admin password and the `sovereign`
Linux account — three trust boundaries, on purpose, so that compromising one
doesn't hand over the others. That decision is not being revisited here.

The question this ADR answers is different: as Sovereign adds more
LAN-facing service panels beyond Pi-hole (the project owner's own phrasing:
"Pi-hole and other services we are going to add"), should reaching each of
those panels keep requiring its own separate sign-in, or can one Console
sign-in also gate the others — something SSO-shaped, without actually
building SSO?

Today, `/dns/` (Pi-hole's admin UI) is reverse-proxied straight through by
Nginx with no gate of its own — reachable by anyone on the LAN who knows the
URL, protected only by Pi-hole's own built-in login screen. As more services
are added behind the same Nginx instance, repeating that pattern means each
one grows its own exposed-until-you-hit-its-login surface, and repeating
"build a whole separate auth system per service" is neither realistic nor
consistent with how Console's own auth was scoped in ADR-0007.

### Why not literal SSO

A shared identity provider (OIDC/OAuth2, a self-hosted IdP like Keycloak or
Authelia, or hand-rolling token issuance/validation across services) was
considered and rejected for the same reason ADR-0007 already rejected it for
Console alone: this is a single-household, single-admin appliance with no
multi-tenant or multi-role concept, and standing up real identity-provider
infrastructure — new services, new attack surface, new things to keep
patched — is disproportionate to what one household actually needs, which
is "don't make me sign in three times for one visit," not "federate
identity across services."

## Decision

**Gate other services' Nginx locations behind Console's existing session
cookie, at the proxy layer, using Nginx's `auth_request` module — one
sign-in unlocks reachability to every gated panel, without merging
credentials, issuing shared tokens, or building anything resembling a real
identity provider.**

- A new, loopback-only, unauthenticated-body `GET /api/v1/auth/verify`
  endpoint on the existing `console-auth` service (port 8091): looks up the
  session cookie via the same `lookup_session()` already used by
  `_require_authenticated_session()`, and returns a bare `204` if valid,
  `401` otherwise. No JSON body, no CSRF check — `auth_request` subrequests
  carry the original request's cookies but not a way to attach a custom
  header the browser didn't already send, and CSRF protects state-changing
  POSTs, not read navigation to a panel that's about to enforce its own
  login anyway.
- Nginx's `/dns/` location gains `auth_request /api/v1/auth/verify-internal;`
  pointed at an `internal`-only location that proxies to the new endpoint,
  the standard `auth_request` pattern (the subrequest URI must stay
  internal so it can't be hit directly from the LAN).
- `error_page 401 = @signin;` redirects an ungated visitor to
  `/console/?next=/dns/`, i.e., Console's own sign-in page, rather than
  Pi-hole's. Console's existing sign-in flow already knows how to reach a
  signed-in state; it just needs to honor `?next=` on success by
  redirecting there instead of staying on `/console/`.
- Any future service panel this project adds behind Nginx picks up the same
  protection by adding the same two lines (`auth_request` + the shared
  `@signin` error page) to its own `location` block — no new service-specific
  auth code, no new credential store, no per-service session logic.
- Pi-hole's own login screen is **not removed or bypassed**. A visitor who
  clears the gate still sees Pi-hole's own login prompt underneath, because
  Sovereign does not control Pi-hole's session internals and reimplementing
  or bypassing them is out of scope (and would mean holding a second,
  Sovereign-managed copy of Pi-hole's own auth state, which is exactly the
  kind of coupling ADR-0007 avoided by keeping the Pi-hole credential
  separate in the first place). This is a *reachability* gate, not a
  *session-sharing* one: it stops an unauthenticated LAN visitor from ever
  seeing Pi-hole's login form at all, but doesn't remove the second,
  lighter prompt once they're through. In practice, using the same
  password for both keeps that second prompt to one quick re-entry rather
  than a real second credential to remember.

## What this actually protects

The same question ADR-0007 already asked for Console itself, now extended
to everything proxied alongside it: not a secret, but who's allowed to
*reach* a panel that can change household-wide state (Pi-hole's DNS
filtering config, and whatever a future service exposes). Today, anyone on
the LAN can already reach `/dns/` and start guessing Pi-hole's password with
no rate limiting Sovereign controls itself (that's entirely up to Pi-hole's
own login implementation). Gating the whole location behind Console's
already-rate-limited, already-hardened session check closes that
reachability gap for every current and future panel at once, in one place,
instead of needing every new service to solve it individually.

## Options

### Option A — Real SSO (OIDC/OAuth2 via a self-hosted identity provider) (rejected)

Stand up Keycloak, Authelia, or similar; every service authenticates
against it.

- **Rejected** for the same reason ADR-0007 rejected third-party identity
  providers for Console alone: disproportionate infrastructure, new attack
  surface, and a multi-tenant/role feature set this single-admin appliance
  has no use for. Also directly conflicts with this project's stated
  self-sufficiency-over-dependencies values (the same reasoning ADR-0006
  applied to reject cloud KMS, and ADR-0007 applied to reject OAuth).

### Option B — One shared credential across all services, no proxy gate

Set every service's own password to match Console's, and stop there —
no `auth_request`, just a documented convention that they're kept in sync.

- Zero new code.
- **Rejected as insufficient on its own**: it does nothing about
  reachability — Pi-hole's login form (and whatever a future service's is)
  stays fully exposed to anyone on the LAN, with no rate limiting or
  hardening Sovereign controls, and "remember to keep two passwords in
  sync by hand" is a real drift risk with no enforcement. Worth doing
  *in addition* to the proxy gate (see Decision's last bullet) as a
  low-friction way to shrink the second, still-visible login prompt, but
  not a substitute for actually gating reachability.

### Option C — `auth_request` proxy gate against Console's session (chosen)

As described in Decision.

- Reuses ADR-0007's already-hardware-qualified session mechanism
  (`console-auth`, rate limiting, session expiry) rather than building
  anything new for authentication itself — only a small new read-only
  verify endpoint and an Nginx directive per gated location.
- Scales to future services by repeating a two-line Nginx pattern, not a
  new subsystem per service.
- **Downside, accepted:** not true SSO — a gated service still shows its
  own login underneath. Judged an acceptable, honestly-scoped tradeoff
  given Option A's disproportionate cost for what this appliance actually
  needs (see Context).

### Option D — Sovereign-managed credential injection (Console logs into Pi-hole on the user's behalf and forwards its session)

Have `console-auth` (or a new privileged helper) hold Pi-hole's credential,
perform Pi-hole's own login flow server-side, and forward or rewrite
Pi-hole's resulting session cookie to the browser after a successful
Console sign-in.

- Would produce true single-session UX (no second prompt at all).
- **Rejected:** requires Sovereign to hold and manage a second service's
  credential on the user's behalf, script against Pi-hole's own
  undocumented internal login flow (fragile across Pi-hole upgrades, the
  same kind of coupling the Pi-hole API assessment already flagged as a
  compatibility risk), and reintroduces exactly the shared-secret coupling
  ADR-0007 deliberately avoided by keeping Pi-hole's credential separate.
  Disproportionate complexity and fragility for saving one password
  re-entry.

## Consequences

### Positive

- One sign-in gates reachability to every current and future LAN-facing
  service panel, closing an existing gap (Pi-hole's admin UI has no
  Sovereign-controlled reachability protection today) without waiting for
  each service to grow its own.
- No new credential, session store, or identity system — reuses
  ADR-0007's already-accepted, already-hardware-qualified mechanism
  entirely.
- Extends to a new service by adding a two-line Nginx pattern to its
  `location` block, not new per-service code.

### Negative

- Not real SSO: a gated panel still shows its own login prompt once the
  proxy gate is passed. Households that want zero-friction single sign-on
  across every panel don't get that from this decision alone (Option B's
  shared-password convention narrows, but doesn't eliminate, the second
  prompt).
- A new always-reachable-from-Nginx endpoint (`/api/v1/auth/verify`,
  internal-only but still new production surface) is called on every
  request to every gated location — needs to stay cheap (in-memory session
  lookup, no disk I/O on the hot path) so it doesn't become a latency or
  availability dependency for panels that would otherwise work fine on
  their own.

### Risks

- If `console-auth` (port 8091) is down, every gated panel becomes
  unreachable too, not just Console itself — a new availability coupling
  that doesn't exist today (Pi-hole currently works independently of
  Console's health). Needs an explicit decision, at implementation time,
  on Nginx's `error_page`/`proxy_intercept_errors` behavior if the verify
  subrequest itself fails to connect, rather than defaulting to whatever
  Nginx does out of the box.
- `?next=` redirect targets must be validated against an allowlist of
  known internal paths before Console honors them post-login, to avoid
  turning the sign-in flow into an open redirect.

## Alternatives Considered

See Options above; no alternatives outside those four were seriously
considered, since Option A (real SSO) and Option C (proxy session gate)
bound the realistic range for this project's stated scale and values.

## Validation and Revisit Conditions

**Implemented and hardware-qualified (2026-08-06).** The `/api/v1/auth/verify`
endpoint, the `auth_request`/`error_page`/`@signin` Nginx wiring, and the
`?next=` sign-in redirect (with its allowlist) are all built and verified
end-to-end on the real Raspberry Pi 5 qualification device, through the
real Nginx proxy, against the real `console-auth` service, from a real
browser — see the
[qualification report](../research/shared-console-session-gate-hardware-qualification-report.md)
for the full method and evidence, including a real implementation bug this
pass caught before it could reach a release: the original `nginx-full`
package pin was wrong for this image's actual Debian 13 (trixie) base
(no `nginx-full` package exists there; the plain `nginx` package already
ships `auth_request`), corrected during this same qualification pass.

Confirmed: an unauthenticated LAN client reaching `/dns/` is bounced to
Console's sign-in with the path preserved; after signing in, the same
browser is bounced back and the gate lets the request through to Pi-hole,
which then correctly applies its own separate, unaffected login. Not yet
separately tested: `console-auth` being down (this ADR's own named risk) —
the gate's fail-open/fail-closed behavior in that specific failure mode
remains unverified.

Revisit this ADR if: a future service's integration needs genuinely
different reachability rules than "same gate as everything else" (e.g. a
service that must stay reachable even when signed out), or if the
second-prompt friction from Option C's honest limitation turns out to
matter enough in practice to justify Option D's added complexity.
