# Sovereign OS Roadmap

## Status Legend

- ✅ Complete — implemented and qualified on supported hardware
- 🟡 In progress — implementation or hardware qualification is active
- ⚪ Planned — accepted direction, not yet started
- ⏳ Pending decision — research or an RFC must close the design boundary

## Current Position

✅ Phase 01 — Flashable Raspberry Pi Image POC

The Raspberry Pi 5 image build, flash, first-boot, Pi-hole, persistent DATA
partition, local routing, first-login, and Sovereign Console health experience
have been exercised on physical hardware.

✅ Milestone 01.1 — Appliance Update Foundation

The signed appliance updater can inspect, prepare, back up, stage, activate,
health-check, commit, recover, and roll back versioned releases while preserving
the dedicated DATA partition. An initial signed update transaction passed
Raspberry Pi qualification.

The first fully versioned appliance-release qualification, from preview.9 to
preview.10, exposed service-readiness and systemd dependency races. Automatic
rollback worked and restored preview.9. The fixes were qualified on Raspberry
Pi 5 hardware in a clean preview.11 base to preview.12 update campaign: an
interrupted-at-`validating` recovery, a forced target-health rollback, and a
successful activation all held with reboot persistence and no regression to
Console, DNS, Pi-hole, Nginx, SSH, credentials, or the dedicated DATA
partition. See the
[preview.12 appliance update qualification report](docs/research/preview-12-appliance-update-qualification-report.md).

Persistent-data restore, bounded retention (`prune`), and signed trust
rotation (`rotate-trust`) are all implemented and hardware-qualified on
Raspberry Pi 5, most recently against a real `0.1.0-preview.13` base image
built and flashed with all three shipped in for the first time — see the
[preview.14 appliance update qualification report](docs/research/preview-14-appliance-update-qualification-report.md)
and the
[prune and trust rotation hardware qualification report](docs/research/prune-and-rotate-trust-hardware-qualification-report.md).
Production signing-key custody is decided (ADR-0006), and the production
key (`sovereign-production-1`) is now generated, provisioned into the
image-builder trust store, and proven end-to-end: `v0.1.0-preview.17` is
a real production-signed release that has been built, published,
discovered, installed, and restored from on Raspberry Pi 5 hardware —
see the
[first production-signed release](docs/research/first-production-signed-release-qualification-report.md),
[install](docs/research/first-production-signed-release-install-qualification-report.md),
and
[restore](docs/research/production-signed-restore-qualification-report.md)
qualification reports. `prune` and `rotate-trust` have since each been
exercised as part of a real signed-release install cycle — `prune`
against `v0.1.0-preview.23`, and `rotate-trust` with the real production
key against the device's real trust store on 2026-08-09 — see the
[rotate-trust real signed-cycle qualification report](docs/research/rotate-trust-real-signed-cycle-qualification-report.md).
[RFC-0014](docs/rfcs/0014-appliance-update-system.md) is formally
Accepted. See Milestone 2 below for the full closing summary.

Unattended automatic installation remains disabled until the manual,
health-gated update path and its operational controls are qualified.

## Milestone Sequence

### 1. Complete Appliance Update Qualification

**Status:** ✅ Complete

**User outcome:** Install a compatible Sovereign appliance release without
reflashing or losing persistent data.

Qualification pair:

- preview.11: clean flashable base containing the systemd and readiness fixes;
- preview.12: signed, versioned installed-device update built from the same
  source revision.

The physical qualification on Raspberry Pi 5 proved:

- update compatibility and signature verification;
- staging without changing the active release;
- interruption recovery (interrupted at `validating`, automatic boot-time
  restore of preview.11);
- forced health-check failure and automatic rollback;
- successful activation and commit;
- reboot persistence;
- preservation of Pi-hole configuration, credentials, update state, and the
  dedicated DATA mount; and
- no regression to Console, DNS, Pi-hole, Nginx, or SSH.

See the
[preview.12 appliance update qualification report](docs/research/preview-12-appliance-update-qualification-report.md)
for full evidence.

### 2. Production Update Operations

**Status:** ✅ Complete — every item below is implemented and
hardware-qualified, including the three gaps that were still open as of
early 2026-08-09: `restore`-into-rollback wiring is recorded as a
deliberate deferral rather than left ambiguous (nothing in the update
pipeline touches persistent data yet, so there is nothing for it to
protect against), a genuine unattended `prune` timer fire was observed,
and `rotate-trust` has now been exercised with the real production key
against the real device trust store. [RFC-0014](docs/rfcs/0014-appliance-update-system.md)
is formally Accepted, closing the last procedural gap (its Acceptance
Criteria and Decision sections had lagged behind its own
implementation, which raced ahead of the paperwork).

**Depends on:** Completed preview.11 to preview.12 qualification

**User outcome:** A supportable update mechanism with trustworthy release and
recovery operations.

Planned work:

