# ADR-0009: Console-Triggered Update Install

**Status:** Accepted
**Date:** 2026-08-01
**Decision owner:** Project creator (delegated to the assistant for this
decision, same as ADR-0008 — see Decision below)
**Related ADRs:** [ADR-0007](0007-console-authentication.md), [ADR-0008](0008-console-privileged-action-invocation.md)
**Related RFCs:** [RFC-0014](../rfcs/0014-appliance-update-system.md), [RFC-0015](../rfcs/0015-update-discovery.md)
**Related milestone:** [Update Discovery and Console Controls](../../ROADMAP.md)
**Supersedes:** None

## Context

ADR-0008 wired the first Console-triggered privileged action —
`sovereign-update check` — through a deliberately minimal mechanism: an
empty trigger file whose mere existence, not content, is the only signal
a root-owned `systemd` path unit trusts. It explicitly scoped out
anything bigger, and named exactly why in its own Revisit Conditions:
an action that takes a parameter, has a blast radius beyond a read-only
check, or needs granular progress reporting should not just reuse that
same file-existence trigger.

Installing an update — `prepare` → `backup` → `stage` → `activate` — hits
all three:

- **Parameter-shaped**, naively: which version to install.
- **Real blast radius**: Pi-hole is quiesced during backup, the whole
  device briefly loses DNS during activation, and a failed step can leave
  a transaction in `recovery_required` needing operator attention.
- **Genuinely long-running and multi-stage**: unlike `check` (seconds, one
  outcome), an install runs through several durable transaction states
  over what could be minutes, downloading a multi-ten-megabyte bundle
  along the way.

RFC-0015 already named the target policy: **notify and require approval**,
never automatic download-and-install. This ADR is about what "require
approval" concretely means for Console specifically.

## Decision

**Reuse ADR-0008's exact mechanism (file-existence trigger + `systemd`
path-activated root oneshot) for the *trigger*, but resolve the
"takes a parameter" problem by giving it none** — the privileged side
independently re-decides which release to install using the same
trust-anchored discovery `check` already performs, never trusting
anything Console sends beyond "the user asked to install." This decision
was delegated to the assistant by the project owner, the same as
ADR-0008 — recorded here for provenance, not reviewed line-by-line before
acceptance.

- A new `sovereign-update install` subcommand does the actual work, all
  inside the same root-owned, already-trusted binary: re-runs the *exact*
  discovery and signature-verification logic `check` already uses
  (`fetch_release_candidates`/`evaluate_release_candidate`, unchanged),
  then — only once a candidate re-verifies — downloads its update bundle,
  and finally calls the *existing* `prepare_update`/`create_backup`/
  `stage_release`/`activate_release` functions in sequence, the same code
  every manual, already-hardware-qualified install has always run. No new
  trust logic, no new state machine: this command is an orchestrator over
  already-qualified primitives, not a new way of installing anything.
- `console-auth` gets `POST /api/v1/console/actions/install`, writing
  `/data/sovereign/console/actions/install.request` — same file-existence
  signal, same shape as `check`'s trigger, different file and a different
  `.path`/`.service` pair (`sovereign-console-install-trigger.*`).
- **Unlike `check`, this endpoint requires the password again**, not just
  a valid session — re-verified against the stored credential exactly
  like login does, discarded immediately after (never stored, never
  becomes part of the session). This is ADR-0007's own already-recorded
  guidance acted on for the first time: *"any mutating action (`activate`,
  `restore`, `rotate-trust`) is a reasonable point to require fresh
  confirmation regardless of session freshness."* A stolen or
  left-open browser session alone is not enough to trigger a real
  install.
- Only proceeds if `/api/v1/update/check`'s last result says
  `update_available` — Console cannot force-install against a device that
  hasn't itself already found and verified a candidate; it can only ask
  the device to do what it already told the user was available.
- **Progress reporting reuses existing state, not new plumbing**:
  `prepare`/`backup`/`stage`/`activate` already write
  `/data/sovereign/update-status.json` at every transition (RFC-0014).
  `console-health` now also serves that file's content, unauthenticated
  (`GET /api/v1/update/status`), the same non-sensitive-status reasoning
  as `/api/v1/update/check`. Console polls this to show real progress
  instead of a single before/after result.
- **No per-step Console control.** The install runs `prepare` → `backup`
  → `stage` → `activate` as one continuous, non-interactive sequence once
  triggered — not four separate Console-driven steps. `activate`'s
  existing health gate and automatic rollback remain the only safety net
  mid-sequence, exactly as they are for a manually-run install today.
  This matches ordinary consumer-OS "install update" UX (one click, one
  outcome) rather than exposing the transaction state machine as
  something Console operates directly.

## What this actually protects

