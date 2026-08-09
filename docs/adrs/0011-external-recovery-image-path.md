# ADR-0011: External Recovery-Image Path for a Fully Unbootable Device

**Status:** Accepted
**Date:** 2026-08-07
**Decision owner:** Project creator
**Related RFCs:** [RFC-0016](../rfcs/0016-full-base-os-updates.md)
**Related ADRs:** None
**Related milestone:** ROADMAP item 6, "Full Base-OS Updates"
**Supersedes:** None

## Context

RFC-0016 names "an external recovery-image path" as one of the design
requirements for full base-OS updates, but explicitly left it undesigned:
its own Failure and Recovery section flags the both-slots-unbootable case
as needing "real physical-recovery implications... is the backstop here
and needs its own design pass," and its Unresolved Questions section asks
outright what that path "actually looks like — this RFC's `tryboot`
fallback covers boot failure, not both-slots-corrupted or physical-media
failure."

Today's actual baseline, already shipped and documented in
[update-recovery-and-compatibility.md](../operations/update-recovery-and-compatibility.md):
if the device won't boot to a usable state at all, the only recovery path
is reflashing the SD card with a known-good image — which wipes the
persistent DATA partition entirely (Pi-hole configuration, gravity
database, admin credentials, everything). That page says plainly:
*"There is currently no tested 'reflash, then restore my data' path; only
in-place restore during a live device has been qualified."*

### Why this can't be a partition on the disk itself

RFC-0016's own Compatibility and Migration section already established
the constraint that rules out an on-device recovery partition: `data`
grows via `growpart` at first boot to consume every remaining byte of
physical media after boot and root, so there is no unclaimed space left
for a third thing once a device has completed first boot — on *any*
device flashed with *any* image shipped to date, not something specific
to this ADR. "External" in RFC-0016's own naming is therefore not
incidental phrasing: recovery has to live on genuinely separate media
(a different SD card or USB stick an operator brings to the device), not
anywhere on the device's own storage.

### What's actually missing, once that's accepted

Given recovery must be external, two separate questions remain:

1. What *is* the external recovery image? Does this project need to
   design, build, and maintain a dedicated minimal recovery OS distinct
   from its normal distributable image?
2. Once a device is reflashed, can an operator get their data back, or
   is a full recovery always also a full data loss?

On (2): `sovereign-update backup`/`restore` already exist (RFC-0014) and
were re-examined for this ADR. A backup directory
(`STATE_ROOT/backups/<backup_id>/`) is already fully self-contained —
a handful of `.tar.zst` archives (Pi-hole state, Sovereign configuration,
secrets, a release pointer) plus a `backup-manifest.json` — and
`restore_backup`'s validation (`validate_backup_manifest`,
`verify_artifact`) checks purely by schema version, declared appliance
version, Pi-hole digest, and per-artifact SHA-256, with **no binding to
device identity** (no machine-id, no hostname, nothing host-specific) in
either the archive contents or the validation logic. Nothing about
`restore` as it exists today assumes the backup was ever on *this*
device, or even that the device was never reflashed in between — it
only insists the *appliance version* the backup came from is compatible
with the currently-installed one (or `--force`, already qualified against
a genuine version mismatch — see the
[production-signed restore qualification report](../research/production-signed-restore-qualification-report.md)).

That means a backup taken before a failure, copied off-device (`scp` to
an operator's own machine — already-existing, ordinary file transfer,
nothing new to build), can in principle be copied back onto a
freshly-reflashed device's `/data/sovereign/backups/<backup_id>/` and fed
straight into the existing `sovereign-update restore <backup_id>` — no
new subcommand, no new validation logic, no new trust boundary. This has
never been exercised end-to-end, which is exactly the gap
update-recovery-and-compatibility.md already names honestly.

## Decision

**Two decisions, addressing the two questions above:**

1. **No dedicated recovery-only OS or image.** The existing distributable
   Sovereign OS image, flashed via Raspberry Pi Imager — the same
   mechanism [docs/operations/raspberry-pi-imager-provisioning.md](../operations/raspberry-pi-imager-provisioning.md)
   already documents for first-time setup — *is* the external recovery
   image. "External recovery-image path" is satisfied by the artifact
   this project already builds and ships on every release; it does not
   name a new thing to design or maintain.
2. **Close the untested reflash-then-restore gap** by formalizing and
   hardware-qualifying the off-device backup round trip described above:
   take a backup (`sovereign-update backup <transaction-id>`), copy the
   resulting `STATE_ROOT/backups/<backup_id>/` directory off the device
   to separate storage the operator controls, reflash, copy that
   directory back onto the fresh device at the same path, and run the
   existing `sovereign-update restore <backup_id>` unmodified. No code
   changes to `backup`/`restore` are anticipated; this decision is about
   proving and documenting a procedure that already-shipped machinery
   supports, not building new machinery.

Implementation and hardware qualification of (2) are **out of scope for
this ADR** — this document only resolves the design question RFC-0016
left open. A follow-up qualification pass (mirroring this project's
existing discipline: real device, real reflash, real restore, a written
report) is the next step once this decision is accepted.