- automate persistent-data restore verification — `sovereign-update restore`
  is implemented and hardware-qualified against real Pi-hole state on
  Raspberry Pi 5, including a forced-health-failure rollback path, twice
  now: once manually deployed, and again on a real `preview.13` base image
  that shipped it natively (see
  [BACKUP_AND_JOURNAL.md](update/BACKUP_AND_JOURNAL.md) and the
  [restore](docs/research/restore-hardware-qualification-report.md) and
  [preview.14](docs/research/preview-14-appliance-update-qualification-report.md)
  qualification reports); it still has not shipped through a release used
  by anyone beyond qualification. Wiring it into automatic update
  rollback is deliberately deferred, not open work: `activate_release`'s
  rollback path doesn't touch persistent data today because nothing in
  `prepare`/`stage`/`activate` does, so there is nothing yet for an
  automatic restore to undo. See the
  [restore-rollback wiring deferral](docs/research/restore-rollback-wiring-deferral.md)
  decision note — this becomes straightforward once an actual
  persistent-data migration step exists to protect against;
- define bounded retention and cleanup for old releases, backups, journals, and
  failed transactions — `sovereign-update prune [--dry-run]` is implemented
  and hardware-qualified on Raspberry Pi 5 against real backups, releases,
  and transaction journals, including confirming the live device stays
  healthy through an aggressive real deletion pass (see
  [BACKUP_AND_JOURNAL.md](update/BACKUP_AND_JOURNAL.md) and the
  [prune and trust rotation qualification report](docs/research/prune-and-rotate-trust-hardware-qualification-report.md)).
  Now wired into a daily `sovereign-update-prune.timer` (jittered, catches
  up on boot if a run was missed), hardware-verified running under its own
  hardened sandbox on Raspberry Pi 5; not yet shipped through a release
  beyond qualification. A genuine unattended timer-elapsed run — via the
  boot catch-up path, after the device missed its overnight window — was
  observed on 2026-08-09, closing the one remaining gap here: see the
  [prune timer unattended-fire qualification report](docs/research/prune-timer-unattended-fire-qualification-report.md);
