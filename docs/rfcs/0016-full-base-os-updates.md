# RFC-0016: Full Base-OS Updates (A/B Root Filesystem)

**Status:** Accepted — direction and migration approach decided
(2026-08-01); implementation and hardware qualification not yet started.
See Decision.
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
- The current image layout gives root a fixed, modest footprint (2.5G on
  the qualification device, not "the whole disk" — see the corrected
  numbers below), but it is `data` — not root — that expands to consume
  every byte of physical media the build-time layout didn't already
  claim, via `expand-data-partition`'s `growpart` call at first boot
  (`image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/usr/lib/sovereign/expand-data-partition`).
  By the time any device has completed its first boot, `data` occupies
  everything after `root` with no gap remaining. This is the central
  migration constraint below — not because root itself is oversized, but
  because nothing is reserved anywhere on the disk for a partition that
  doesn't exist yet in the build-time layout.
- `docs/research/console-triggered-install-qualification-report.md`
  documents the concrete incident that motivates prioritizing this now:
  a `.18`-flashed device structurally could not test a feature whose
  code had shipped weeks earlier, because that feature's systemd units
  live in the rootfs, not the appliance layer.
- The partition layout and `tryboot_a_b` mechanism described in
  Proposal are read directly from upstream `rpi-image-gen`'s official
  `image/gpt/ab_userdata` example (checked against a local copy of
  release `v2.7.0` during this RFC's research), not secondhand
  description — specifically its `genimage.cfg.in.ext4` (partition
  table), `pre-image.sh` (the `autoboot.txt` this project's design
  reuses verbatim), and `device/rootfs-overlay` (confirms no runtime
  script rewrites `autoboot.txt`; promotion is firmware-only). This
  example also includes cryptroot, eMMC write-protect, and erofs
  variants Sovereign does not need — implementation should extract the
  relevant ext4/plaintext subset, not adopt the example wholesale, and
  should vendor or pin the exact upstream commit actually used, per
  this project's existing pinning discipline (RFC-0010).

## Proposal

### Target partition layout

Corrected from the original draft after direct inspection of
`rpi-image-gen`'s own official `image/gpt/ab_userdata` reference example
(vendored locally during this project's earlier build-system research;
this is the same example the image-build assessment cited as evidence
for choosing this builder). The real reference layout has more parts
than this RFC first assumed, and the mechanism is simpler and more
precisely specified than the earlier "shared boot partition with an
`os_prefix` subdirectory" guess:

```text
bootconfig  (new, tiny — GPT partition holding only autoboot.txt, the
             tryboot control file the firmware reads before anything else)
boot A      (kernel, initramfs, dtbs, config.txt for slot A — whole,
             separate FAT partition, not a subdirectory of a shared boot)
boot B      (same, for slot B)
root A      (ext4, read-only at runtime — see "Root is read-only" below)
root B      (same, inactive except during/after an update)
data        (unchanged: /data, independent of every other partition,
             existing growpart-on-first-boot behavior unaffected —
             and now also where /opt/sovereign's appliance-release tree
             lives, moved out of root; see "Root is read-only" below)
```

Six partitions instead of today's three (`boot`/`root`/`data`) — moving
to **GPT**, not the MBR partition table this project's images use today
(see Unresolved Questions for why: six partitions don't fit MBR's
practical 4-primary-partition ceiling without nesting most of them
inside an extended partition).

Root A and root B are each sized to comfortably hold the base OS with
headroom for the packages this project actually installs (see
`image-builder/sovereign/layer/sovereign-proof.yaml`'s package list) —
not sized to 100% of the disk. `data` continues to expand to fill
whatever remains, as it does today.

Real numbers from this project's own qualification device, checked
directly (`df -h`, `lsblk -f`) rather than assumed:

- **root** is currently 2.5G total, 1022M used (44%). A root slot sized
  around 3G, comfortably covering today's usage with headroom for
  growth, is a reasonable starting point for both A and B — a modest
  ~6G total for both slots against devices this project targets (the
  qualification device alone has 113G of `/data`).
- **boot** is currently a single 98M partition with only **49M free**.
  Under the corrected layout above, boot content splits into two
  *separate* partitions (boot A, boot B), each holding only one slot's
  kernel/initramfs/dtbs at a time — this actually relaxes the original
  concern (a single ~98–120M partition per slot, not one shared
  partition needing to hold both simultaneously with near-zero margin).
  `kernel_2712.img` (10M) + `initramfs_2712` (14M) total ~24M today, so
  each of boot A/boot B needs to be sized comfortably above that, not
  the current 98M split two ways. Two smaller, real, independent
  findings either way: the current image ships device trees for boards
  this project doesn't support at all (`bcm2710-*`/`bcm2711-*`, Pi
  2/3/4/CM4 — ~500K combined, out of 20 `.dtb` files total for a
  Pi-5-only product) — cheap cleanup worth doing regardless of this
  RFC's outcome; and the new tiny `bootconfig` partition (32M in the
  reference example) holding only `autoboot.txt` is new overhead this
  layout didn't have before, though trivial in absolute size.
