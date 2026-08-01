# ADR-0008: Console Privileged Action Invocation

**Status:** Accepted
**Date:** 2026-08-01
**Decision owner:** Project creator (delegated to the assistant for this
decision — see Decision below)
**Related ADR:** [ADR-0007](0007-console-authentication.md)
**Related RFCs:** [RFC-0014](../rfcs/0014-appliance-update-system.md), [RFC-0015](../rfcs/0015-update-discovery.md)
**Related milestone:** [Update Discovery and Console Controls](../../ROADMAP.md)
**Supersedes:** None

## Context

ADR-0007 gave Console a real login/session mechanism but explicitly left
one problem unsolved: *"this ADR addresses who's allowed to ask, not how
the ask reaches root."* `console-auth` runs as an unprivileged,
`DynamicUser`, `NoNewPrivileges=yes`, `ProtectSystem=strict` service — by
design, the same hardening every other Console-adjacent process gets. It
has no path today to actually cause `sovereign-update` (which requires
root — `fail(os.geteuid() == 0, "ROOT_REQUIRED", ...)` guards every
mutating subcommand) to do anything.

RFC-0015 already deferred Console-triggered update actions pending
exactly this ADR. This decision covers two things together, since the
mechanism chosen constrains what can safely be exposed:

1. **How** an authenticated Console session gets a privileged action to
   actually happen, without widening `console-auth`'s own privilege.
2. **What** the first action exposed this way should be.

### What this actually protects

Once any authenticated session can cause a root action, the question is
the same shape as ADR-0007's: not protecting a secret, but gating *who is
allowed to cause state change*, now one layer deeper — from "who can
open an authenticated session" to "what can an authenticated session
actually make root do." A bug in the invocation mechanism itself could
let a compromised or buggy `console-auth` process (still just a web
server parsing untrusted HTTP requests) escalate arbitrary root
execution, which would undo everything `NoNewPrivileges`/`DynamicUser`/
`ProtectSystem=strict` are there to contain.

## Decision

