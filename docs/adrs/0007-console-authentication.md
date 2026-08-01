# ADR-0007: Sovereign Console Authentication

**Status:** Accepted
**Date:** 2026-07-31
**Decision owner:** Project creator
**Related ADR:** [ADR-0005](0005-sovereign-console-and-health-boundary.md)
**Related RFCs:** [RFC-0014](../rfcs/0014-appliance-update-system.md), [RFC-0015](../rfcs/0015-update-discovery.md)
**Related milestone:** [Update Discovery and Console Controls](../../ROADMAP.md)
**Supersedes:** None

## Context

[ADR-0005](0005-sovereign-console-and-health-boundary.md) deliberately shipped
Console as **read-only and unauthenticated** on the trusted LAN, and said so
explicitly:

> Authentication is required before settings, restarts, updates, credential
> changes, detailed logs, or other state-changing operations are added.

That boundary has held. The initial Console slice — `/console/`,
`/console/health/`, `/api/v1/health` — exposes only bounded, non-sensitive
health data (version, uptime, aggregate memory/storage, temperature,
interface names/addresses, named service health) from an unprivileged,
loopback-only, systemd-hardened health process, per
[docs/design/console-health.md](../design/console-health.md). No credential
exists to check because nothing on that surface can change device state.

That is no longer true of what's queued up next. RFC-0015 (Update Discovery)
was scoped explicitly to avoid this problem for its own device-side `check`
subcommand, and says so in its own Summary:

> This RFC proposes the mechanism for that check... and explicitly does not
> propose a Console UI or an automatic install path. Both remain out of
> scope until Console has an authentication story (see ADR-0005), per the
> project owner's own prior decision on that boundary.

ROADMAP milestone "Update Discovery and Console Controls" lists, as
still-planned work blocked on this: showing update details in Console,
**user-triggered download and installation**, and reporting
download/verification/staging/activation/validation/rollback states. All of
that means Console needs to be able to invoke `sovereign-update
prepare/backup/stage/activate/restore/prune/rotate-trust` — every one of
which is currently an operator-run, SSH-gated command — from a LAN-facing,
currently-unauthenticated web page. The same question will eventually apply
to any future Pi-hole admin actions Console might surface directly rather
than linking out to `/dns/admin/`.

This ADR does not choose Console's authentication mechanism for the project
owner. It lays out the realistic options at this project's current scale (a
small/solo maintainer, self-hosted household appliance, budget-conscious,
values self-sufficiency over third-party dependencies) so a deliberate
choice can be recorded and revisited as Console's privileged surface grows,
the same way ADR-0006 did for production signing-key custody.

### What this actually protects

Once Console gains any mutating capability, whoever can reach it over the
LAN (and, if the device is ever exposed beyond the LAN — see Threat Model
below — anyone who can reach it at all) can:

- trigger an appliance update install, restore a backup, or rotate the
  update trust store on a device that answers DNS for the household;
- potentially change Pi-hole configuration or credentials, if Console ever
  grows admin actions beyond linking to `/dns/admin/`;
- at minimum, cause disruption (unwanted reboots, restores, or update
  installs) even without extracting any secret.

This is not about protecting a secret value the way ADR-0006's signing key
is — health data and Console's own state aren't confidential in the same
sense. It's about gating **who is allowed to cause state change** on a
device with real household impact (DNS for every device on the network,
Pi-hole credentials, the update trust chain). The existing layered defenses
(signed manifests, staged/health-gated activation, automatic rollback)
constrain what a *bad update* can do once triggered; they do nothing to
constrain *who is allowed to trigger one* — that is what Console
authentication is for.

### Threat model

Sovereign OS's stated deployment model is a self-hosted household appliance
on a trusted LAN, not exposed to the public internet by default (see
[docs/operations/first-login-and-network-setup.md](../operations/first-login-and-network-setup.md):
"Do not expose the preview appliance directly to the internet"). Realistic
threats at this scale, roughly in order of likelihood:

- **Other devices/users on the same LAN**, not fully trusted: guests,
  IoT devices with their own compromises, a household member who
  shouldn't have admin access, a compromised laptop already on the
  network. This is the primary threat this ADR needs to address —
  Console living on the LAN doesn't mean everyone reachable on the LAN
  should be able to trigger updates or restores.