- No `autoboot.txt` exists on this device today (confirmed directly) —
  as expected, since nothing has configured `tryboot` yet. The
  bootloader itself is well past the version that added `tryboot`
  support (this device: EEPROM dated 2025-11-05; `tryboot` shipped in
  Raspberry Pi's 2023-05-11 firmware release), so the firmware
  prerequisite is already satisfied on hardware this project already
  qualifies against — the gap is purely in image layout and
  `sovereign-update` integration, not firmware readiness.

### Root is read-only

**Decided (2026-08-02, project creator): root A/root B are read-only at
runtime**, matching `rpi-image-gen`'s own reference design rather than
keeping root writable as this RFC originally sketched. Root as a
writable filesystem inside an A/B slot gets rollback but not integrity —
inconsistent with the atomic, never-mutated-in-place philosophy this
project already applies at the appliance layer (`current` is a symlink
swap between versioned, immutable release directories; nothing is ever
edited in place). A read-only root extends the same discipline down one
layer, and gives this DNS appliance a real, ongoing tamper-resistance
property beyond just enabling OTA updates.

This was weighed against the real complexity it adds — primarily that
Docker leans heavily on `/var/lib/docker`, which can't sensibly live on
a read-only filesystem — and concluded the cost is smaller for Sovereign
specifically than it would be for a general-purpose Docker host:
`activate_release` already re-imports the Pi-hole image by digest
(`docker load`) on every appliance activation, so Sovereign's Docker
usage is already tolerant of the image cache being ephemeral. A slot
switch resetting `/var/lib/docker` is not a new failure mode this design
introduces — it's a cost the appliance layer already absorbs today.

Following the reference architecture's pattern:

- `/var` and `/home` are reclaimed from each root slot at build time
  (emptied, replaced with a minimal writable skeleton for services that
  need `PrivateTmp`) and bind-mounted from persistent storage at boot,
  before `local-fs.target`.
- The systemd journal persists across slot switches (`Storage=persistent`
  under a dedicated, bounded-size location), rather than resetting with
  every base-OS update — losing log history on every update would be a
  real regression from today.
- `/etc/machine-id` is preserved and synced at boot rather than
  regenerated per slot, so device identity (and anything keyed off it)
  survives a base-OS update the same way it already survives an
  appliance update today.

**`/opt/sovereign` moves out of root entirely, onto `/data`.** This is
not optional once root is read-only — RFC-0014's appliance-release tree
(`RELEASES_ROOT`, today `/opt/sovereign`) is actively written to by
every appliance update, completely independent of base-OS updates
(ADR-0002: "application, appliance, and base-OS versions are tracked
independently"). If it stayed inside root, a base-OS update would
silently revert appliance content to whatever was baked into that base
image at build time, undoing independent appliance progress — a real
correctness bug, not just an immutability inconvenience. `/data` is
already this project's established boundary for "state that must survive
independently of the OS" (Pi-hole configuration, device secrets, backup
and transaction journals, update state all already live under
`/data/sovereign`); the appliance-release tree belongs there for exactly
the same reason, not in a second, newly-invented persistent-storage
mechanism.

Concretely, this is a **bind mount, not a path rename**: `/opt/sovereign`
stays the literal path every already-qualified piece of code, nginx
proxy config, and systemd `ExecStart=` line already hardcodes — none of
that gets touched. What changes is what backs it: at boot, before
anything needs it, `/opt/sovereign` gets bind-mounted from real storage
under `/data`, using the exact same "reclaim a path from the read-only
root, bind-mount it from persistent storage before `local-fs.target`"
mechanism already being adopted for `/var` and `/home` above — this
project's own instance of the reference architecture's `slot-shared`
pattern, not a separate mechanism invented for this one path.

What deliberately isn't adopted from the reference: `erofs` as the root
filesystem type (its own default) or dm-verity-backed integrity
verification. Both are real, further hardening steps in the same
direction as read-only root, but are separable, additive decisions this
RFC doesn't need to make now — plain read-only ext4 already delivers the
property that matters for this milestone (root cannot be mutated in
place; a corrupted or tampered root is still detectable by activation's
own signature/health gates, just not by filesystem-level verification on
every read). Revisit if a future security-focused RFC wants that
stronger guarantee.

### Slot selection and health confirmation: Raspberry Pi `tryboot`

Recommendation: build directly on the Raspberry Pi 5's own firmware
`tryboot_a_b` mechanism, following `rpi-image-gen`'s own official
`ab_userdata` reference example precisely rather than a bespoke
approximation, instead of adopting RAUC or Mender. See Alternatives
Considered for why.

The reference example's `autoboot.txt` (confirmed directly from its
`pre-image.sh`, which generates it at build time) is short and precise:

```ini
[all]
tryboot_a_b=1
boot_partition=2

[tryboot]
boot_partition=3
```

`tryboot_a_b=1` puts the firmware in a specific, documented A/B mode: a
**normal** boot always uses whatever `boot_partition` the `[all]`
section currently names (partition 2, i.e. boot A, initially). A
**trial** boot — triggered from Linux userspace via `reboot "0
tryboot"`, not by editing this file — uses the `[tryboot]` section's
`boot_partition` (3, i.e. boot B) for exactly that one boot.

**Corrected (2026-08-02, hardware-verified — supersedes this
paragraph's original text):** promotion is *not* automatic. An initial
draft of this RFC, written before any hardware testing, claimed the
firmware treats an ordinary reboot following a trial boot as implicit
confirmation and promotes the trial slot on its own. Direct hardware
testing disproves this: from an uncommitted trial boot, a plain `sudo
reboot` reverts to the *original* slot, not the trial slot. `[all]` in
`autoboot.txt` only ever changes when something explicitly writes it —
`rpi-slot-tryboot` (from `rpi-ab-slot-mapper`) prints the promoted
config fragment to stdout for exactly this purpose, but nothing invokes
it automatically; that is deliberately left to policy in a higher
layer, per that layer's own documentation ("it simply exposes stable
by-slot device links leaving policy to higher layers"). This is
actually a *safer* default than the originally-assumed behavior — it
means a trial that merely reboots itself, for any reason, reverts
automatically rather than committing — but it does mean
`sovereign-update` must perform an explicit commit step, not just an
ordinary reboot, to make a trial slot permanent.

At a high level, applied to Sovereign's existing transaction model:

1. A base-OS update artifact (a new full root-filesystem + boot-partition
   image pair, signed the same way appliance releases are today) is
   written to the currently-inactive slot (root B + boot B, in the
   partition numbers above).
2. `sovereign-update` triggers a trial boot: `reboot "0 tryboot"`. No
   `autoboot.txt` edit is needed for this step — the `[tryboot]` section
   is already static, always pointing at "the other" boot partition.
3. On that trial boot, a systemd unit gated the same way
   `verify-update-health` gates appliance activation today — reusing
   that pattern, not just its name — confirms DNS, HTTP, Console, and
   Docker health.
4. On success, `sovereign-update` explicitly commits: it runs
   `rpi-slot-tryboot` and writes its output over `autoboot.txt` on the
   (writable) `bootconfig` partition, making the trial slot the new
   `[all]` default, then performs an ordinary reboot (not another
   `tryboot`) into it. The transaction reaches `committed` in the same
   `sovereign-update status` surface appliance updates already report
   through.
5. On failure — health checks fail, or the trial boot never completes at
   all (crash, hang, power loss) — the device is still running the
   trial slot's kernel (if it's running at all) with `[all]` in
   `autoboot.txt` still pointing at the *original* slot, since nothing
   in step 4 ran. Any reboot or power cycle without that explicit commit
   returns to a normal boot using `[all]`'s unchanged value — the
   original slot — automatically. No software fallback logic is required
   for the crash/hang/power-loss case, and this now includes a hard
   power cut, hardware-verified directly (see Testing Strategy): a
   *detected* health failure (case 3 succeeding at running Sovereign's
   own code, but reporting bad health) simply means `sovereign-update`
   skips the step-4 commit and reboots or power-cycles back to the
   known-good slot — the same "do nothing, let it revert" path as any
   other failure, not a separate rollback mechanism.

### Build on `rpi-image-gen`'s own A/B layers, not a hand-rolled equivalent

