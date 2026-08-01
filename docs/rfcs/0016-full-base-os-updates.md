# RFC-0016: Full Base-OS Updates (A/B Root Filesystem)

**Status:** Draft
**Author:** Project creator and Claude
**Created:** 2026-08-01
**Reviewers:**
**Target phase:** ROADMAP item 6, "Full Base-OS Updates"
**Supersedes:** None

## Summary

Extend Sovereign's update system below the "appliance" layer it already
covers to the base OS itself — kernel, firmware, Docker, systemd units,
and any other content baked into the image at build time — using a
redundant (A/B) root-filesystem layout on the Raspberry Pi 5's own
`tryboot` firmware mechanism, verified and committed by reusing the
signed/staged/health-gated/rollback machinery `sovereign-update` already
has, rather than adopting a third-party OTA framework.

## Problem

`sovereign-update`'s existing `prepare`/`backup`/`stage`/`activate`
sequence (RFC-0014, hardware-qualified across many releases this project
has shipped) updates exactly one thing: the versioned "appliance" content
under `/opt/sovereign/releases/<version>/appliance/` — Pi-hole's pinned
container, nginx config, Console binaries, and `sovereign-update` itself.
Everything else on the device — the Debian base, kernel, firmware,
Docker Engine, and every systemd unit file under `/etc/systemd/system/`
that ships in the rootfs overlay — is fixed at whatever the device was
originally flashed with. There is no path to change any of it short of a
full reflash.