- **A LAN-adjacent attacker via a compromised browser session** (e.g. a
  malicious web page open in the same browser as an authenticated Console
  session performing a request against `sovereign.local` — CSRF-shaped),
  independent of whatever auth mechanism is chosen.
- **Brute-force or credential-stuffing** against whatever credential is
  chosen, if the device is ever port-forwarded or otherwise made reachable
  from outside the LAN despite guidance not to (operators do this in
  practice more often than documentation assumes).
- **Remote unauthenticated exploitation** of Console itself (a
  vulnerability in the auth mechanism or the app) — the highest-severity
  but hopefully lowest-likelihood case, and the main argument for keeping
  the mechanism as simple and well-trodden as possible rather than a
  bespoke scheme.

This is a materially different threat model than ADR-0006's signing key
(which must resist a targeted, motivated attacker seeking to compromise
*every* device trusting that key). Console auth mainly needs to resist
casual/opportunistic access from other LAN parties and defend in depth
against the LAN boundary itself failing, not a nation-state adversary. That
should shape session length, brute-force protection, and mechanism
complexity toward "solid and standard," not maximal.

### Constraints already fixed by the existing design

- Nginx is the only LAN-facing HTTP service (ADR-0005); any auth mechanism
  is enforced there or in whatever Console backend Nginx proxies to, not
  scattered across services.
- The health API backend is intentionally unprivileged and loopback-only.
  Any mutating Console backend that calls into `sovereign-update` needs at
  minimum a way to invoke a privileged action from an unprivileged web
  request — the auth mechanism and that privilege boundary are related but
  distinct problems; this ADR addresses who's allowed to ask, not how the
  ask reaches root.
- An OS-level admin account (`sovereign`) already exists with SSH access
  and a mandatory first-login password-change flow (see
  [docs/operations/first-login-and-network-setup.md](../operations/first-login-and-network-setup.md)).
  It is the only credential concept that exists on the device today.
