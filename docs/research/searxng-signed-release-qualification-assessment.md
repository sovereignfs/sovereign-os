# Research: Real Signed-Release Qualification for SearXNG's Artifact/Import Path

**Status:** Concluded (desk research); code prep landed, hardware/CI execution still open
**Author:** Claude (assistant), reviewed by project owner
**Started:** 2026-08-21
**Concluded:** 2026-08-21
**Decision informed:** Scope and sequencing of the remaining "Real signed-release
qualification" item on [PR #17](https://github.com/sovereignfs/sovereign-os/pull/17)'s
test plan, and the two structural gaps this investigation found along the way.

## Question

The hardware qualification pass for `web.search`/`web.fetch`/SearXNG (see
[web-search-and-confirmation-flow-hardware-qualification-report.md](web-search-and-confirmation-flow-hardware-qualification-report.md))
explicitly left one item open: "Not a substitute for a real `rpi-image-gen`
build, flash, and signed update — every artifact/import systemd path...
remains unexercised." Can that gap be closed from this session, and if not,
what specifically blocks it and what can be done now to shorten the real
qualification pass when it eventually happens?

## Context

SearXNG's deployment (this branch) added three new systemd units
(`sovereign-searxng-artifact.service`, `sovereign-searxng-import.service`,
`sovereign-searxng.service`) that ship as base-image (rootfs-overlay)
content, plus a new pinned OCI image
(`image-builder/sovereign/searxng-image.env`). Neither of those has ever
been exercised through the project's real release/update machinery — only
through a manual smoke test with everything staged under a writable path
and run by hand (see the qualification report above). llama.cpp's own
equivalents were never exercised through the real release machinery either,
which turned out to be relevant (see Findings).

## Sources and Environment

Direct code inspection only (macOS, no privileged device access, no CI
trigger) of:
- `image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/usr/sbin/sovereign-update`
  (the installed, on-device updater)
- `scripts/create-release-bundle.py`, `scripts/create-update-release.py`
- `image-builder/README.md`, `.github/workflows/build-image.yml`
- `docs/rfcs/0016-full-base-os-updates.md`,
  `docs/adrs/0006-production-signing-key-custody.md`
- `docs/research/appliance-file-set-update-ceiling-finding.md`,
  `docs/research/appliance-file-set-ceiling-fix-qualification-report.md`,
  `docs/research/second-base-os-update-hardware-qualification-report.md`

## Findings

**Finding 1 — new systemd units cannot reach an already-flashed device
through any update mechanism at this project's current implementation
state, independent of SearXNG.** `sovereign-update`'s appliance-release
`prepare → backup → stage → activate` cycle never writes under
`/etc/systemd/system/` and never runs `systemctl daemon-reload` or
`systemctl enable` — confirmed by reading `activate_release` directly, and
by two prior real qualification reports hitting this exact wall for
`console-auth`'s own unit. The only mechanism that *can* deliver new
systemd units to an already-flashed device is
[RFC-0016](../rfcs/0016-full-base-os-updates.md)'s base-OS A/B `tryboot`
update, which ships a whole new root filesystem for the inactive slot
(confirmed hardware-qualified for its own purpose in
[second-base-os-update-hardware-qualification-report.md](second-base-os-update-hardware-qualification-report.md)),
not the appliance-release delta mechanism. This applies equally to
SearXNG's three units and to llama.cpp's own three-unit equivalents
(`sovereign-llama-artifact.service` etc.), which have the identical status.

**Finding 2 — a real base-OS image build is CI-only.** Per
`image-builder/README.md`, the macOS Docker adapter (`Dockerfile.proof`) is
explicitly "not a qualified release environment" — only an engineering
proof of ARM64 dependency resolution and image assembly. The real,
qualifiable build path is `.github/workflows/build-image.yml`, which runs
on a native `ubuntu-24.04-arm` GitHub Actions runner,
`workflow_dispatch`-triggered, budgeted up to 120 minutes. There is no
macOS-sandbox route to a real, ship-quality image.