Further research (into the `ab_userdata` example's own declared layer
dependencies) found that its slot-detection and `autoboot.txt`
generation logic isn't bespoke to that example — it comes from a
separate, versioned, documented upstream layer:
**`rpi-ab-slot-mapper`** (`layer/rpi/device/ab-slots.yaml` in
`rpi-image-gen`, currently v3.0.0), which itself depends on
`rpi-storage-binder` — a layer this project's images already require
today (`image-builder/sovereign/image/sovereign-data/image.yaml`'s
existing `X-Env-Layer-Requires`). This substantially changes the
implementation plan for the better: build on this layer directly rather
than reimplementing equivalent slot-detection logic.

Concretely, `rpi-ab-slot-mapper` installs:

- udev rules that create stable `/dev/disk/by-slot/active/*` and
  `/dev/disk/by-slot/other/*` symlinks from GPT partition labels;
- `rpi-slot-tryboot`, which reads those symlinks and prints exactly the
  `autoboot.txt` content this RFC's Proposal section already described
  (confirmed by reading the script directly — it generates precisely
  the `[all]`/`tryboot_a_b=1`/`[tryboot]` structure shown above, by
  resolving the current partition numbers dynamically rather than
  hardcoding them);
- `rpi-slot-label` / `rpi-slot-static` for labeling and static-fallback
  slot identification;
- initramfs-tools/dracut integration for early-boot root selection.

What it deliberately does **not** do: decide *when* to write a new
`autoboot.txt`, *when* to trigger `reboot "0 tryboot"`, or *when* to
treat a trial boot as confirmed versus roll back. That orchestration —
exactly the piece this RFC's "Reusing RFC-0014's machinery" section
below describes — is left to the consumer, which is precisely where
`sovereign-update`'s own transaction state machine should plug in.

The full reference layer this piece comes from,
`image-rota` (`image/gpt/ab_userdata/image.yaml`'s actual layer name),
also declares `rootfs_type: erofs` as its default (not `ext4`) and pulls
in `device-base`/`systemd-min` — implementation should confirm exactly
which of those are load-bearing for `rpi-ab-slot-mapper` to function
versus specific to that reference example's own choices (erofs,
encryption variants) before assuming the whole dependency chain is
required.

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
understated: **root itself is small and fixed (2.5G on the qualification
device), but `data` grows via `growpart` at first boot to consume every
byte of physical media left after boot and root — so by the time any
device has completed its first boot, there is no unclaimed space left on
the disk for a partition that wasn't already in the build-time layout.**
This is true on any device flashed with any image shipped to date,
including the device this project's own hardware qualification runs on
— not because root was sized greedily, but because nothing reserves
space in advance for a partition the layout didn't originally define.

Two consequences follow:

- **New images** can adopt the A/B layout directly — this is a
  build-time layout change with no migration problem.
- **Already-flashed devices** cannot gain a second root slot without
  either (a) an in-place, live repartition-and-shrink of an in-use root
  filesystem (invasive, high-risk, and likely infeasible to do safely
  while the filesystem is mounted and serving DNS), or (b) a reflash,
  which is exactly the operation this whole milestone exists to avoid.

**Decided (2026-08-01, project creator):** the transition to A/B is a
one-time reflash for currently-deployed devices, including this
project's own qualification hardware. Every device that goes through
that single reflash gains base-OS updates from that point forward with
no further reflashing required. Devices are not permanently excluded
from this capability based on when they were first flashed; the one-time
reflash is the deliberate exception to "no reflashing," made once, in
service of never needing it again for this class of update.

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

**Progress (2026-08-02):** the six-partition GPT layout builds
successfully end-to-end (`image-builder/sovereign/image/sovereign-ab-data`,
a new additive layer — the production `sovereign-proof.yaml` build path
is untouched). Verified locally, without a CI round-trip, using native
ARM64 Docker on Apple Silicon. Confirmed directly against the built
image: GPT partition table with exactly the designed six partitions
(`bootconfig`/`boot_a`/`boot_b`/`system_a`/`system_b`/`data`) at the
right sizes, `autoboot.txt` content matching the `tryboot_a_b` design
exactly, and `cmdline.txt`'s `root=` correctly using the
`rpi-ab-slot-mapper`-provided by-slot symlink rather than a hardcoded
UUID. Not yet done: booting this image at all (real or otherwise), let
alone a `tryboot` trial-boot cycle — that remains the real qualification
gate this section describes, unstarted.