- The Pi-hole admin password is already a **separate** credential from the
  Linux account password, by deliberate existing design (same document,
  section 3: "The Linux login password and Pi-hole password remain
  separate"). Any new Console credential adds a third, unless it's
  explicitly tied to one of the first two.
- No web session, cookie, or login-form infrastructure exists anywhere in
  the appliance today — this would be new surface however it's built.

## Decision

The project owner accepted the Initial Recommendation below: **Option B
(separate Console-specific credential) delivered as Option C (session-based
login)**, with Option D (mTLS) left open as a future defense-in-depth layer
rather than a starting requirement.

Implemented as:

- A distinct credential, `pbkdf2_sha256`-hashed (600,000 iterations, stdlib
  `hashlib.pbkdf2_hmac`, no external dependency) at
  `/data/sovereign/console/admin-password.hash`, set via a new
  `sovereign-console-password` command mirroring `sovereign-pihole-password`'s
  interactive, minimum-12-character, atomic-replace pattern.
- A new loopback-only, systemd-hardened backend, `console-auth`
  (`sovereign-console-auth.service`, port 8091), proxied by Nginx at
  `/api/v1/auth/login`, `/api/v1/auth/logout`, and `/api/v1/auth/session` —
  the same shape as the existing `console-health` service.
- Session-based login: an `HttpOnly`, `SameSite=Strict` cookie (no `Secure`
  attribute, since Nginx has no TLS listener to protect against — see the
  service's own comment on this), an 8-hour default session lifetime, and a
  CSRF token returned at login and required via `X-CSRF-Token` on mutating
  requests (currently just `logout`).
- Rate limiting without lockout, per the Session Length and Brute-Force
  Considerations above: 5 failed attempts per source IP within 5 minutes
  triggers an increasing `Retry-After` delay rather than blocking the
  legitimate owner out.
- A dedicated `sovereign-console` system group (declared via
  `systemd-sysusers.d`) grants the auth service's `DynamicUser` read access
  to the credential file without widening the existing, separately-owned
  `/data/sovereign/secrets/` directory Pi-hole's own credential lives under.

A Console sign-in UI (login form, session restore on page load, sign-out)
now calls this backend from the topbar, always through same-origin `fetch`
with `preventDefault()`, respecting the page's `form-action 'none'` CSP.

Hardware-qualified on Raspberry Pi 5: the full login/session/CSRF/logout/
rate-limiting flow, and the interactive `sovereign-console-password` script
under a real pty, both verified against the real deployed service behind
the real Nginx proxy, with the device fully reverted to its exact prior
state (all four modified files restored byte-identical from the real
`v0.1.0-preview.17` release bundle) afterward — see the
[hardware qualification report](../research/console-authentication-hardware-qualification-report.md).

**Explicitly not yet done, and deliberately out of this pass's scope** per
this ADR's own boundary ("this ADR addresses who's allowed to ask, not how
the ask reaches root"):

- No mutating action exists yet for this auth layer to gate — Console
  remains read-only in practice until the "Update Discovery and Console
  Controls" milestone wires an actual `sovereign-update` action behind it,
  which needs its own follow-up design work for the privilege-escalation
  path from this unprivileged backend to a root update action.
- Has only ever been deployed manually for qualification — a real signed
  release attempt (`v0.1.0-preview.18`) was rejected at `stage`, not
  because of anything specific to Console auth, but because it's the
  first release to add a new appliance file since the installed
  updater's file allowlist was fixed at flash time — see
  [the finding](../research/appliance-file-set-update-ceiling-finding.md).
  Console auth cannot ship through a real install until that's resolved.

## Options

### Option A — Reuse the OS-level `sovereign` account credential

Console prompts for the Linux account username/password (validated via PAM
or an equivalent local check) and issues a session cookie on success.

- **No new credential to create, remember, or leak** — one password to
  compromise a device's DNS and its update system, whether over SSH or
  Console.
- Matches the mental model the first-login flow already establishes: "the
  `sovereign` account is the device."
- **Downsides:** couples two different trust boundaries (remote shell
  access and web-triggered update/restore actions) to a single secret. A
  password chosen for SSH convenience becomes the same password gating
  destructive update actions from a browser, and vice versa. If Console's
  web auth is ever compromised through a mechanism-specific bug, SSH
  access is compromised too. Also needs a real mechanism to check a Linux
  password from an unprivileged web backend (PAM binding, or shelling to
  a small privileged helper) — nontrivial new attack surface of its own.

### Option B — Separate Console-specific credential

A distinct username/password (or passphrase-only) pair, set on first use of
any mutating Console action, stored as its own hashed secret (e.g.
`/data/sovereign/secrets/console-admin-password`, mirroring how the Pi-hole
password is already stored separately from the Linux one).

- Keeps the three trust boundaries (SSH, Pi-hole, Console) cleanly
  separated, matching the precedent the Pi-hole password already set.
- Compromise of one credential doesn't hand over the others.
- **Downsides:** a third credential for the household to manage and not
  lose; needs its own first-set/reset flow analogous to first-login and the
  Pi-hole password script; if forgotten, needs its own recovery path (SSH
  in and reset it, similar to `sovereign-pihole-password`).

### Option C — Session-based login (cookie + server-side session state)

Either credential model above, but formalized as a real login: a login
form, a signed/opaque session cookie with an expiry, server-side (or
signed-stateless) session validation on every mutating request, and logout.

- The standard, well-understood web pattern; easiest for a solo maintainer
  to implement correctly using existing libraries rather than inventing
  something bespoke.
- Naturally supports session expiry (defense-in-depth against a left-open
  browser tab) and CSRF-token pairing to address the CSRF-shaped risk noted
  in Threat Model above.
- **Downsides:** is a login *system*, not just a check — needs secure
  cookie flags, CSRF protection, session storage/expiry, and rate-limiting
  on the login endpoint itself to resist brute-force. More to build and
  more to get subtly wrong than a stateless check, though this is well-worn
  ground with existing patterns to copy correctly rather than invent.

### Option D — mTLS / client certificate

Console requires a client certificate issued by a device-local CA; only
browsers/devices provisioned with that certificate can reach mutating
endpoints (or Console at all).

- **Strong protection against casual/opportunistic LAN access** — a device
  without the certificate can't even open a login prompt to attack.
- No password to phish, brute-force, or forget.
- **Downsides:** by far the most operationally heavy option for a
  household user: generating, installing, and trusting a client
  certificate in a browser is not something most non-technical users have
  ever done, and there's no existing UX precedent in this project for it.
  Needs a local CA the device stands up and manages (its own smaller
  version of the ADR-0006 key-custody problem). Losing the certificate (a
  wiped phone, a reinstalled browser) means a new SSH-gated
  re-provisioning step just to view Console again, which is a heavy cost
  for what today is *read-only* health browsing on devices that haven't
  needed any credential at all. Best suited as a defense-in-depth layer
  once Console has other auth, not as the sole mechanism, given the
  household-usability bar this project has held elsewhere (e.g. Wi-Fi
  setup and first login are both designed to be copy-pasteable from a
  terminal, not requiring cert tooling).

### Option E — HTTP Basic Auth at the Nginx layer

Nginx enforces `auth_basic` with an `htpasswd`-style file in front of
mutating routes (or all of `/console/`), no application-level session code
at all.

- Minimal new code — Nginx already terminates every LAN request (ADR-0005)
  and already has this module built in.
- Simplest possible mechanism to reason about and audit.
- **Downsides:** no real session concept (browsers cache Basic Auth
  credentials per-origin until closed, with inconsistent "logout" UX
  across browsers), no built-in brute-force throttling without additional
  Nginx config (`limit_req`), and it trains users to type a password into
  a plain, un-styled browser prompt rather than a page that's clearly part
  of the product — a worse fit for a project that has otherwise built a
  deliberate, calm Console UI (see
  [docs/design/console-health.md](../design/console-health.md)).

## Initial Recommendation

Leaning toward **Option B (separate Console-specific credential) delivered
as Option C (proper session-based login)** as the best fit for this
project's scale and existing precedent, with Option D (mTLS) worth
revisiting later as an optional defense-in-depth layer rather than the
starting mechanism:

- Option B keeps faith with a pattern the project has already chosen once
  (Pi-hole's password is deliberately separate from the Linux one) rather
  than introducing the first place where a single credential spans both
  shell and web access. A Console-triggered `restore` or `rotate-trust`
  going wrong is a different blast radius than an SSH session, and they
  arguably deserve independent credentials the same reasoning already gave
  Pi-hole.
- Option C is recommended over Option E specifically because Console's
  mutating actions (update install, restore, trust rotation) are
  meaningfully higher-consequence than "view an admin dashboard," and this
  project has already invested in Console being a deliberate, calm product
  surface rather than infrastructure plumbing (ADR-0005's own rejected
  alternatives explicitly ruled out a container-management-style
  dashboard) — a real login page fits that better than a browser-native
  Basic Auth prompt, and session expiry plus CSRF protection are worth the
  modest extra implementation cost given what a successful CSRF-shaped
  request could trigger.
- Option A is not recommended as the primary mechanism because it
  collapses two independently-useful trust boundaries (remote shell,
  web-triggered mutation) into one secret, for a marginal convenience gain
  (one password to remember instead of two) that this project has already
  decided against once for Pi-hole.
- Option D is not recommended as the *starting* mechanism given the
  household-usability bar evident elsewhere in this project's own
  documentation (first login and Wi-Fi setup are both designed to be
  copy-paste simple), but is worth a later look once Console's privileged
  surface is large enough to justify the setup cost, especially if the
  device is ever expected to be reachable beyond the LAN.

This recommendation is offered for the project owner's judgment, not as a
default to implement without review.

## Session Length and Brute-Force Considerations

Whichever option is chosen, given the LAN-primary threat model above:

- A moderate session length (hours, not minutes, and not "forever") is
  reasonable for a trusted-household-LAN default — this is not a banking
  app — but sessions should still expire, and any mutating action
  (`activate`, `restore`, `rotate-trust`) is a reasonable point to require
  fresh confirmation regardless of session freshness, mirroring how
  `rotate-trust`'s own lockout check already refuses actions that would
  leave a device unable to trust future updates (ADR-0006's Rotation
  section) — Console's auth layer should have an equivalent "don't let one
  mistake brick the device" instinct.
- Basic rate-limiting on the login endpoint (Nginx `limit_req` or
  equivalent) is worth doing regardless of mechanism — it's cheap defense
  against both a compromised LAN device and the "someone port-forwards
  this against documented guidance" case.
- No lockout-after-N-failures policy is recommended by default, to avoid a
  denial-of-service where a malicious LAN device locks the legitimate
  owner out of their own appliance; rate-limiting (slowing attempts) is
  preferred over lockout (blocking the owner) at this threat level.

## Credential Reset / Recovery Considerations

Analogous to Rotation/Revocation in ADR-0006, but for a login credential
rather than a signing key:

- Whatever credential is chosen needs an SSH-gated reset path from the
  existing `sovereign` account, mirroring `sovereign-pihole-password` —
  losing the Console credential should never require a reflash the way
  losing the *only* trusted update-signing key would (ADR-0006's Recovery
  section).
- If Option A is chosen instead of the recommendation above, resetting the
  Linux password already resets Console access as a side effect — worth
  flagging as exactly the coupling this ADR recommends against.
- A compromised Console credential (e.g. a household member's laptop with
  a saved session gets compromised) should be recoverable by invalidating
  all existing sessions on password change, the same way changing a
  website password today typically signs out other devices.

## Consequences

### Positive

- Unblocks the "Update Discovery and Console Controls" milestone's
  Console-facing bullets (RFC-0015's explicitly deferred UI and
  installation-triggering scope) and any future Console-surfaced Pi-hole
  admin actions.
- Gives Console a deliberate, documented auth boundary instead of an
  implicit "we'll figure it out later" gap, matching how ADR-0006 closed
  the equivalent gap for signing-key custody.
- Establishes a precedent (separate-per-surface credentials) that keeps
  future privileged surfaces from defaulting to reusing the SSH password
  by inertia.

### Negative

- Whichever option is chosen adds real implementation surface (login flow,
  session or credential storage, reset path) that does not exist in the
  appliance today — nothing about this ADR is free.
- A new credential is another thing a household can lose, forget, or reuse
  insecurely across services, the same usability cost every new credential
  carries.

### Risks

- Building session/login infrastructure from scratch (Option C) risks
  subtle security bugs (session fixation, insufficient entropy, missing
  CSRF protection) if not built carefully — favor well-worn libraries or
  patterns over a bespoke scheme.
- Choosing Option A for short-term convenience quietly re-couples SSH and
  Console access, undermining the separation this ADR otherwise
  recommends; if that trade is made deliberately it should be recorded as
  such, not accidental.
- Whatever mechanism is chosen must be re-verified once Console actually
  starts calling `sovereign-update` subcommands — this ADR reasons about
  the auth boundary in the abstract but does not itself qualify the
  privilege-escalation path from an unprivileged Console backend to a root
  update action; that remains a separate, necessary design step even
  after this ADR is decided.

## Alternatives Considered

### No authentication; keep Console read-only indefinitely

Rejected as a long-term stance — it's exactly the state ADR-0005 already
described as temporary ("Authentication is required before settings,
restarts, updates, credential changes... are added"), and the ROADMAP
already commits to Console-triggered update installation as a named
milestone outcome. Deferring this ADR further only delays a decision the
project has already signaled it needs to make.

### OAuth / third-party identity provider

Rejected outright as inconsistent with this project's stated
self-sufficiency values (the same reasoning ADR-0006 applied to reject
cloud KMS for signing-key custody) and wildly disproportionate for a
single-household, single-admin appliance with no multi-tenant concept.

## Validation and Revisit Conditions

Revisit this ADR if: Console's privileged surface grows enough that a
single flat credential feels insufficient (e.g. multiple household members
needing different privilege levels, which would favor a small role
concept this ADR does not attempt to design), the device is ever expected
to be reachable beyond the LAN by design rather than by accident (which
would favor Option D or at least mandatory rate-limiting/lockout
hardening beyond what's recommended here), or implementation reveals that
the chosen mechanism can't cleanly gate the privilege-escalation path into
`sovereign-update` (which would need its own follow-up design work
regardless of which auth option is chosen here).
