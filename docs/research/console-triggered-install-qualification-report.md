# Console-Triggered Install Hardware Qualification Report

**Status:** Qualified on real hardware (Raspberry Pi 5)

**Date:** 2026-08-01

**Scope:** ADR-0009 (Console-triggered update install), end-to-end via the
real Console web API on a real device: login, discovery, install-trigger,
health-gated backup, staging, activation, and reboot persistence.

## Outcome

A Console-triggered install (`POST /api/v1/console/actions/install`, fresh
password required) was qualified end-to-end on a Raspberry Pi 5: discovery
found an available update, the trigger endpoint wrote the file-trigger,
the systemd path/service unit ran `sovereign-update install` as root, and
the transaction reached `committed` with the target version active,
surviving a full reboot.

Getting there took nine attempts and surfaced five distinct, real bugs —
all pre-existing, previously-unexercised code, none introduced by this
feature's own new code. Every fix was made from direct evidence (captured
output, `journalctl`, `namei -l`), not inference, after the first two
fixes based on plausible-but-wrong theories cost two wasted attempts.

## The five bugs, in the order they were found

### 1. `verify-update-health` had no retry loop at all

The health-check script used at every `sovereign-update` health gate did
a single-shot check. On real hardware, Pi-hole's restart after a backup
didn't always settle before the check ran, especially with tens of
thousands of accumulated real DNS queries slowing FTL's startup.

**Fix:** wrapped every check in a retry loop.

### 2. That retry loop's budget was still too short

A 60-second budget still lost the race on real hardware even though every
individual check passed cleanly moments later. Root cause: Docker only
updates a container's health *status* on its own healthcheck cadence
(unconfigured default: 30s interval) — polling faster doesn't help if the
status itself hasn't been re-evaluated yet.

**Fix:** extended the budget to 140s (with a 180s outer subprocess
timeout), enough to comfortably span several healthcheck cycles.

Neither of these fully explained subsequent failures. The real problem
was that `sovereign-update` discarded the health script's stdout/stderr
(`subprocess.DEVNULL`), so every failure after this point had to be
diagnosed from indirect, after-the-fact evidence — Docker's own health
log only retains its last 5 entries, so the window that mattered was
usually already gone by the time anyone looked. This is why the next two
bugs were initially misattributed to the same "Docker timing" theory
before direct evidence corrected the diagnosis:

- `verify-update-health` was rewritten to name every check and its result
  explicitly on final failure, instead of relying on `set -e` to exit on
  whichever check happened to be first.
- `sovereign-update`'s health-check call sites now capture that output
  (`run_checked_capturing`) and fold a tail of it directly into the
  transaction's failure record, so a real failure is self-diagnosing from
  `sovereign-update status` alone.

### 3. Missing `CAP_NET_BIND_SERVICE`

With the self-diagnosing rework in place, the next failure named its
cause directly: `nginx -t`, invoked by `verify-update-health`, failed
with `bind() to 0.0.0.0:80 failed (13: Permission denied)`. nginx's
config test is not a pure parse — it actually attempts to bind every
configured listen socket. `sovereign-console-install-trigger.service`'s
`CapabilityBoundingSet` stripped `CAP_NET_BIND_SERVICE` from root's
effective capabilities, so the bind failed even though the process ran
as root.

**Fix:** added `CAP_NET_BIND_SERVICE` to the unit's `CapabilityBoundingSet`.

### 4. Missing `CAP_CHOWN`

The very next attempt failed the same nginx-config check with a different
errno: `chown("/var/lib/nginx/body", 33) failed (1: Operation not
permitted)`. nginx's config test also chowns worker-owned temp
directories to the configured `user` UID — another real startup side
effect, not pure validation.

**Fix:** added `CAP_CHOWN` to the same `CapabilityBoundingSet`.

### 5. `verify-local-access`'s root/console checks raced service restart

With both capabilities fixed, activation reached much further —
`backed_up` → `staged` — before failing with `SERVICE_START_FAILED:
sovereign-local-access.service`. `journalctl` showed a stream of `curl:
(22) ... 404` from `verify-local-access`, and this same intermittent
pattern was already documented from cold-boot occurrences
(`docs/research/local-access-routing-report.md`). Its `root_redirect` and
`/console/` checks fired immediately after nginx/console restart with no
retry at all — three lines later, its *own* `/api/v1/health` check
already retried up to 30s, but the earlier checks didn't.

**Fix:** wrapped the root-redirect and `/console/` checks in the same
kind of retry loop already used elsewhere in the script.

### 6. `mkdir(mode=0o755)` silently downgraded to `0o700` under a restrictive umask

Even with fix 5 deployed, activation still failed at the same step, but
`journalctl` this time showed something unrelated to nginx or curl races:
`sovereign-console.service` (console-health) crash-looping with
`status=203/EXEC` — a failure to execute its own binary at all — which in
turn tore down `sovereign-local-access.service` every few seconds via its
`Requires=` dependency, surfacing as the same-looking
`SERVICE_START_FAILED` for a completely different reason.