- establish production signing-key custody, rotation, and revocation —
  decided in [ADR-0006](docs/adrs/0006-production-signing-key-custody.md)
  (password-manager-held key, hardware key as a future upgrade). Routine
  rotation/revocation is implemented as `sovereign-update rotate-trust`
  (signed, atomic, refuses any change that would leave a channel with no
  trusted key — see [update/README.md](update/README.md)'s "Trust Rotation
  v1" section) and hardware-qualified on Raspberry Pi 5, including the
  realistic single-key rotation handoff, immediate enforcement of
  revocation, and the lockout protection (see the
  [prune and trust rotation qualification report](docs/research/prune-and-rotate-trust-hardware-qualification-report.md)).
  The production key (`sovereign-production-1`, Ed25519, scoped to both
  `preview` and `stable`) has now been generated under that custody
  decision and its public half is baked into the image-builder overlay's
  trust store, so future base images trust it out of the box; the private
  half lives only as an encrypted secret in the maintainer's password
  manager. `v0.1.0-preview.17` is the first release signed with it,
  published, discovered, and — as of a full `prepare`/`backup`/`stage`/
  `activate` run on the same Raspberry Pi 5 — genuinely **installed**:
  the device now runs `0.1.0-preview.17`, `update_state: committed`,
  confirmed across a cold reboot. See the
  [discovery](docs/research/first-production-signed-release-qualification-report.md)
  and
  [install](docs/research/first-production-signed-release-install-qualification-report.md)
  qualification reports. That install campaign also found and fixed a
  real regression: `sovereign-proof.service` failing on any boot after
  `prune` removes the base image's own (now-inactive) release directory
  — `proof-init` now only performs that check during first-boot
  bootstrap. `restore` has since also been qualified against the real
  pre-activation backup that install created: correctly rejected a
  version-mismatched restore by default, then recovered an injected
  canary correctly under `--force` with no regression — see the
  [production-signed restore qualification report](docs/research/production-signed-restore-qualification-report.md).
  `prune` has now been exercised as part of a genuine signed-release
  install cycle: `v0.1.0-preview.23`, signed with the real production
  key by its custody holder (the assistant never handles that key,
  per ADR-0006), discovered, installed, and committed on the
  qualification device, followed by a real (non-dry-run) `prune` run.
  It correctly removed nothing — not a gap, but confirmation that
  `prune_releases`' protection logic works as designed: a release
  beyond the raw `keep_count` (here, `0.1.0-preview.21`, a third
  release against `keep_count: 2`) stays protected as long as any
  transaction still within retention (`committed` state, `keep_days:
  90`) records it as a rollback anchor — a genuinely useful, real-cycle
  confirmation that release and transaction retention interlock
  correctly rather than pruning something a still-live rollback path
  depends on. `rotate-trust` has now also been exercised with the real
  production key against the real device trust store, while the device
  ran a real signed, already-committed release (`0.1.0-proof.3`): a
  real, maintainer-signed add-only manifest brought the trust store to
  genuine dual trust, the newly added key proved itself functional by
  signing its own revocation, and a negative test confirmed revocation
  is enforced immediately against the real production key's rotation
  channel — see the
  [rotate-trust real signed-cycle qualification report](docs/research/rotate-trust-real-signed-cycle-qualification-report.md).
  This closes the last named gap in this milestone. Getting a rotation
  manifest onto already-flashed devices without an operator manually
  running the command still depends on the Update Discovery work in
  item 3 below (now complete, so this is unblocked whenever a rotation
  is actually needed);
- approve the update RFC and production manifest policy — the production
  manifest policy has been live and deployed since early qualification
  (`/etc/sovereign/update-policy.json`); [RFC-0014](docs/rfcs/0014-appliance-update-system.md)
  itself was formally Accepted on 2026-08-09, after its Acceptance
  Criteria and Decision sections were brought in line with the
  implementation and hardware qualification that had already shipped
  around it;
- publish release compatibility, rollback limitations, and recovery
  guidance — published as
  [docs/operations/update-recovery-and-compatibility.md](docs/operations/update-recovery-and-compatibility.md),
  written for the device operator rather than a contributor; and
- qualify every supported source-to-target update path on real hardware.
  A `0.1.0-preview.17` → `0.1.0-preview.18` attempt surfaced a real
  structural gap: the installed updater's appliance file allowlist was
  fixed at flash time and couldn't learn about a new file added by the
  release introducing it. Fixed and hardware-qualified the same day — the
  validator now rejects only missing required files, not unrecognized
  ones, and classifies appliance scripts by shebang instead of a
  hardcoded name set; the exact real stuck transaction was recovered
  through to `committed` on real hardware, confirmed persistent across a
  reboot — see
  [the finding](docs/research/appliance-file-set-update-ceiling-finding.md)
  and its
  [fix qualification report](docs/research/appliance-file-set-ceiling-fix-qualification-report.md).
  This does not touch the larger, still-unresolved question of delivering
  new systemd units/base-image content via update at all (see item 6
  below) — only the narrower file-allowlist symptom.

### 3. Update Discovery and Console Controls

**Status:** ✅ Complete

**Depends on:** Production Update Operations for the Console-facing and
installation-triggering bullets below; the device-side check-and-notify
bullet was deliberately scoped in RFC-0015 to not depend on it (no
Console change, no production key) and has already started.

**User outcome:** Learn about and install `x+1` from Sovereign Console without
using the command line or reflashing.

Planned work:

- publish signed update-channel metadata over HTTPS, and periodically check
  for compatible updates without sending household data — accepted in
  [RFC-0015](docs/rfcs/0015-update-discovery.md) and implemented as
  `sovereign-update check`, reusing the existing signed-manifest
  verification unchanged, with no new trust logic, no Console change, and
  no production key required. Runs daily via
  `sovereign-update-check.timer`, hardware-verified on Raspberry Pi 5
  against the real live GitHub API, including the positive "update found"
  path against a genuinely published (non-draft) release — see
  [update/README.md](update/README.md)'s "Update Discovery v1" section and
  the
  [positive-path qualification report](docs/research/update-discovery-positive-path-qualification-report.md).
  That campaign also surfaced a real gap, now fixed: `build-image.yml`'s
  release-publish step never uploaded the update-candidate manifest/bundle
  at all, and its filename collided with the image's own provenance file
  (now `image-manifest.json`). The workflow now conditionally uploads the
  unsigned update-candidate assets when `build_update_candidate` is
  selected; an operator still has to sign and upload the `.sig` offline
  before a release becomes discoverable;
- **Console authentication** — the prerequisite ADR-0005 itself named before
  any mutating Console action can exist. Decided and implemented in
  [ADR-0007](docs/adrs/0007-console-authentication.md): a separate
  Console-specific credential (`sovereign-console-password`), a
  loopback-only, systemd-hardened login backend (`sovereign-console-auth`,
  `/api/v1/auth/*`), session cookies with CSRF protection, and per-source
  rate limiting without lockout, with a sign-in UI wired into Console's
  topbar. Unit-tested (`tests/test_console_auth.py`) and
  hardware-qualified on Raspberry Pi 5 — see the
  [console authentication hardware qualification report](docs/research/console-authentication-hardware-qualification-report.md).
  A real signed-release install attempt (`v0.1.0-preview.18`) surfaced a
  structural finding bigger than Console auth itself — see
  [the finding](docs/research/appliance-file-set-update-ceiling-finding.md)
  — since fixed: `.18` is genuinely installed via a real update on real
  hardware, `console-auth`'s binary included. The base-image content it
  also needs (systemd unit, `sysusers.d` group, directory bootstrap) was
  then deployed manually and permanently to the qualification device —
  real, accepted drift against what any future image build produces
  until the next reflash, not something an update can deliver (tracked
  at item 6 below). Console authentication is now genuinely live and
  working on real hardware;
- **the first Console-triggered privileged action** — decided and
  implemented in
  [ADR-0008](docs/adrs/0008-console-privileged-action-invocation.md): a
  file-existence trigger picked up by a `systemd` path-activated,
  root-owned oneshot runner, scoped to exactly one action,
  `sovereign-update check`. Hardware-qualified on Raspberry Pi 5 — the
  full chain (auth/CSRF gating, the trigger actually firing, a real
  check running as root, the result surfacing back to Console, cooldown
  enforcement) verified correctly, after finding and fixing two real
  defects (a missing `ReadWritePaths=` grant, and a static-group name
  that collided with an unrelated service's own `DynamicUser` identity)
  — see the
  [qualification report](docs/research/console-check-trigger-hardware-qualification-report.md).
  `prepare`/`backup`/`stage`/`activate` (an actual install trigger) are
  explicitly out of scope for this pass — deliberately smaller blast
  radius first;
- **user-triggered download and installation, with full state reporting**
  — decided and implemented in
  [ADR-0009](docs/adrs/0009-console-triggered-install.md): reuses
  ADR-0008's file-trigger mechanism, resolved for a real action's
  parameter/blast-radius/status needs by having the privileged side
  independently re-decide the target through the same trust-anchored
  discovery `check` already uses (Console never supplies or influences
  which version installs), a required fresh password re-entry, and a
  single continuous prepare→backup→stage→activate sequence with no
  per-step Console confirmation. Hardware-qualified on Raspberry Pi 5 —
  the full sequence committed and survived a reboot via the real Console
  web API, after finding and fixing five real, previously-unexercised
  defects (a missing and then insufficient health-check retry budget, two
  missing systemd capabilities `nginx -t`'s real startup side effects
  need, an unretried local-access race against service restart, and a
  release directory silently losing world-traversability under the
  trigger unit's own umask hardening) — see the
  [qualification report](docs/research/console-triggered-install-qualification-report.md);
- show version, channel, release notes, download size, reboot requirements, and
  rollback limitations in Console — done: the update panel now shows a
  details row (channel, download size, reboot requirement, rollback
  support/limitations, release-notes link) whenever an update is
  available, sourced from fields `sovereign-update check` already
  verified from the signed manifest but hadn't previously surfaced past
  the CLI;
- retain a CLI recovery path independent of Console (already true: every
  step ADR-0009 orchestrates — `prepare`/`backup`/`stage`/`activate`/
  `recover`/`discard` — remains directly callable, unattended installs
  are simply the same primitives run in sequence).

The initial policy is **notify and require approval**. Automatic download and
maintenance-window installation follow only after repeated field qualification.
Every automatic policy retains signature verification, health-gated activation,
and automatic rollback.

### 4. Local Conversation and Capabilities

**Status:** 🟡 In progress — started 2026-08-09. The dependency below is
now satisfied (Milestone 2 is Complete).

**RFCs:** All four of the milestone's required RFCs are Accepted —
[RFC-0002](docs/rfcs/0002-local-conversation-and-inference-runtime.md)
(runtime and conversation architecture),
[RFC-0003](docs/rfcs/0003-capability-contract.md) (the typed registry
and six-stage deterministic executor),
[RFC-0004](docs/rfcs/0004-ai-capability-invocation.md) (AI capability
invocation, including the untrusted-forever boundary on capability
results), and
[RFC-0006](docs/rfcs/0006-pihole-capability-mapping.md) (Pi-hole
capability mapping, aggregate-only per Console health's own privacy
precedent).

**Capabilities:** `system.health`, `pihole.status`, and
`pihole.summary` are all implemented
(`sovereign_capabilities.py`, `sovereign_pihole.py`,
`sovereign_system.py`) and smoke-tested against the real device — see
the [pihole](docs/research/pihole-capabilities-smoke-test-report.md)
and [system.health](docs/research/system-health-capability-smoke-test-report.md)
reports. `web.search` and `web.fetch` are now implemented too
(`sovereign_websearch.py`), against
[RFC-0017](docs/rfcs/0017-web-search-and-fetch-capability-mapping.md)
(Draft, awaiting project-owner review — implemented ahead of formal
acceptance, matching this project's own precedent, e.g. the Conversation
Service itself shipped against RFC-0002/0003/0004 before those RFCs'
Decision sections were filled in). Both are backed by the now-embedded
SearXNG service: `image-builder/sovereign/searxng-image.env` (real
pinned ARM64 digest, `ghcr.io/searxng/searxng`) and `appliance/searxng/`
(compose template, `settings.yml`, `start-searxng`/`stop-searxng`, the
same artifact/import/server three-stage systemd shape Pi-hole and
llama.cpp use), unit-tested (`tests/test_searxng_deployment.py`) — see
[searxng-deployment-assessment.md](docs/research/searxng-deployment-assessment.md)'s
Addendum for the real-image verification (pinned digest, confirmed
`SEARXNG_SECRET` env-var mechanism, no built-in healthcheck, real JSON
response shape) this embedding was built from.

`sovereign_conversation.py` gained the real confirmation pause/resume
flow RFC-0004 specified but left unimplemented (`PendingTurnStore`,
`resume_turn()`, building on `sovereign_capabilities.ConfirmationStore`'s
already-implemented, already-tested `issue()`/`consume()`) — a
`required`-confirmation proposal now halts its round and returns a
`pending_confirmation` object with the literal disclosed arguments,
resumed via `POST /message`'s new `confirmation: {token, approve}`
field, single-use and audited either way. `web.fetch`'s SSRF policy
resolves the destination address immediately before connecting (not a
one-time hostname check a later DNS lookup could bypass) and pins the
TCP connection to that validated address while preserving the original
hostname for TLS SNI/certificate checks — verified live against real
public HTTPS sites and against every one of this device's own real
loopback ports during this session. `web.search` was verified live
against a real SearXNG container too (real query, real trimmed
results). `/data/sovereign/capabilities/policy.json`'s `external_enabled`
gate is read fresh per request and fails safe to disabled when the file
doesn't exist — reusing the same directory `sovereign-conversation.service`
was already granted write access to for its audit log, rather than a new
top-level file that would have needed its own systemd hardening grant
(and a root-run bootstrap step this project has no existing mechanism
for, having no `tmpfiles.d` usage anywhere — checked before implementing,
not after). 30 new tests
(`tests/test_websearch_capabilities.py`) plus extensions to
`tests/test_conversation.py`/`test_conversation_service.py` (full
HTTP-level pause/resume/policy round trips against the real registry).

Console's Chat page now renders the approve/deny confirmation prompt too:
a `.confirmation-card` discloses the literal capability name and
arguments from `pending_confirmation`, resumes the turn via the
`confirmation` request field on Approve/Deny, locks the composer while a
decision is pending, and clears itself on sign-out — unit-tested
(`tests/test_console.py`) and manually verified end-to-end against a
stub backend. Fixed a real pre-existing UI bug in the process: chat
receipts previously always said "stayed local" regardless of
classification, which would have been actively wrong for these two
capabilities.

The settings toggle is done too: authenticated `GET`/
`POST /api/v1/conversation/policy` (atomic `.tmp`-then-rename write,
same convention `sovereign-pihole-password` uses) and a labeled switch
on Chat (`#chat-policy-row`) that loads the real state on sign-in and
persists a change immediately, reverting the visible toggle if the write
fails. Manually verified end-to-end: toggling on and back off against a
stub backend correctly gated whether a search proposal reached a
confirmation prompt at all. `web_search_enabled` still defaults to
`false` on a device that has never touched the toggle.

**Real-hardware qualification is done** — see the
[web.search/confirmation flow hardware qualification report](docs/research/web-search-and-confirmation-flow-hardware-qualification-report.md):
real pinned digests pulled and run natively on the project's Raspberry
Pi 5 (`sovereign.local`, still `0.1.0-proof.3`, the same device the
llama-server deployment was qualified against), a real 2GB model
download with a matching checksum, real inference, real SearXNG search,
all five capabilities exercised through the real executor including a
real SSRF test against the device's own actual running services, a real
confirmation round trip, and a real browser-authenticated pass driven by
the project owner (their Console password never seen by the assistant,
matching this project's standing credential-handling convention). Found
and fixed one real bug live: the policy toggle's `GET` request was
missing its CSRF header and always failed against the real server (the
`POST` path was unaffected) — a regression test now covers it. This was
a manual smoke-test deployment, the same precedent the original
llama-server qualification established, not a real signed release —
the artifact/import systemd paths and `sovereign-conversation.service`'s
real `DynamicUser` sandbox remain unexercised (that directory-creation
question is still open, named in the report's own Limitations).

**Not yet done:** wiring SearXNG into the
release-bundle/update-release tooling
(`scripts/create-release-bundle.py`/`create-update-release.py`) the way
Pi-hole and llama.cpp already are; `sovereign-update`'s own
component-digest validation, which llama.cpp itself also doesn't have
yet (a disclosed, shared gap, not specific to SearXNG); and a real
`rpi-image-gen` build/flash/signed-update qualification of everything in
this milestone section, so the artifact/import systemd paths and the
real hardened sandbox get their first genuine exercise.

**Conversation Service:** implemented — `sovereign_conversation.py`
(RFC-0003/0004's bounded propose→execute→narrate loop: max 3 rounds per
turn, max 3 capability proposals per round, per-capability
invocation budgets enforced, capability results re-enter context as
plain untrusted `tool`-role messages) sits behind a thin loopback-only
HTTP wrapper, `bin/sovereign-conversation`
(`GET /api/v1/conversation/health`,
`POST /api/v1/conversation/message`), running as
`sovereign-conversation.service`
(`DynamicUser=yes`, hardened, not yet auto-enabled — see below).
Deliberately out of scope for this pass: streaming (the selected
llama.cpp adapter can't parse tool calls from a streamed response, so
every round is single-shot), a working confirmation pause/resume flow
(capabilities requiring confirmation are detected and refused with a
clear error — nothing registered needs one yet), and conversation
storage (stateless; the caller supplies full history per call). 26
unit/HTTP-layer tests cover the turn loop and the live service, and it
has been smoke-tested end to end on the real device — real inference
(llama.cpp + Qwen2.5-3B-Instruct), all three registered capabilities
proposed/executed/narrated correctly (including a model-chosen
structured argument for `pihole.summary`), a compliant audit trail, and
correct error handling. See the
[smoke test report](docs/research/conversation-service-smoke-test-report.md).

Wiring in the Pi-hole capabilities surfaced a real production gap:
`pihole-admin-password` was root-only (`0600`), which an unprivileged
`DynamicUser` service could never read. Fixed by mirroring
console-auth's own established pattern — a new
`sovereign-pihole-secrets` sysusers.d group,
`start-pihole`/`sovereign-pihole-password` now set the secrets
directory to `0710` and the password file to `0640` group-readable
(`chown root:sovereign-pihole-secrets`).

**Authentication:** wired, reusing console-auth's own session boundary
rather than a second one (RFC-0002/ADR-0007). console-auth gained
`GET /api/v1/auth/verify-mutating` — like the existing
`/api/v1/auth/verify` used to gate `/dns/` via Nginx `auth_request`, but
also checking the CSRF token, since a conversation turn does real work
directly (inference, capability execution) rather than navigating to a
panel with its own separate login. `bin/sovereign-conversation` delegates
to it on every `POST /message`, forwarding the caller's `Cookie` and
`X-CSRF-Token` headers and translating 401/403/unreachable into its own
JSON errors; `GET /health` stays open, matching `/api/v1/health`'s own
boundary (liveness only, nothing household-specific). Nginx now proxies
both routes onto the LAN-facing surface — `/message` with a 180s read
timeout, since a turn can run multiple real inference calls across
propose/execute/narrate rounds, well past the 5s every other API location
here uses. Smoke-tested against real hardware: all three auth outcomes
(no session, valid session with a missing/wrong CSRF token, valid
session with the correct one) verified over real HTTP, plus one full
authenticated turn reaching real inference and executing `system.health`
— see the
[report](docs/research/conversation-service-authentication-smoke-test-report.md).

**llama-server deployment and auto-enabling:** done, per
[ADR-0014](docs/adrs/0014-llama-server-deployment-and-model-provisioning.md).
The llama.cpp runner image is embedded in the base image and every
release exactly the way Pi-hole's is (`llama-image.env`, a real
`skopeo`-fetched digest, the same three-stage
artifact/import/server systemd shape). ADR-0013's selected model
(Qwen2.5-3B-Instruct-Q4_K_M) is deliberately **not** embedded — it does
not fit the real device's A/B system partition's size budget (confirmed
this session: ~2.0GB free, the model alone is ~2GB) — `start-llama-server`
downloads it into `/data/sovereign/models/` on first start instead, and
re-verifies its SHA-256 digest on every start after that, not just once.
`sovereign-conversation.service` gets a soft `After=` (not `Requires=`)
on the new `sovereign-llama-server.service`, so a still-downloading or
failed model load falls into the Conversation Service's existing,
already-tested `PROVIDER_UNAVAILABLE` degraded response. All four units
(`sovereign-llama-artifact`, `sovereign-llama-import`,
`sovereign-llama-server`, `sovereign-conversation`) are now in
`customize90-sovereign`'s enable-units list — the actual gap this
milestone was blocked on.

Known, disclosed tradeoff: a fresh install's first boot needs real
internet access and a multi-minute ~2GB download before conversation
works at all — a real regression from Pi-hole's fully-offline-after-imaging
posture, not hidden in the ADR.

**Deployment path qualified on real hardware.** `verify-llama-artifact`,
`import-llama-image`, and `start-llama-server` all ran for real against
a genuine `skopeo`-fetched artifact of the exact pinned digest (not a
full `rpi-image-gen` build, which stays out of scope for a smoke pass —
see the report's Limitations) — real checksum/tar-content verification,
real `docker load`+tag+platform check, real ~2GB model download, and a
real completion request whose `system_fingerprint` matched the exact
pinned upstream revision. Idempotency (a second run skips the download)
and the core trust-boundary claim — a corrupted model file is detected
and transparently re-downloaded, not silently trusted — were both
confirmed live, not just read from the script. Full writeup:
[llama-server-deployment-qualification-report.md](docs/research/llama-server-deployment-qualification-report.md).

**Runner and model benchmarking is concluded.**
`scripts/benchmark-inference-runner.py` (backed by
`sovereign_inference.py`, RFC-0002's Inference Provider Adapter
contract against both llama.cpp and Ollama) ran six real hardware
passes across two runners, two model sizes, and two corpora — including
finding and fixing a real bug (streaming silently dropped capability
proposals), confirming genuine thermal throttling via
`vcgencmd get_throttled` for the first time in this project's history,
and building a 28-item evaluation corpus after the initial 5-item one
hit a ceiling effect. Full narrative and data in the
[llama.cpp 3B](docs/research/llamacpp-qwen2.5-3b-benchmark-report.md),
[llama.cpp 7B](docs/research/llamacpp-qwen2.5-7b-benchmark-report.md),
[Ollama 3B](docs/research/ollama-qwen2.5-3b-benchmark-report.md),
[v1 corpus](docs/research/v1-corpus-benchmark-report.md), and
[DNS-latency-during-generation](docs/research/dns-latency-during-generation-qualification-report.md)
reports. That evidence became two accepted decisions:
[ADR-0012](docs/adrs/0012-local-inference-resource-and-dns-latency-budgets.md)
(80°C thermal budget, 40%-of-RAM memory ceiling, 50ms DNS-latency
budget) and
[ADR-0013](docs/adrs/0013-initial-inference-runner-and-model-selection.md)
(**llama.cpp + Qwen2.5-3B-Instruct** selected — better v1-corpus
accuracy than Ollama, no cold-start penalty, and Qwen2.5-7B excluded
outright on the memory budget). Two non-blocking validation gaps remain
open per ADR-0013's Required Follow-up (a realistic intermittent-use
thermal pass; broader DNS-latency-during-generation coverage) but do
not block moving on.

**Console Chat is now wired to the real Conversation Service.** The Chat
nav page (`console/index.html`, `console/assets/console.js`/`console.css`)
is no longer a static design preview: the composer posts to
`/api/v1/conversation/message` with the caller's session cookie and CSRF
token (reusing the same `csrfToken` console-auth's own sign-in flow
already maintains), renders the returned text and `capability_events` as
chat bubbles and receipts, and shows `/api/v1/conversation/health` in the
trust strip. Sending is gated on a signed-in Console session — the
composer stays disabled with a "Sign in to chat with Sovereign" prompt
until then, matching the same session boundary the update-install flow
uses. Client-side history sent back on each turn is capped at 20 messages
to stay under `/message`'s 64KiB request-body ceiling. Home Assistant and
Activity remain static design previews. Implemented and unit-tested
(`tests/test_console.py`); **not yet hardware-qualified** — this has only
been exercised against a local stub server, not the real device.

**Remaining:** hardware qualification of the Chat wiring above; a real
`rpi-image-gen` base-OS build exercising the llama-server deployment path
end to end (this session's qualification reproduced the embedding step by
hand with real tooling, not through the actual build pipeline);
`web.search`/`web.fetch` — deployment, capability implementation, the
confirmation/policy wiring, the Console approve/deny confirmation UI, and
the settings toggle to set `external_enabled` are all done now (see
above), still awaiting RFC-0017 project-owner review and hardware
qualification.

**Depends on:** Stable appliance update boundary

**User outcome:** Ask Sovereign local questions, inspect system and Pi-hole
status, and explicitly use privacy-transparent, self-hosted web-search tooling.

Milestone 01.2 will deliver:

- a Sovereign-owned conversation experience;
- provider-neutral local inference and model-management contracts;
- a Raspberry Pi 5 benchmark of llama.cpp and Ollama;
- a typed capability registry and deterministic executor;
- `system.health` and read-only Pi-hole capabilities;
- opt-in `web.search` through a locally operated SearXNG instance;
- restricted `web.fetch`, citations, privacy indicators, and audit events; and
- real-hardware qualification within DNS-latency, memory, power, and thermal
  budgets.

### 5. Home Automation Integration

**Status:** ⚪ Planned

**Depends on:** Qualified capability executor

**User outcome:** Ask about and safely control allowlisted home entities through
the same Sovereign conversation boundary.

The first slice is read-only Home Assistant entity discovery, state, and
history. Later slices may propose allowlisted actions, but deterministic policy
outside the model must authorize them and require confirmation according to
risk. The model never receives unrestricted Home Assistant, shell, Docker, or
network access.

### 6. Full Base-OS Updates

**Status:** ✅ Complete — every RFC-0016 Acceptance Criteria item is
now hardware-qualified, including the two hardest ones: a second
base-OS update with no reflash, and a genuine reflash-then-restore
recovery round trip. A few small implementation-detail questions
remain open in RFC-0016's own Unresolved Questions (CLI/API shape
polish, whether a base-OS and appliance update could ever share one
transaction), none of them blocking —
[RFC-0016](docs/rfcs/0016-full-base-os-updates.md) (accepted
2026-08-01): A/B root on Raspberry Pi's native `tryboot` mechanism,
reusing RFC-0014's signed/staged/health-gated/rollback machinery rather
than adopting a third-party OTA framework. Existing single-root devices
(including this project's own qualification hardware) migrate via a
one-time reflash, then receive base-OS updates like any new device from
that point forward. The `tryboot`/trial/commit/recovery cycle, release
tooling, `recover`/`prune` transaction integration, and CI release-candidate
wiring are all hardware- or live-verified.

The qualification device — already migrated to A/B on 2026-08-02 —
received a genuine **second** base-OS update on 2026-08-06 with no
further reflash: staged, trialed, health-gated, and committed, confirmed
persistent across an ordinary reboot. The Console base-OS panel — a
read-only `/api/v1/update/base-os-status` route and matching panel,
deployed the same day onto the device's separately-stale Console — was
then confirmed genuinely serving that real transaction data through the
real nginx proxy. See the
[second base-OS update qualification report](docs/research/second-base-os-update-hardware-qualification-report.md)
for both. That work found four real already-flashed-device
compatibility gaps — a pre-fix `sovereign-update` binary rejecting
modern manifests, a `"proof"`/`"preview"` semver-ordering collision
that permanently blocked such devices from real `preview.N` base-OS
releases, a stale-binary transaction missing a field the recovery
logic needs (causing a healthy trial to be falsely flagged as
interrupted), and `installed_base_os_version` being a hardcoded
build-time placeholder that never reflected the real installed
version. None of the four blocked a freshly-flashed device. As of
2026-08-07, all four are resolved: the ordering collision and the
placeholder both got real code fixes (`compare_versions`'s new
`PRERELEASE_CHANNEL_ORDER` table; `pre-image.sh` now templates from
`$SOVEREIGN_VERSION`), each with new test coverage; the other two
needed no separate fix, since `main` already contained their fixes —
the qualification device just hadn't received them yet.

The external recovery-image path — the last named-but-undesigned
requirement — is decided and hardware-qualified via
[ADR-0011](docs/adrs/0011-external-recovery-image-path.md): the
existing distributable image, reflashed via Raspberry Pi Imager, is
the recovery vehicle (no dedicated recovery-only OS), and the
previously-untested "reflash, then restore my data" gap is closed. The
qualification device was genuinely reflashed (wiping it entirely, via
a new CI artifact for the actual flashable A/B disk image, since none
existed before) and a pre-reflash backup restored onto it through the
existing, unmodified `backup`/`restore` commands — every persisted
file (Pi-hole state, admin-password secret) independently verified
byte-for-byte, the restored device's DNS service confirmed genuinely
working, and zero code changes needed. See the
[external recovery backup/restore qualification report](docs/research/external-recovery-backup-restore-qualification-report.md).

**Depends on:** Stable appliance updater and persistent partition contract

**User outcome:** Update Debian, kernel, firmware, Docker, and early system
services without reflashing.

The current updater covers versioned Sovereign appliance releases; it does not
make base-OS package transactions atomic. The long-term milestone must select
and qualify an A/B root-filesystem or equivalent immutable deployment design
with:

- persistent DATA independent of either system slot;
- atomic boot-slot selection;
- boot and health confirmation;
- automatic fallback to the previous system;
- signed system artifacts; and
- an external recovery-image path.

This milestone closes the remaining “flash once” gap.

## Progress Summary

- ✅ Concept paper and master plan
- ✅ Phase 01 appliance architecture decision
- ✅ `rpi-image-gen` assessment, proof build, and automated ARM64 image pipeline
- ✅ Flashable Raspberry Pi 5 image exercised on hardware
- ✅ Docker-based Pi-hole, `/dns/*` routing, and persistent DATA
- ✅ First-login credential-change and optional SSH-key flow
- ✅ Sovereign Console read-only health page qualified on Raspberry Pi 5
- ✅ Signed update transaction, interruption recovery, rollback, and persistence
  demonstrated on Raspberry Pi 5
- ✅ Fully versioned appliance-release qualification (preview.11 to
  preview.12), including readiness hardening
- ✅ Persistent restore automation, retention, and production signing operations
- ✅ Update discovery and Sovereign Console update controls
- ⏳ Local inference benchmark and conversation/capability RFCs
- 🟡 SearXNG-backed web-search capability — implemented, unit-tested,
  fully wired into Console's Chat UI including the settings toggle, and
  smoke-tested end-to-end on real Raspberry Pi 5 hardware (RFC-0017,
  Draft); a real signed-release qualification (artifact/import systemd
  paths, the real hardened sandbox) remains
- ⚪ Home Assistant capability integration
- ✅ A/B full base-OS updates (RFC-0016): every Acceptance Criteria item
  hardware-qualified, including a second base-OS update with no
  reflash, the Console panel against a live transaction, and a genuine
  reflash-then-restore recovery round trip (ADR-0011); four real
  already-flashed-device defects found and fixed

---

## Phases

- [00 Master Plan](docs/roadmap/00-master-plan.md)
- [01 Flashable Pi-hole Image POC](docs/roadmap/01-preview-poc.md)
- [Console Foundation](docs/roadmap/01-console-foundation.md)
- [01.1 Appliance Update Foundation](docs/roadmap/01-1-update-foundation.md)
- [01.2 Local Conversation and Capabilities](docs/roadmap/01-2-local-conversation-capabilities.md)

## Project Documentation

- [Documentation index](docs/README.md)
- [Initial target user](docs/product/target-user.md)
- [Core preview use cases](docs/product/core-use-cases.md)
- [Preview scope and non-goals](docs/product/preview-scope.md)
- [System overview](docs/architecture/system-overview.md)
- [Preview threat model](docs/security/threat-model.md)
- [ADR-0001: Phase 01 appliance architecture](docs/adrs/0001-phase-01-appliance-architecture.md)
- [RFC-0010: Raspberry Pi image deployment](docs/rfcs/0010-raspberry-pi-image-deployment.md)
- [Image release checklist](docs/operations/image-release-checklist.md)
- [ADR-0002: Installation images and update artifacts](docs/adrs/0002-install-images-and-update-artifacts.md)
- [ADR-0004: Provider-neutral assistant and web search](docs/adrs/0004-provider-neutral-assistant-and-web-search.md)
- [ADR-0005: Sovereign Console namespace and health boundary](docs/adrs/0005-sovereign-console-and-health-boundary.md)
- [RFC-0014: Appliance update system](docs/rfcs/0014-appliance-update-system.md)
- [RFC-0016: Full base-OS updates (A/B root filesystem)](docs/rfcs/0016-full-base-os-updates.md)
- [Preview.12 appliance update qualification report](docs/research/preview-12-appliance-update-qualification-report.md)