## Alternatives Considered

### A dedicated, minimal recovery-only OS image

A stripped-down image built solely for recovery (no Pi-hole, no Console,
just enough to run recovery/restore tooling), separate from the normal
distributable image.

- **Rejected.** Doubles the image-build surface this single-maintainer,
  single-hardware-target project has to build, sign, and keep current
  forever, for no capability the existing distributable image doesn't
  already have — a fresh flash of the normal image already produces a
  fully working device, which is the actual recovery goal. This is the
  same disproportionate-maintenance-cost reasoning ADR-0006 applied to
  reject cloud KMS and ADR-0010 applied to reject a real SSO identity
  provider.

### Network (PXE) boot recovery

Recover a bricked device by netbooting a recovery environment over the
LAN instead of requiring physical media.

- **Rejected.** Raspberry Pi 5's PXE/network boot path is a real EEPROM
  capability, but stands up new infrastructure (a DHCP/TFTP or PXE
  server) this appliance's single-household deployment model has no
  other use for, and conflicts with this project's offline-first,
  self-hosted values in the same way ADR-0004 already reasoned about
  external dependencies for the assistant/search milestone. Reflashing
  from an operator's own machine, already documented and already the
  supported path, needs no new server infrastructure at all.

### An on-device recovery partition

Reserve space at build time for a small recovery partition alongside
`bootconfig`/`boot_a`/`boot_b`/`system_a`/`system_b`/`data`.

- **Rejected outright, not a judgment call.** RFC-0016's Compatibility
  and Migration section already establishes that `data` consumes every
  byte left after boot and root at first boot — there is no space left
  for a seventh partition once any device has completed first boot,
  independent of this ADR's own reasoning. Reserving space for it at
  build time would mean permanently shrinking every device's usable
  `data` capacity for a partition most devices will never need.

### Build a new `sovereign-update export-backup`/`import-backup` convenience wrapper now

Script the copy-off/copy-back steps instead of leaving them as plain
`scp`/`rsync` in an operator runbook.

- **Deferred, not rejected.** Worth doing once the manual procedure is
  actually qualified and its exact steps are known precisely — writing
  convenience tooling around an unproven procedure risks automating the
  wrong thing. Revisit after the qualification pass this ADR sets up.

## Consequences

### Positive

- Resolves RFC-0016's last named-but-undesigned requirement with no new
  artifact to build, sign, or maintain — the existing release pipeline
  already produces the "external recovery image."
- Turns "reflash always means total data loss" into "reflash means data
  loss only if you skipped taking an off-device backup first" — a real,
  meaningful improvement using machinery this project has already built
  and qualified for a different purpose (in-place restore).
- No new trust boundary, validation logic, or attack surface: `restore`'s
  existing content-only validation (no device-identity binding) already
  supports this use case without modification.

### Negative

- Still fundamentally destructive: a full reflash always wipes root and
  DATA immediately; recovery only works if the operator took a backup
  *before* the failure and stored it somewhere the failed device's own
  wipe can't reach. A device that fails without ever having had an
  off-device backup taken is no better off than today.
- The copy-off/copy-back steps are manual (`scp`/`rsync` by hand) until
  the deferred convenience-wrapper alternative above is revisited —
  real friction for an operator recovering from an actual failure, not
  just a qualification nicety.

### Risks

- **Resolved:** this ADR's claim about `restore`'s validation being
  device-identity-agnostic was based on reading source at the time of
  writing; the 2026-08-08/09 qualification pass (see Validation and
  Revisit Conditions) confirmed it directly against a real reflash and
  a real restored device, not just analysis.
- If a future change to `backup`/`restore` ever *does* introduce
  device-identity binding (for a reason unrelated to this ADR), it would
  silently break this recovery path without necessarily being flagged as
  a regression against a "supported" feature, since none of today's
  tests exercise the cross-device case this ADR relies on.

## Validation and Revisit Conditions

**Accepted (2026-08-07, project creator).** Direction approved as
written. **Hardware-qualified (2026-08-08/09).** The full
backup-off/reflash/backup-back/restore round trip was exercised for real
on the qualification device — a real backup, copied off-device, a real
destructive reflash (via a newly-added CI artifact for the actual
flashable A/B image, since none existed before), and a real `restore
--force` against the version mismatch a genuine reflash produces.
Every persisted file (Pi-hole state, secrets) was independently
verified byte-for-byte against the original backup, not just trusted
from the tool's own reported status, and the restored device's actual
DNS service was confirmed working. Zero code changes to
`backup`/`restore` were needed — this ADR's claim about their
device-identity-agnostic validation held up under real conditions. See
the
[external recovery backup/restore qualification report](../research/external-recovery-backup-restore-qualification-report.md)
for the full account.

Revisit this ADR if: the manual copy-off/copy-back friction proves
unacceptable in practice (promote the deferred convenience-wrapper
alternative), or if `restore`'s validation logic ever needs to change in
a way that would reintroduce device-identity binding this ADR currently
relies on it not having.