**File-trigger + a `systemd` path-activated, root-owned oneshot runner**,
scoped for now to exactly one action: `sovereign-update check`. This
decision was delegated to the assistant by the project owner ("write
ADRs and start working in them after") rather than reviewed line-by-line
before acceptance, unlike ADR-0006/0007 — recorded here for anyone
auditing this decision's provenance later.

- `console-auth`, after verifying session + CSRF exactly like `logout`
  already does, writes an empty trigger file to
  `/data/sovereign/console/actions/check.request`. It has group-write
  access to that directory (`sovereign-console-secrets`, mode `0730` —
  write and traverse, no read) and nothing more; it cannot read the
  directory's contents, cannot invoke anything else. `ReadWritePaths=`
  for that one directory was added to its otherwise-unchanged hardening.
- A `systemd` `.path` unit
  (`sovereign-console-check-trigger.path`, `PathExists=`) watches for that
  file and activates a oneshot `.service`
  (`sovereign-console-check-trigger.service`) running as root. The
  service's only job: remove the trigger file, then run
  `sovereign-update check`. Nothing about the trigger file's content is
  trusted or parsed — its mere existence is the only signal, so there is
  no request format for a compromised writer to abuse beyond "cause
  `check` to run," which is already something `sovereign-update-check.timer`
  does unattended, daily, for every device.
- Reading the result stays fully separate from triggering it, and stays
  unauthenticated: `/data/sovereign/update-check.json` was already
  designed world-readable, non-sensitive output (RFC-0015). `console-health`
  (already unprivileged, already loopback-only, already the read-only
  status surface) now also serves it, unauthenticated, exactly like every
  other health field. Only *causing a new check to run* costs anything
  (a live GitHub API call) and is worth gating; reading the last result
  costs nothing and was never meant to require a login.
- Client-side triggering is additionally rate-limited (one trigger per 60
  seconds, enforced in `console-auth`'s existing in-memory rate-limit
  style) to bound how often an authenticated session can force a live
  GitHub API call.

Scope, deliberately narrow: **only `check` is wired this way in this
pass.** `prepare`/`backup`/`stage`/`activate` (an actual Console-triggered
*install*) are explicitly out of scope here — they have a materially
larger blast radius (data migration risk, service interruption, the
whole health-gated rollback machinery), deserve their own confirmation
UX and progress-reporting design, and should not inherit this decision by
default just because the plumbing now exists. Extending this mechanism to
install-triggering needs its own revisit (see Validation and Revisit
Conditions).

## Options

### Option A — `sudo` with a narrow `NOPASSWD` rule

`console-auth` execs `sudo -n /usr/sbin/sovereign-update check` under a
`/etc/sudoers.d/` rule scoped to exactly that command.

- **Rejected outright, not just deprioritized:** `console-auth` runs under
  `DynamicUser=yes`, which assigns a *new random username* on every
  service start. A static `sudoers` rule cannot reference a username that
  doesn't exist yet at write time and changes on every restart. Using
  this option would require first moving `console-auth` off
  `DynamicUser` onto a static system account — a real hardening
  regression (losing UID/GID randomization and the extra isolation
  `DynamicUser` provides) paid just to make `sudo` work, not because a
  static account is otherwise desirable here.

### Option B — a socket-listening privileged helper daemon

A new root-owned service listens on a Unix domain socket (or loopback
TCP, like `console-health`/`console-auth` already do); `console-auth`
connects and sends a small authenticated-locally request.

- Workable, and closer to conventional service-to-service design.
- **Not chosen:** needs a request protocol (parsing, versioning, a second
  place a malformed message can be mishandled), a persistently-running
  root process idle most of the time, and its own socket-permission
  hardening — meaningfully more surface than "does a specific file exist"
  for a feature whose entire initial scope is "run one specific,
  argument-free command." Worth reconsidering if/when this needs to carry
  real parameters (see Revisit Conditions).

### Option C — PolicyKit (`polkit`)

Define a `polkit` action and policy; `console-auth` requests it via
`pkexec` or D-Bus.

- The standard Linux-native answer to exactly this class of problem.
- **Not chosen:** introduces a `polkit`/D-Bus dependency this project has
  deliberately avoided everywhere else — `sovereign-update`,
  `console-health`, and `console-auth` are all dependency-free stdlib
  Python by explicit, consistent choice throughout this codebase. Adding
  the first non-stdlib runtime dependency for one narrow trigger is
  disproportionate, and a minimal appliance image is exactly the kind of
  project where every added always-running system service has a real,
  ongoing image-size and attack-surface cost.

### Option D — file-trigger + `systemd` path-activated oneshot runner (chosen)

Described in Decision above.

- No listening socket, no persistently-running privileged process (the
  oneshot only exists while handling one request), no request protocol
  to parse or version — the trigger file's *existence*, not its content,
  is the entire signal.
- Matches this codebase's existing durable-file-state idioms closely
  (`sovereign-update`'s own atomic transaction journal, the `.timer` units
  already running `sovereign-update check`/`prune` as root on a schedule
  — this is the same pattern, just event-triggered instead of
  time-triggered).
- **Downside:** doesn't generalize cleanly to actions that need real
  parameters (e.g., "restore *this specific* backup ID") without adding a
  request format later — acceptable now because the one action in scope
  takes none, but a real constraint to weigh before extending this to
  more than `check`.

## Consequences

### Positive

- `console-auth` gains zero new privilege — it can cause exactly one
  specific root command to run, with a mechanism where the untrusted
  input surface (an HTTP request handled by unprivileged code) is
  separated from the trusted action (a root process that trusts nothing
  but a file's existence) by a boundary neither side can widen from where
  it sits.
- Unblocks the first genuinely useful thing an authenticated Console
  session can do, closing part of the "Update Discovery and Console
  Controls" milestone.

### Negative

- Two new systemd units, a new directory with its own permission model,
  and a new endpoint pair (trigger + read) are real new surface, on top
  of everything ADR-0007 already added.
- The file-existence-only protocol is deliberately inflexible; extending
  it to parameterized actions is a real, separate design cost later, not
  a small addition.

### Risks

- If the `.path`/`.service` pairing is misconfigured, the realistic
  failure mode is "trigger silently does nothing" (fails safe) rather
  than an unintended privilege escalation — worth confirming directly in
  hardware qualification rather than assuming from the unit file alone.
- A compromised `console-auth` process, even though it cannot itself gain
  privilege, *can* still repeatedly write the trigger file — bounded by
  the 60-second client-side rate limit, but that limit lives in the same
  process being assumed compromised in this threat scenario. The real
  backstop is that the only consequence of unlimited triggering is
  unlimited `sovereign-update check` runs — already a command safe to run
  arbitrarily often (RFC-0015: read-only discovery, no mutation).

## Alternatives Considered

### Skip the mechanism question; hardcode a one-off for `check` only

Rejected — the actual hard problem (how does unprivileged Console code
ever safely reach root) doesn't go away by special-casing one command; it
would just resurface, unexamined, the moment a second action is needed.

## Hardware Qualification

Hardware-qualified on Raspberry Pi 5, deployed permanently alongside the
already-live Console authentication — see the
[qualification report](../research/console-check-trigger-hardware-qualification-report.md).
The full real chain (unauthenticated rejection, CSRF enforcement,
trigger, the `.path`/`.service` pair actually firing and running
`sovereign-update check` as root, the result appearing in
`/api/v1/update/check`, cooldown enforcement) verified correctly — after
fixing two real defects design review alone didn't catch: the auth
service's unit was missing `ReadWritePaths=` for the new trigger
directory (silent `503` on every write), and the static group backing it
was named `sovereign-console` — colliding with `sovereign-console.service`'s
(unrelated `console-health`) own `DynamicUser`-derived identity, breaking
that pre-existing service's ability to restart at all. Renamed to
`sovereign-console-secrets` throughout.

## Validation and Revisit Conditions

Revisit this ADR before extending this mechanism to any action that:
takes parameters (a specific backup ID, a specific target version); has a
blast radius beyond "runs a read-only discovery check" (anything in the
`prepare`/`backup`/`stage`/`activate`/`restore`/`rotate-trust` family);
or needs to report granular in-progress status back to Console rather
than a single before/after result file. Any of those likely favors Option
B (a real request protocol) over continuing to stretch Option D's
file-existence-only signal.