`namei -l` on the freshly-staged release directory showed the answer
directly: `drwx------ root root 0.1.0-preview.22` — mode `0700`, not the
intended `0755`. `stage_release`'s `install_candidate.mkdir(mode=0o755)`
relies on `mkdir`'s `mode=` argument, which — unlike `chmod` — is always
masked by the calling process's umask.
`sovereign-console-install-trigger.service` sets `UMask=0077` (correct,
deliberate hardening for the credential-adjacent trigger flow), so every
`0o755` request was silently becoming `0o700`. The resulting release tree
was unreadable to every `DynamicUser=` appliance service that needed to
traverse into it after activation. A manual interactive
`sovereign-update stage` never exercised this — an interactive shell's
umask is normally `0022` — only the real Console-triggered path did.

**Fix:** every `mkdir(mode=0o755)` call site in `sovereign-update` now
follows up with an explicit `os.chmod(path, 0o755)`, which sets bits
absolutely regardless of umask.

## An operational lesson, not a code bug

The device was reflashed mid-qualification (see below) with
`v0.1.0-preview.18` on the reasonable-sounding theory that it was "the
last known-stable version." This was a mistake: `.18` predates ADR-0009
entirely. Its rootfs was built before the Console-triggered install
feature's systemd units (`sovereign-console-install-trigger.path/
.service`), nginx proxy routes, and `sovereign-update install` subcommand
existed at all. Those pieces are baked into the image at build time via
the rootfs overlay — they are **not** part of the incremental "appliance"
layer that `sovereign-update install` itself updates (the release
manifest's `components.appliance.version` and `components.image_base.
version` are tracked and updated separately for exactly this reason). No
amount of upgrading `.18` over the network could ever have installed
those pieces; the device had to be reflashed with a full image that
already had them (`v0.1.0-preview.21`) before the Console-triggered path
could be exercised at all.

## Timeline

| Attempt | Target | Result | Cause |
|---|---|---|---|
| 1–2 | .19, .20 | `PREUPDATE_HEALTH_FAILED` | Bugs 1–2 (found and fixed between attempts) |
| 3 | .21 | `PREUPDATE_HEALTH_FAILED` | Deployment gap: fix for bug 2 not yet redeployed onto the *active* release |
| 4 | .21 | `PREUPDATE_HEALTH_FAILED` | Bug 2 not actually sufficient; still diagnosing blind (no output capture yet) |
| — | — | — | Self-diagnosing rework of `verify-update-health` + `run_checked_capturing` |
| 5 | .21 | `PREUPDATE_HEALTH_FAILED` (nginx bind EACCES) | Bug 3, found directly from captured output |
| 6 | .21 | `PREUPDATE_HEALTH_FAILED` (nginx chown EPERM) | Bug 4, found directly from captured output |
| 7 | .21 | `SERVICE_START_FAILED` (local-access, curl 404s) | Bug 5 |
| 8 | .21 | `SERVICE_START_FAILED` (local-access again) | Device went unreachable mid-attempt; reflashed with `.18` by mistake (predates ADR-0009 entirely) |
| — | — | — | Reflashed again with `.21` (has ADR-0009's units); re-deployed all fixes onto its stale active release |
| 9 (1st retry) | .22 | `PREUPDATE_HEALTH_FAILED` | Fixes hadn't been deployed onto the fresh `.21` flash yet (it predated all of them) |
| 9 (2nd retry) | .22 | `SERVICE_START_FAILED` (console-health 203/EXEC) | Bug 6, found via `namei -l` |
| 9 (3rd retry) | .22 | **`committed`** | All six fixes in place |

## Verification performed

- Full sequence `verified → backed_up → staged → committed` via the real
  `POST /api/v1/console/actions/install` endpoint (fresh-password
  re-verification, CSRF, file-trigger, systemd path/service unit).
- All appliance services (`sovereign-console`, `sovereign-console-auth`,
  `sovereign-local-access`, `nginx`, `sovereign-pihole`) confirmed
  `active` post-activation.
- Reboot persistence: `current` symlink and its release metadata still
  pointed at the target version after a full reboot; `sovereign-update
  status` still reported `committed`.
- Full test suite (167 tests) passing after every fix, including new
  regression coverage for capabilities, the retry loops, and the umask
  bug (`test_staged_release_is_traversable_under_a_restrictive_umask`,
  which reproduces the exact `UMask=0077` condition via `preexec_fn`).

## Cleanup performed

- Disposable qualification signing key (`install-qual`) removed from
  `/etc/sovereign/update-trust.d/`; the real `sovereign-production-1`
  trust key was never touched.
- Throwaway GitHub releases `v0.1.0-preview.21` and `v0.1.0-preview.22`
  deleted.
- Qualification-only Console password left in place on the device by the
  device owner's explicit direction (development-phase test credential,
  not a production secret).