**Finding 3 — signing is the maintainer's alone, by unbroken precedent.**
Per [ADR-0006](../adrs/0006-production-signing-key-custody.md) and every
subsequent real qualification (e.g. the base-OS update report above,
"the assistant never handled the key; the device operator ran
`scripts/sign-update-manifest.py` locally"), the production Ed25519 key
lives in the maintainer's password manager and is decrypted out to sign
offline as a distinct manual step. This is unrelated to SearXNG
specifically and applies to any future signed release.

**Finding 4 (unplanned, found while investigating Finding 1) — llama.cpp's
own image-import path was never actually wired into the real release
tooling either, and would have failed manifest validation outright if it
had been attempted.** `scripts/create-update-release.py` already writes a
`components.llama` block into the release manifest (added when llama.cpp
was deployed), but the *installed* `sovereign-update`'s
`validate_update_manifest` used `exact_keys(components, ["appliance",
"image_base", "pihole"], ...)` — a closed-set check with **no** tolerance
for extra keys. Any real release manifest built by the current
`create-update-release.py` would have been rejected outright by the
installed updater with `INVALID_MANIFEST` the moment it included the
`llama` key that script has produced since llama.cpp was added. Separately,
`activate_release`'s image import was hardcoded to `docker load` exactly
one file, `pihole-arm64.oci.tar` — llama's own OCI tar was written into
every release bundle by `create-update-release.py` but never actually
imported by `activate_release` on activation. Both gaps predate this
session's SearXNG work; SearXNG would only have made the same problem
worse (a second unrecognized component key, a second un-imported image).

## What Was Done About It

Given the above, a real signed-release qualification genuinely cannot be
completed from this session (Findings 2 and 3 are hard blockers on tooling
and authority this session doesn't have). What *was* achievable and has
been done, in this same change set:

- `scripts/create-release-bundle.py` and `scripts/create-update-release.py`
  now produce SearXNG's `searxng-image.env`/OCI-tar/manifest-component
  content the same way they already do for Pi-hole and llama.cpp.
- The installed `sovereign-update`'s manifest schema
  (`update/schema/sovereign-update-manifest-v1.schema.json` and its
  in-code twin in `validate_update_manifest`), `RELEASE_FILES`,
  `validate_release_payload`, and `activate_release` were generalized from
  a Pi-hole-only, hardcoded single-image path into a data-driven loop
  (`IMAGE_COMPONENTS`) covering Pi-hole, llama.cpp, and SearXNG uniformly.
  This closes Finding 4 for llama.cpp (previously silently broken) as well
  as adding SearXNG, rather than adding a second copy of the same latent
  bug.
- `update/examples/update-manifest-v1.example.json` and every test fixture
  that builds a release/update-bundle by hand
  (`tests/test_update_client.py`, `tests/test_update_install.py`,
  `tests/test_update_release.py`, `tests/test_update_check.py`,
  `tests/test_release_bundle.py`, `tests/test_update_manifest.py`) were
  updated to the three-component schema; the full suite (519 tests) passes,
  including a manual `jsonschema.validate` run of the updated schema
  against the updated example (the `jsonschema` package is not installed
  in this environment's system Python, so that specific test skips
  normally — verified separately via a scratch virtualenv).

This is still not a real signed-release qualification — no code path above
has been exercised by an actual CI build, an actual maintainer signature,
or an actual device activation. It removes two structural defects
(Findings 1's systemd-unit ceiling is unchanged and still open; Finding 4's
manifest/import bugs are now fixed) so that a future real qualification
pass tests real gaps, not ones already known and fixable from a desk.

## Limitations

- ~~Compose-template rendering and `nginx -t`-style deep validation
  (`validate_appliance_configuration`'s existing behavior for Pi-hole) was
  **not** extended to llama.cpp's or SearXNG's own compose templates —
  only the image-import/digest-matching half of activation was
  generalized. A malformed `llama/compose.yaml.in` or
  `searxng/compose.yaml.in` template would currently pass
  `validate_release_payload` and only fail later, at Compose-up time. This
  is a smaller, contained follow-up, not attempted here to keep this
  change's scope to what the image-import generalization actually
  required.~~ **Closed 2026-08-22**: `validate_appliance_configuration`
  now renders and runs `docker compose config --quiet` against all three
  templates (`COMPOSE_TEMPLATES`, generalizing the same loop shape
  `IMAGE_COMPONENTS` already established), not just Pi-hole's. Verified
  against real `docker` (not the fake stub the rest of this test suite
  uses elsewhere) that all three real templates pass, and that a
  structurally invalid one is rejected — see
  `tests/test_appliance_compose_validation.py`.
- Finding 1 (systemd units require a base-OS update, not an appliance
  update) remains completely open — nothing in this change set attempts a
  base-OS update mechanism change, since none is needed: the mechanism
  already exists and is already hardware-qualified for its own original
  purpose (RFC-0016). What's missing is simply *running* it for a release
  that includes SearXNG (and llama.cpp), which requires the CI build and
  maintainer signing described in Findings 2 and 3.
- None of this was exercised against a real device. The generalized
  `activate_release`/`validate_release_payload` code path is covered by
  the existing `SOVEREIGN_UPDATE_TEST_MODE=1` unit-test harness (fake
  `docker`/`systemctl`/`nginx` scripts, not real ones) — real `docker load`
  of real multi-hundred-MB ARM64 images, real activation timing under the
  900-second per-image timeout, and real rollback behavior on a real
  failure mid-multi-image-import are all unverified.

**Finding 5 (2026-08-22, found while preparing to actually trigger a real
qualification build) — `build-image.yml` itself would have failed
`build_update_candidate=true` outright.** `create-update-release.py`'s
`--searxng-env`/`--searxng-oci` are `required=True` (added alongside
Finding 4's fix), but the workflow's "Package unsigned appliance update
candidate" step was never updated to pass them — it still only passed
`--pihole-env`/`--oci`/`--llama-env`/`--llama-oci`. A real
`workflow_dispatch` run would have hit an `argparse` error and failed
before producing anything. Fixed by adding the two missing flags to the
workflow step; guarded against recurring with
`test_workflow_passes_every_image_component_flag_to_create_update_release`,
which diffs the script's actual required arguments against the
workflow's invocation rather than hardcoding a fixed flag list (so a
future fourth component gets the same protection automatically).

## Recommendation

Treat this as sufficient prep work for now; do not attempt the CI
build/sign/device-trial sequence without the maintainer's explicit
go-ahead, since it consumes real CI minutes and requires their own signing
step. When the maintainer is ready for a real qualification pass, the
sequence is: trigger `build-image.yml` with
`build_update_candidate=true`/`build_base_os_candidate=true` → maintainer
signs the resulting manifest offline (`scripts/sign-update-manifest.py`,
matching every prior release) → drive `stage`/`activate` (appliance) and/or
`stage-base-os`/`trial-base-os`/`commit-base-os` (base-OS) against real
Raspberry Pi 5 hardware, watching specifically for: multi-image `docker
load` timing/memory pressure with three real images loaded in sequence,
and any latent issue in the newly-generalized manifest/`RELEASE_FILES`
logic that the fake-tool unit-test harness can't surface.

## Unresolved Questions

- ~~Should `validate_appliance_configuration` be extended to render and
  validate llama.cpp's and SearXNG's own Compose templates the way it
  already does for Pi-hole's?~~ **Resolved 2026-08-22: yes, done** — see
  the Limitations entry above.
- Does a three-image sequential `docker load` (each up to 900s) fit
  comfortably inside whatever end-to-end time budget a real update
  transaction is expected to complete in? Untested.

## Decision Impact

PR #17's test-plan checklist item "Real signed-release qualification
(artifact/import systemd paths, real hardened sandbox)" stays unchecked —
this document is the disclosed reason why, replacing silence with an
explicit, itemized account of what was and wasn't possible from this
session, consistent with this project's own qualification-reporting
convention.
