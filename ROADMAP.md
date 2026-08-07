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

🟡 Milestone 01.1 — Appliance Update Foundation

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
qualification reports. `prune` and `rotate-trust` have not yet been
exercised as part of a real signed-release install cycle.

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

**Status:** 🟡 In progress

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
  by anyone beyond qualification, and is not yet wired into automatic
  update rollback for future data migrations;
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
  beyond qualification, and an actual unattended timer-elapsed run has not
  been separately observed;
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
  depends on. `rotate-trust` still hasn't been exercised this way —
  deliberately deferred as its own separate, deliberate event rather
  than bundled into this cycle. Getting a rotation manifest onto
  already-flashed devices without an operator manually running the
  command still depends on the
  Update Discovery work in item 3 below (now complete, so this is
  unblocked whenever a rotation is actually needed);
- approve the update RFC and production manifest policy;
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

**Status:** ⚪ Planned; research and RFC work may proceed in parallel

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

**Status:** 🟡 Core mechanism hardware-verified end to end, including a
second base-OS update with no reflash; Console UI surfacing still needs
its own live-hardware pass —
[RFC-0016](docs/rfcs/0016-full-base-os-updates.md) (accepted
2026-08-01): A/B root on Raspberry Pi's native `tryboot` mechanism,
reusing RFC-0014's signed/staged/health-gated/rollback machinery rather
than adopting a third-party OTA framework. Existing single-root devices
(including this project's own qualification hardware) migrate via a
one-time reflash, then receive base-OS updates like any new device from
that point forward. The `tryboot`/trial/commit/recovery cycle, release
tooling, `recover`/`prune` transaction integration, and CI release-candidate
wiring are all hardware- or live-verified. Console UI surfacing for
base-OS update state — a read-only `/api/v1/update/base-os-status`
route and matching Console panel — is implemented and unit-tested but
still not exercised against a live base-OS transaction on hardware.

The qualification device — already migrated to A/B on 2026-08-02 —
received a genuine **second** base-OS update on 2026-08-06 with no
further reflash: staged, trialed, health-gated, and committed, confirmed
persistent across an ordinary reboot. See the
[second base-OS update qualification report](docs/research/second-base-os-update-hardware-qualification-report.md).
That pass found and worked around four real already-flashed-device
compatibility gaps — a pre-fix `sovereign-update` binary rejecting
modern manifests, a `"proof"`/`"preview"` semver-ordering collision that
permanently blocks such devices from real `preview.N` base-OS releases,
a stale-binary transaction missing a field the recovery logic needs
(causing a healthy trial to be falsely flagged as interrupted), and
`installed_base_os_version` being a hardcoded build-time placeholder
that never reflects the real installed version. None of the four block
a freshly-flashed device; all four still need real fixes before this
milestone is production-ready, alongside the Console panel's own
hardware pass.

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
- 🟡 Persistent restore automation, retention, and production signing operations
- 🟡 Update discovery and Sovereign Console update controls
- ⏳ Local inference benchmark and conversation/capability RFCs
- ⚪ SearXNG-backed web-search capability
- ⚪ Home Assistant capability integration
- 🟡 A/B full base-OS updates (RFC-0016): core `tryboot` cycle, release
  tooling, and CI wiring hardware/live-verified, including a second
  base-OS update with no reflash; Console UI surfacing implemented and
  unit-tested but not yet hardware-verified against a live transaction;
  four real already-flashed-device defects found and still need fixes

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