**Progress (2026-08-02, continued):** first real boot on the
qualification Raspberry Pi 5. Found and fixed, in order: Raspberry Pi
Imager's first-boot account provisioning writing directly to
`/etc/passwd`/`/etc/shadow`/etc., impossible on read-only root; the new
image layer's bdebstrap hooks missing Docker installation, the
ADR-0003 bootstrap account, and almost all appliance service
enablement (authored from scratch rather than derived from
`sovereign-data`'s proven hooks); and, most substantively, that
individual-file bind mounts for the account database are insufficient
on read-only root — `passwd`/`usermod`/PAM write account files by
renaming a sibling temp file in the *same* directory, which needs the
whole `/etc` directory writable, not just the mounted file. Fixed by
overlaying `/etc` at boot (`sovereign-etc-overlay.service`): a writable
upper layer on `/data`, shared across slots (not per-slot) so account
state and imager-provisioned configuration survive a future slot
switch instead of reverting to build-time defaults, while untouched
files still track whatever the current slot's image ships. Confirmed
on hardware: SSH login with the ADR-0003 bootstrap credential, the
forced first-login password change, Docker, and the full appliance
service set (Pi-hole, Console, nginx) all now work end-to-end on the
GPT A/B image. A same-day detour attempted a native-systemd-`.mount`-unit
version of the `/etc` overlay after a hardware test appeared to hang;
the hang turned out to be an unrelated LAN/mDNS reachability issue on
the test machine, not a real boot problem, so that redesign was
reverted in favor of the already-hardware-proven version. Still not
done: an actual `tryboot` trial-boot cycle, which remains this
milestone's real qualification gate.

**Progress (2026-08-02, tryboot cycle):** the qualification gate itself,
qualified. `sudo reboot "0 tryboot"` correctly performs a one-time trial
boot of the inactive slot (verified via a marker file written to the
inactive slot's root beforehand, and via `sovereign-slot-var-generator`'s
own slot detection). Two safety-critical properties confirmed directly,
not assumed from documentation:

- An **uncommitted** trial reverts automatically on the very next
  ordinary (non-tryboot) reboot — no manual intervention, no hard power
  cycle needed. `autoboot.txt` is untouched by the trial boot itself
  (`rpi-slot-tryboot`, read from `rpi-ab-slot-mapper`'s own source, is
  a pure stdout-printing helper with no side effects — "it simply
  exposes stable by-slot device links leaving policy to higher layers,"
  per that layer's own documentation; promotion is not automatic and
  has no wiring anywhere in the upstream reference either, confirmed by
  grepping for callers). This is the most important property for the
  whole design's safety case, and it held without any Sovereign code
  written to enforce it — a firmware-level guarantee, not a userspace
  one.
- An **explicit commit** (`rpi-slot-tryboot > /bootfs/autoboot.txt`,
  run manually here since Sovereign hasn't built the automated
  health-gated commit step yet) correctly promotes the trial slot to
  the permanent default, verified to persist through a subsequent
  ordinary reboot.

Not yet done: a hard power cut *during* an active, uncommitted trial
(as opposed to a graceful uncommitted reboot, already verified above),
and the actual automated `sovereign-update`-side integration (health
gate + commit step) that item 6 on the roadmap still needs — today's
commit step was a manual qualification action, not product code.

**Progress (2026-08-02, forced-failure test):** the hard-power-cut case
above, now also qualified. Power was pulled within seconds of issuing
`sudo reboot "0 tryboot"` — before the trial slot could plausibly have
finished, likely even started, booting — then restored for a normal
cold boot. Result: the device came up cleanly on the committed default
(`system_b`), `uptime` confirming a genuine fresh boot; `autoboot.txt`
unchanged; no `systemd-fsck` errors logged. A dry-run `e2fsck -fn`
against the interrupted trial slot's own root filesystem afterward
found zero errors across all five passes — the interruption left no
corruption on either slot, not just on the one that ended up booting.
Both halves of RFC-0016's Testing Strategy forced-failure requirement
(interrupted trial boot, forced health-check failure) are covered for
the interrupted-boot half; forced health-check failure has no product
code to test yet (see below).

**Progress (2026-08-03/04, automated integration, full cycle on
hardware):** `sovereign-update` gained real product code for the base-OS
transaction flow described in the Proposal section above —
`stage-base-os`, `trial-base-os`, an automatic health-gate
(`verify-base-os-trial`, invoked by a new boot-time systemd unit,
`sovereign-verify-base-os-trial.service`, gated the same way appliance
activation's `verify-update-health` is gated) and `commit-base-os` — reusing
the existing Ed25519 signature/trust-store machinery for a new,
independently-versioned base-OS manifest (two artifacts: `system_boot`,
`system_root`). All four commands run against real, signed artifacts and
real block devices, with a hard safety check that refuses to ever write
to the currently-active slot's device, verified freshly at write time
against the by-slot symlinks rather than any cached/independently-computed
slot identity.

Two real bugs were found and fixed before this reached hardware cleanly:

- A state-machine bug where the generic `transition()` helper (written for
  appliance transactions) was reused for base-OS transitions without
  also overriding *where* it writes state — silently writing into the
  appliance's own `transactions/` directory and status file instead of
  `base-os-transactions/`. Caught by local unit tests before ever
  touching hardware.
- `/usr/sbin/reboot` on this image is a symlink to `systemctl`, not a
  standalone binary. A bare positional `"0 tryboot"` argument (mimicking
  traditional `reboot ARG` syntax) does **not** reliably reach the
  firmware through it — hardware-verified to silently fall back to an
  ordinary reboot instead, even though the exact same argument form had
  worked in earlier manual qualification testing via an interactive
  shell. `systemctl`'s own documented `--reboot-argument=ARG` option
  ("Specify argument string to pass to reboot()") is required instead,
  and was confirmed on hardware to trigger a real trial boot reliably.
  This was **only** caught by hardware testing — every local test stub
  is a fake `reboot`/`systemctl` script that simply logs its argv, which
  can't distinguish real firmware-reaching behavior from a plain reboot
  that happens to also succeed and return exit code 0.

With both fixed, a complete, unattended (aside from the manual CLI
invocations standing in for a future "install this update" trigger)
cycle succeeded on the qualification device: `stage-base-os` verified
and wrote a signed artifact pair to the inactive slot; `trial-base-os`
triggered a real trial boot; the boot-time health gate ran automatically
and reported `validated` against real Docker/DNS/Console health (not a
stub); `commit-base-os` wrote the promoted `autoboot.txt` and rebooted;
the device came up on the newly-committed slot as the permanent
default, confirmed via a genuine fresh `uptime` and `autoboot.txt`'s
`[all]` section now pointing at the promoted partition.

This required first resolving an unrelated, real finding: the
qualification device's `eth0` DHCP client had stopped acquiring an
IPv4 lease (a driver/systemd-networkd race, `ENOMEDIUM` despite a stable
carrier — see
[`docs/research/eth0-dhcp-carrier-race-finding.md`](../research/eth0-dhcp-carrier-race-finding.md)),
which was silently failing the appliance health check (no internet →
Pi-hole's `gravity.db` never builds) independent of anything in this
milestone's own code. Worked around with a persistent static IP on the
qualification device; the general DHCP-client bug remains open and
unrelated to RFC-0016.

RFC-0016's core acceptance criteria — a working `tryboot` A/B cycle with
signed artifacts, health-gating, and both graceful and forced-failure
recovery — are now met and hardware-verified. Remaining before this is
production-ready: Console UI surfacing for base-OS update state.

**Progress (2026-08-04, release tooling):** `scripts/create-base-os-release.py`
now exists, mirroring `create-update-release.py`'s own shape and
conventions (unsigned manifest + artifacts out; signing stays a
separate, explicit step via the existing `sign-update-manifest.py`, per
ADR-0006's key-custody boundary). It takes already-built raw
`boot.vfat`/`root.ext4` images as input rather than building them
itself — the same relationship `create-update-release.py` has to a
pre-built Pi-hole OCI archive — since genimage's own deploy step
produces android-sparse-format output, not the plain raw images
`stage-base-os` writes sequentially onto a block device.

This surfaced a real gap in the `stage-base-os` implementation itself,
fixed alongside the release tooling: it had only ever been exercised
against uncompressed qualification artifacts, but real release artifacts
need zstd compression to be practical (a 3G raw root image compresses
to a fraction of that) — `write_raw_artifact` now decompresses while
streaming directly onto the device rather than assuming the artifact is
already raw. `BASE_OS_BOOT_MEDIA_TYPE`/`BASE_OS_ROOT_MEDIA_TYPE` gained
an explicit `+zstd` suffix to say so, matching the existing
`update_bundle` artifact's own `+tar+zstd` convention. Not yet wired
into `.github/workflows/build-image.yml` at this point: doing so needs
the image-build pipeline itself to export the raw boot/root images
somewhere accessible before genimage's sparse conversion, which the
`deploy/` output alone doesn't do — see the next entry below.

**Progress (2026-08-05, recover/prune integration):** `recover`/`prune`
now cover base-OS transactions, closing the gap noted above. This
needed more care than the appliance-transaction case it mirrors,
because of a boot-ordering fact: `sovereign-update-recovery.service`
runs early (`Before=sovereign-pihole.service`), while the trial
health-gate (`sovereign-verify-base-os-trial.service`) runs later
(`After=...sovereign-console.service, nginx.service`). That means
recovery runs on *every* boot, including a genuinely in-progress
trial boot, before the health-gate has had a chance to run — a naive
sweep of `trial`-state transactions would misfire and recover a trial
that hasn't failed at all. Fixed by recording which slot a trial
transaction targets (`target_slot`, via a new `slot_label_for()`
helper) at stage time, and comparing it against the currently active
slot at recovery time: still on the target slot means the trial is
genuinely in progress (leave it alone), already reverted means the
transaction was abandoned (mark `recovery_required`). Added
`discard-base-os` to close out terminal-state transactions, and
extended `prune`'s sweep and post-prune `sync_directory` calls to
include the `base-os-transactions` directory alongside the existing
appliance one.

This also surfaced and fixed a real, pre-existing bug:
`current_slot_label()` parsed the by-slot symlink's `readlink` target
for a `system_a`/`system_b` suffix, but that target is just a raw
device node path (e.g. `../../mmcblk0p4`) and never contains the slot
label at all — `sovereign-update status` had been silently reporting
`"active_slot": "mmcblk0p4"` instead of a proper slot name since this
was first written. The new recovery logic was the first consumer that
actually needed a *correct* slot label to compare against, rather than
one that was purely informational. Fixed by shelling out to
`blkid -s PARTLABEL -o value`, matching the existing
`sovereign-slot-var-generator` script's own approach.

**Progress (2026-08-05, CI wiring):** `.github/workflows/build-image.yml`
can now produce an unsigned base-OS update candidate end to end, closing
the gap left by the release-tooling entry above. This turned out to need
more than a packaging step: CI's existing "Build image" run only ever
targets `sovereign-proof.yaml`, the plain non-A/B config, and that
image's `boot.vfat`/`root.ext4` are structurally the wrong shape for a
base-OS update (no tryboot partitions to stage onto). Producing a base-OS
candidate genuinely requires a second, separate image build against
`sovereign-ab-proof.yaml` — so it's gated behind a new opt-in
`build_base_os_candidate` dispatch input (default `false`, mirroring
`build_update_candidate`'s own shape) rather than doubling every build's
runtime unconditionally.

Getting at the raw `boot.vfat`/`root.ext4` at all needed a small
`scripts/build-sovereign-image.sh` change: `rpi-image-gen`'s own deploy
step (`layer/base/deploy.sh` in the vendored tool) only ever exports
`*.sparse` files out of its work directory, even though genimage builds
the plain raw images too, as an intermediate step, on the way to its
android-sparse conversion. `build-sovereign-image.sh` now `docker cp`s
those two raw files out of the container directly (into
`evidence/base-os/`, alongside the script's existing oci/bootstrap/
sovereign-release evidence exports) — a tolerated no-op for configs,
like the plain image, that were never meant to feed a base-OS release.
The workflow's new "Build base-OS image" / "Package unsigned base-OS
update candidate" / "Upload base-OS update artifact" steps mirror the
existing appliance-update-candidate ones exactly, including the same
ADR-0006 unsigned-manifest caveat in the draft-release step (CI never
holds the signing key; an operator still signs offline before
publishing).

**Progress (2026-08-05, CI wiring live-verified):** the CI wiring above
had only been proven against Docker-stubbed tests until now — actually
dispatching the workflow (`build_base_os_candidate: true`, no draft
release) against real Docker/`rpi-image-gen` was the natural next check,
and it passed cleanly: both the primary and second (A/B) image builds
succeeded, run
[31030670477](https://github.com/sovereignfs/sovereign-os/actions/runs/31030670477),
7m49s total. The uploaded `sovereign-base-os-0.1.0-preview.24-rpi5-arm64`
artifact was downloaded and checked directly rather than just trusting a
green run: both `boot.img.zst`/`root.img.zst` files' recomputed SHA-256
matched `base-os-manifest.json`'s declared digests exactly, and the
manifest validated cleanly against `sovereign-update`'s own
`validate_base_os_manifest()` — the same validator `stage-base-os` runs
on a device.

This confirms the CI pipeline itself is correct end to end. It does not
confirm the pipeline's *output* against real hardware — every hardware
tryboot/trial/commit/recovery cycle qualified so far in this RFC used
manually-built images, never an artifact that came out of this workflow.
That's the natural next verification once there's a reason to cut a real
base-OS release, not attempted here.

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
  from general Raspberry Pi documentation. The firmware version
  requirement itself is already satisfied on this project's
  qualification hardware (see Proposal); what remains unverified is the
  exact config syntax, not whether the feature exists.
- The **boot partition must grow** — confirmed directly on real
  hardware, not estimated: today's 98M boot partition has only 49M
  free, and a second slot's kernel + initramfs alone (~24M) would
  consume essentially all of that margin. This is a required image-layout
  change this RFC depends on, not an optional optimization.
- This is a genuinely bigger, riskier surface than any prior update-
  system milestone: a failure mode here can leave a device unable to
  boot at all, not just unable to reach `committed` state. The
  qualification bar (see Testing Strategy) needs to reflect that.
- Read-only root adds real new surface beyond the partition/tryboot
  mechanism itself: `/var`/`/home` reclaim-and-bind-mount at boot,
  journal persistence configuration, machine-id sync, and moving
  `/opt/sovereign` onto `/data` all need their own correctness
  verification, not just "the OS boots." A subtly wrong bind-mount
  ordering (before `local-fs.target`, before anything that writes to
  `/var` starts) is a real, easy-to-get-wrong failure mode this design
  introduces that a writable-root approach wouldn't have had.
- Docker's storage under `/var/lib/docker` is not preserved across a
  slot switch under this design (see "Root is read-only"). Acceptable
  because `activate_release` already re-imports the Pi-hole image by
  digest on every appliance activation, but this should be explicitly
  qualified, not just assumed — confirm Docker itself starts cleanly
  against an empty `/var/lib/docker` after a slot switch, not only that
  the subsequent `docker load` succeeds.

## Unresolved Questions

- **Resolved: move to GPT.** Not because `tryboot_a_b` is confirmed to
  require it at the firmware level (that remains unverified either way)
  — but because the six-partition layout itself doesn't fit MBR's
  practical ceiling of 4 primary partitions (or 3 primary + 1 extended
  containing logical partitions). `rpi-image-gen`'s reference example
  uses GPT's own partition-table format directly, cleanly addressing 6
  partitions with `in-partition-table = true` entries; reproducing the
  same layout under MBR would mean nesting most of the new partitions
  inside an extended partition, working against the tooling instead of
  with it, for a hardware target that has no need to preserve MBR
  specifically. Today's images move to GPT as part of this milestone.
- **Resolved: use the `/dev/disk/by-slot/active/*` symlink scheme
  verbatim** — it comes from `rpi-ab-slot-mapper`, a separate, versioned
  upstream layer (not something to reimplement), and Sovereign already
  depends on that layer's own prerequisite (`rpi-storage-binder`). Still
  open: whether the small `bootconfig` partition specifically is
  required by that layer or is incidental to the `ab_userdata` example,
  and which of `image-rota`'s other declared dependencies
  (`device-base`, `systemd-min`) are load-bearing versus specific to
  that example's own choices (erofs, encryption variants Sovereign
  doesn't need).
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
  of both, unaffected — including `/opt/sovereign`'s appliance-release
  tree, now living there: an appliance update installed *after* a
  base-OS update must still be present and correctly `current` after a
  *subsequent* base-OS update, proving the two layers are genuinely
  independent, not just independently versioned on paper.
- Root is confirmed read-only at runtime (a write attempt fails), with
  `/var` and `/home` correctly bind-mounted and writable, Docker starting
  cleanly against a slot-switch-reset `/var/lib/docker`, the journal and
  `/etc/machine-id` surviving a base-OS update unchanged.
- `sovereign-update status` and Console correctly represent an in-flight
  and a committed base-OS transaction.
- The qualification device (and any other currently-deployed device)
  is successfully migrated via the decided one-time reflash and
  receives at least one subsequent base-OS update without a second
  reflash.

## Decision

**Accepted (2026-08-01, project creator).** Direction approved as
written: A/B root on Raspberry Pi's native `tryboot`, reusing RFC-0014's
signed/staged/health-gated/rollback machinery rather than adopting a
third-party OTA framework. The migration question is resolved (see
Compatibility and Migration): a one-time reflash for currently-deployed
devices, A/B thereafter. Remaining items in Unresolved Questions are
implementation-detail decisions, not open direction questions, and may
be resolved during implementation and hardware qualification rather
than blocking the start of that work.