This was a deliberate, explicit deferral (ADR-0002: "Implement A/B root
filesystems immediately — Deferred because it adds bootloader, partition,
storage, health-commit, and recovery complexity before the POC image is
proven"; RFC-0014 lists "A/B root filesystem implementation" as a
non-goal), not an oversight. The persistent `/data` partition was
deliberately separated from the start specifically to keep this door
open (ADR-0002: "A dedicated data partition prepares the product for A/B
OS updates").

That deferral has now produced a concrete, repeatedly-felt operational
cost, not just a theoretical gap. During ADR-0009's hardware
qualification (Console-triggered install), a device flashed with
`v0.1.0-preview.18` could never exercise the feature under test at all —
`.18`'s rootfs predated ADR-0008/0009's systemd units entirely, and no
amount of appliance-layer updating could install them. The device had to
be reflashed with a newer full image before qualification could even
start. Every new systemd unit, base-package security fix, or Docker
Engine upgrade this project ships from here forward will hit the same
wall on every already-deployed device, growing more disruptive the
longer it goes unaddressed.

## Goals

- Update the base OS (kernel, firmware, Docker Engine, systemd units,
  and other rootfs content) on an installed device without reflashing
  and without losing `/data`.
- Reuse the existing signed-manifest, staged, health-gated,
  automatic-rollback model (RFC-0014) rather than building a second,
  parallel trust/state-machine system for this layer.
- Atomic slot selection with automatic fallback: a base-OS update that
  fails to boot or fails health checks must return the device to the
  previously-working slot without operator intervention.
- Keep `/data` fully independent of either root slot, as already
  established.
- Preserve the existing appliance-layer updater's role: base-OS updates
  and appliance updates remain distinct, independently versioned
  concerns (`components.image_base.version` vs.
  `components.appliance.version`, already present in every release
  manifest — see RFC-0014's release model).

## Non-Goals

- Changing anything about how appliance-layer updates work today. This
  RFC adds a layer beneath RFC-0014's mechanism; it does not replace it.
- Fleet orchestration, staged rollout percentages, or any hosted
  management service. Sovereign does not depend on a vendor's cloud
  console for updates (see the image-build assessment's explicit
  rejection of Raspberry Pi Connect as a dependency).
- Solving migration for devices that cannot be repartitioned in place
  (see Compatibility and Migration) beyond documenting the limitation
  honestly.
- Multi-platform support. This targets Raspberry Pi 5 specifically, the
  project's only supported hardware target.

## Context and Evidence

- ADR-0002 named the data partition's separation from root as
  deliberate groundwork for this exact milestone, and named "base-OS
  security maintenance requires A/B implementation sooner" as an
  explicit revisit condition. That condition has now been met.
- `docs/roadmap/01-1-update-foundation.md` §13 already sketches the
  target partition layout (`boot / root A / root B / data`) and names
  the three candidate mechanisms to research: RAUC, Mender, and
  Raspberry Pi's native `tryboot`.
- `docs/research/image-build-system-assessment.md` documents that
  `rpi-image-gen` — the builder this project already uses — ships an
  `ab_userdata` GPT layout example and an official OTA example built on
  `tryboot`, explicitly citing them as evidence the builder was chosen
  partly *because* it supports this direction. It also explicitly warns
  that builder's own OTA example is tied to Raspberry Pi Connect and
  "does not replace Sovereign's independent update-system design."
- The current image layout (`image-builder/sovereign/image/sovereign-data/image.yaml`)
  sizes the root partition at `root_part_size: 100%` of whatever remains
  after boot — i.e. today's images reserve **no** space for a second
  root slot at all. This is the central migration constraint below.
- `docs/research/console-triggered-install-qualification-report.md`
  documents the concrete incident that motivates prioritizing this now:
  a `.18`-flashed device structurally could not test a feature whose
  code had shipped weeks earlier, because that feature's systemd units
  live in the rootfs, not the appliance layer.

## Proposal

### Target partition layout

```text
boot        (unchanged: firmware, kernel, tryboot config)
root A      (fixed size, ext4, read during normal operation)
root B      (same fixed size, ext4, inactive except during/after an update)
data        (unchanged: /data, independent of either root slot, existing
             growpart-on-first-boot behavior unaffected)
```

Root A and root B are each sized to comfortably hold the base OS with
headroom for the packages this project actually installs (see
`image-builder/sovereign/layer/sovereign-proof.yaml`'s package list) —
not sized to 100% of the disk. `data` continues to expand to fill
whatever remains, as it does today.

### Slot selection and health confirmation: Raspberry Pi `tryboot`

Recommendation: build directly on the Raspberry Pi 5's own firmware
`tryboot` mechanism (supported since the 2023 EEPROM bootloader; already
demonstrated for A/B use by `rpi-image-gen`'s own official OTA example),
rather than adopting RAUC or Mender. See Alternatives Considered for why.

At a high level:

1. A base-OS update artifact (a new full root-filesystem image, signed
   the same way appliance releases are today) is written to the
   currently-inactive root slot.
2. The `boot` partition's `autoboot.txt` / `tryboot.txt` (or equivalent,
   pending firmware-version confirmation during implementation) is set
   to boot the new slot for exactly one trial boot.
3. On that trial boot, a systemd unit gated the same way
   `verify-update-health` gates appliance activation today — reusing
   that pattern, not just its name — confirms DNS, HTTP, Console, and
   Docker health.
4. On success, the device commits: the new slot becomes the persistent
   default (`autoboot.txt` updated to boot it normally, not just as a
   trial), and the transaction reaches `committed` in the same
   `sovereign-update status` surface appliance updates already report
   through.
5. On failure — health checks fail, or the trial boot never completes at
   all (crash, hang, power loss) — the firmware's own `tryboot` fallback
   behavior returns the next boot to the previously-active slot with no
   software involvement required. This satisfies "automatic fallback to
   the previous system" even in the worst case (the new slot's own OS
   never came up enough to run any of Sovereign's own code).

### Reusing RFC-0014's machinery

The signed-manifest verification, transaction journal, and
staged/backing-up/staged/activating/validating/committed state machine
`sovereign-update` already implements should be extended to a new
transaction kind (base-OS) rather than duplicated. Concretely:

- `release-manifest.json` already carries `components.image_base.version`
  separately from `components.appliance.version` — this RFC's artifacts
  populate that field for real, rather than leaving it static.
- A new artifact role (alongside today's `update_bundle`) carries the
  full root-filesystem image for the inactive slot.
- The existing trust store, key custody (ADR-0006), and rotation
  (`sovereign-update rotate-trust`) apply unchanged — this is a new
  artifact type under the same signing scheme, not a new trust root.

### Interaction with the appliance layer

Base-OS updates and appliance updates remain independently versioned and
independently triggered, matching today's manifest structure. An open
question (see below) is whether a base-OS update should ever bundle a
simultaneous appliance update in the same transaction, or whether they
must always be sequential (base-OS commits and reboots cleanly first,
*then* a normal appliance update proceeds against the new slot). The
latter is simpler to reason about and is the working assumption for this
draft.

## Interfaces and Data Flow

Pending implementation detail; sketched here for review:

- `sovereign-update` gains new subcommands or extends existing ones —
  exact CLI shape (`sovereign-update stage-base-os`, or a `--layer`
  flag on existing verbs, or something else) is an open question, not
  decided in this draft.
- `sovereign-update status` gains fields distinguishing an in-flight
  base-OS transaction from an appliance one, and reports which root
  slot is currently active/trial/committed.
- Console's update panel (just extended in this milestone to show
  channel/size/reboot/rollback for appliance updates) needs the same
  treatment for base-OS updates, including communicating that a
  base-OS update *always* requires a reboot, unlike most appliance
  updates today.

## Security and Privacy

- No new trust root: base-OS artifacts are signed and verified through
  the existing `sovereign-production-*` key custody and channel-scoping
  already in place (ADR-0006).
- The inactive slot, while being written, is not yet trusted or bootable
  as a fallback target — `tryboot`'s one-shot trial-boot semantics mean
  a partially-written or corrupted slot is never selected for normal
  boot, only for a single trial that a failed health check (or failure
  to boot at all) reverts from automatically.
- `/data` remains outside both root slots, so a compromised or corrupted
  root slot cannot be used to exfiltrate or tamper with persistent
  secrets by virtue of sharing a filesystem with them — this is already
  true today and is preserved, not newly introduced, by this design.

## Failure and Recovery

- Trial boot never completes (power loss, kernel panic, hang before
  Sovereign's own health-check unit runs): firmware-level `tryboot`
  fallback returns to the previous slot with no software dependency at
  all — the strongest failure mode this design can offer, since it does
  not depend on anything in the new slot working.
- Trial boot completes but health checks fail: the same
  `verify-update-health`-style gate used today reports failure, and the
  device falls back the same way a failed appliance activation does —
  needs a concrete decision on whether this triggers an immediate
  reboot back to the confirmed-good slot or waits for an operator,
  mirroring the existing appliance rollback design.
- Both slots become unbootable (e.g., a prior failed transaction was
  never cleaned up before a second one started): needs a documented,
  qualified worst case, analogous to today's `recovery_required` state
  for appliance transactions, but with real physical-recovery
  implications (external recovery-image path, named as a goal in
  ROADMAP item 6, is the backstop here and needs its own design pass).

## Compatibility and Migration

This is the hardest open problem in this proposal and should not be
understated: **today's images allocate the entire disk (minus boot and
an initial small data partition) to a single root partition
(`root_part_size: 100%`).** There is no reserved space for a second
root slot on any device flashed with any image shipped to date,
including the device this project's own hardware qualification runs on.

Two consequences follow:

- **New images** can adopt the A/B layout directly — this is a
  build-time layout change with no migration problem.
- **Already-flashed devices** cannot gain a second root slot without
  either (a) an in-place, live repartition-and-shrink of an in-use root
  filesystem (invasive, high-risk, and likely infeasible to do safely
  while the filesystem is mounted and serving DNS), or (b) a reflash,
  which is exactly the operation this whole milestone exists to avoid.

The honest options are: accept that existing single-root devices remain
on today's appliance-only updater indefinitely (with the base-OS gap
documented as a known, permanent limitation for that generation of
device, not silently glossed over), or accept that the transition to
A/B is itself a one-time reflash for currently-deployed devices — the
one case where reflashing is the correct, not-avoidable answer. This
draft does not resolve which; it should be an explicit decision recorded
before implementation begins, not discovered during it.

## Operations and Observability

- `sovereign-update status` must make the active/inactive slot and any
  in-flight base-OS transaction visible, the same way it already does
  for appliance transactions.
- Release/build tooling (`build-image.yml`) needs to produce a
  base-OS artifact alongside today's image and appliance-update
  artifacts, from the same pinned component-version manifest RFC-0014
  already requires image and update artifacts to share.
- Storage headroom checks (today's `free_bytes` requirement gate) need
  to account for writing a full second root image, not just an
  appliance-layer bundle — likely a meaningfully larger number.

## Testing Strategy

- Unit tests for manifest/artifact handling follow the same pattern as
  today's `tests/test_update_*.py` — signature verification, size
  limits, compatibility checks — extended for the new artifact role.
- `tryboot` behavior itself cannot be meaningfully unit-tested; it
  requires the same real-hardware qualification discipline this
  project has applied to every other update-system milestone
  (see the qualification reports linked from RFC-0014 and this
  milestone's own history). Expect a real, possibly multi-attempt
  hardware qualification campaign before this ships, consistent with
  every prior update-system milestone in this project.
- Forced-failure qualification (interrupted trial boot via a hard power
  cut, forced health-check failure) is not optional given how central
  automatic fallback is to this design's safety case.

## Alternatives Considered

### RAUC or Mender (adopt a third-party A/B OTA framework)

Both are established, and both support Raspberry Pi via `tryboot`
integration under the hood — meaning even adopting one of them still
ultimately delegates to the same firmware mechanism this RFC proposes
using directly. What they add on top is primarily: multi-hardware-target
abstraction (irrelevant — this project targets exactly one board),
bundle/manifest formats and signing of their own (redundant with the
signed-manifest, trust-rotation, and staged/health-gated/rollback system
this project already built and hardware-qualified for the appliance
layer), and in Mender's case, an optional hosted management service
(explicitly the kind of dependency this project's governance rejects —
see the image-build assessment's rejection of Raspberry Pi Connect on
the same grounds). Adopting either would mean running two parallel
signing/trust/state-machine systems — one already built and proven
(RFC-0014), one imported — for conceptually the same problem at two
layers of the same device. Rejected as unnecessary complexity and a real
governance mismatch, not because either is technically unsound.

### OSTree-style atomic filesystem trees

A single filesystem with atomically-swapped checkouts (as used by
Fedora Silverblue and similar) instead of two full physical partitions.
More storage-efficient (shared, deduplicated content between "slots"),
but it is a much larger integration effort — it changes the whole
filesystem management model, is not natively supported by
`rpi-image-gen`, and has no precedent anywhere else in this project's
tooling. Rejected for this milestone as disproportionate engineering
cost relative to a project with a single maintainer and a single
hardware target; worth reconsidering only if physical A/B's storage
cost (a full second root partition) proves genuinely prohibitive on
real hardware.

### Defer indefinitely, keep documenting the gap

Rejected: the ADR-0009 qualification incident this session already
demonstrated the cost is not hypothetical, and the cost compounds with
every future rootfs-level change this project ships.

## Drawbacks and Maintenance Cost

- A second root partition roughly doubles the storage this project's
  base OS occupies on every device, on top of whatever the base-OS
  artifact itself costs in transfer/build time.
- `tryboot`'s exact configuration surface (which firmware versions
  support which `autoboot.txt` syntax) needs to be confirmed against
  the actual EEPROM version this project's images ship, not assumed
  from general Raspberry Pi documentation.
- This is a genuinely bigger, riskier surface than any prior update-
  system milestone: a failure mode here can leave a device unable to
  boot at all, not just unable to reach `committed` state. The
  qualification bar (see Testing Strategy) needs to reflect that.

## Unresolved Questions

- Existing single-root device migration: reflash-once-then-A/B-forever,
  or permanently excluded from base-OS updates? (See Compatibility and
  Migration.)
- Exact `tryboot` configuration mechanism and the minimum EEPROM/firmware
  version this project can require.
- CLI/API shape for triggering and observing a base-OS transaction —
  new subcommands vs. extending existing ones.
- Whether a base-OS update and an appliance update can ever be part of
  the same transaction, or must always be sequential.
- Sizing for root A/root B: fixed at build time from today's package
  list, or does the image-build layout need a configurable margin for
  future growth?
- What "external recovery-image path" (named as a goal in ROADMAP item
  6) actually looks like — this RFC's `tryboot` fallback covers boot
  failure, not both-slots-corrupted or physical-media failure.

## Acceptance Criteria

- A device on a new A/B-layout image can receive a signed base-OS
  update, boot the new slot on trial, pass health checks, and commit —
  hardware-qualified on Raspberry Pi 5, following this project's
  established qualification discipline.
- A forced trial-boot failure (health check failure, and separately, a
  hard power cut mid-trial-boot) is qualified to correctly fall back to
  the previous slot with no data loss and no manual recovery needed.
- `/data` survives a base-OS update, a rollback, and a repeated cycle
  of both, unaffected.
- `sovereign-update status` and Console correctly represent an in-flight
  and a committed base-OS transaction.
- The migration question (above) is explicitly decided and documented,
  not left implicit.

## Decision

Leave blank until review. Record approval, rejection, or requested
changes with date and owner.