The same shape of question ADR-0007 and ADR-0008 both asked: not a
secret, but who's allowed to cause state change, and how much state
change one click can cause. `check`'s worst case was an extra GitHub API
call. This action's worst case is real: Pi-hole downtime during
activation, and — if a step fails outside `activate`'s own health gate —
a transaction stuck needing an operator's SSH session to resolve. The
fresh-password requirement and the "only if already discovered" guard
both exist specifically to raise the bar above "a valid cookie," given
that higher real cost.

## Options

### Option A — Extend ADR-0008's trigger mechanism unchanged, with a version parameter in the trigger file (rejected)

Write the target version into the trigger file instead of leaving it
empty; the root-owned runner reads and acts on it.

- **Rejected:** the entire point of the file-existence-only design in
  ADR-0008 was that the trigger's *content* is never trusted — the
  moment content is trusted, `console-auth` (unprivileged, parsing
  untrusted HTTP input) becomes able to influence *which* root action
  happens, not just *whether* one happens. Any bug in that parsing path
  becomes a privilege-relevant bug. Not worth it when the alternative
  (the privileged side re-decides the target itself, from the same
  trust-anchored source `check` already uses) has no such risk and costs
  nothing extra.

### Option B — A real request/response protocol (socket or queue), per ADR-0008's own Revisit Conditions

Build the general request-protocol mechanism ADR-0008 flagged as the
right answer once an action needs real parameters or granular status.

- The conceptually "correct" next step ADR-0008 explicitly anticipated.
- **Not chosen for this specific action**, because it turns out this
  action doesn't actually need a parameter once framed correctly (see
  Decision) — the file-existence trigger still works, it's just paired
  with existing-file-based status reporting instead of a live status
  channel. Worth building for a future action that genuinely can't avoid
  taking a parameter (e.g., restoring one specific backup among several).

### Option C — Console orchestrates each step itself (separate triggers for prepare/backup/stage/activate)

Expose four separate trigger actions; Console (or its user) confirms
each one in sequence.

- Gives the most visibility and the most points to abort.
- **Rejected** as the wrong default UX for this project's stated policy
  (RFC-0015: notify and require approval — one approval, not four) and
  disproportionate complexity for a first pass; the four-step machinery
  already exists for CLI/operator use and remains available there for
  anyone who wants that granularity.

## Consequences

### Positive

- No new trust logic anywhere: `install` is a thin orchestrator over
  already-hardware-qualified functions, verifying with the exact same
  code path `check` and every manual install this whole project has ever
  used.
- Closes the last named gap from ADR-0007's original scope note ("how
  the ask reaches root") for the one action that actually matters to a
  household user: getting an update installed without SSH.
- The fresh-password requirement and discovery-gate ("must already say
  `update_available`") are both free — no new mechanism, just reusing
  what already exists (login verification, `check`'s own result file).

### Negative

- `sovereign-update install` is real new code — a network download of a
  large artifact from inside a command that previously never fetched
  more than a small manifest/signature, and a new orchestration path
  through four existing functions that have only ever been called
  individually, by an operator, with time to react between each. That
  sequencing itself needs its own hardware qualification, not just each
  step in isolation.
- A failed install still leaves an operator-recovery case
  (`recovery_required`) that Console cannot resolve — "retain a CLI
  recovery path independent of Console" (already a stated ROADMAP
  requirement) remains load-bearing, not optional, once this ships.

### Risks

- Running `prepare`→`backup`→`stage`→`activate` back-to-back with no
  human in the loop between steps is qualitatively different from every
  prior qualification campaign this session, which always ran them one
  command at a time with a person watching. The full sequence needs its
  own explicit hardware qualification pass, not an assumption that
  "each step already works" implies the sequence does.
- A large, previously-untested download path (the update bundle, tens of
  megabytes, over a live network connection from inside `sovereign-update`
  itself for the first time) is new attack surface for resource
  exhaustion or a stalled/partial download — needs explicit size and
  timeout bounds, not just reuse of the small-asset `http_get_bytes`
  limits `check` uses today.

## Alternatives Considered

### Wait for ADR-0008's Option B (a real protocol) before doing anything

Rejected — as Decision explains, the version-parameter problem that would
have required it dissolves once the privileged side is designed to
re-decide the target itself. Building request/response machinery now
would be solving a problem this specific action doesn't actually have.

## Validation and Revisit Conditions

Revisit this ADR if: a future action genuinely cannot avoid taking a
Console-supplied parameter (e.g., "restore backup `X`" where `X` must
be one of several real choices, not "whatever's already verified") — that
needs Option B. Also revisit if hardware qualification of the full
`prepare`→`activate` sequence surfaces a failure mode specific to running
it unattended (no operator watching between steps) that the individually-qualified
steps never exercised.
