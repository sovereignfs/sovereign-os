# RFC-0015: Update Discovery — Channel Metadata and Device-Side Checking

**Status:** Accepted
**Author:** Project creator and Claude Sonnet 5
**Created:** 2026-08-01
**Reviewers:**
**Target phase:** Milestone 01.1, "Update Discovery and Console Controls" (ROADMAP item 3)
**Supersedes:** None

## Summary

Give a device a way to learn "a compatible update exists" without an
operator manually downloading and inspecting a release first. This RFC
proposes the mechanism for that check — what gets published, where, how a
device verifies and reports it — and explicitly does not propose a Console
UI or an automatic install path. Both remain out of scope until Console has
an authentication story (see [ADR-0005](../adrs/0005-sovereign-console-and-health-boundary.md)),
per the project owner's own prior decision on that boundary.

## Problem

Every update this project has qualified so far — preview.9/10, preview.11/12,
preview.13/14 — required an operator to already know a new version existed,
download its manifest and artifact by hand, and run `sovereign-update
prepare` themselves. There is no way for a device, or its owner, to find out
a compatible update exists without already knowing to look. ROADMAP item 3's
first two bullets name this directly: "publish signed update-channel
metadata over HTTPS" and "periodically check for compatible updates without
sending household data."

A second, smaller problem this RFC surfaces: **no release for this project
has ever actually been published.** `gh release list` shows only draft
releases for `preview.1` through `preview.5`; every build since, including
every version qualified this session, used `publish_draft_release: false`.
Any discovery mechanism needs something real to check against, so this RFC
also has to settle where that lives.

## Goals

- A device can determine, on its own schedule, whether a compatible update
  is available for its channel, without an operator triggering the check.
- The check reuses the existing signed-manifest trust chain — it must not
  introduce a second, weaker way to claim "this is a legitimate release."
- The check sends nothing about the household beyond what's structurally
  necessary to identify compatible releases (device type, channel, current
  version) — no query history, no telemetry, no account.
- Discovery is read-only: checking for an update never downloads the full
  artifact, stages anything, or mutates the device.
- Results are visible locally (CLI, and — for a future slice — Console's
  read-only health surface) as "notify," never "install."

## Non-Goals

- Automatic download or installation. The ROADMAP's own policy for this
  milestone is explicit: **notify and require approval**. Automatic
  maintenance-window installation is a stated later step, gated on
  repeated field qualification, not part of this RFC.
- Any Console UI or mutating trigger. Blocked on Console authentication,
  which this RFC does not attempt to solve.
- A general release CDN, mirroring, or fleet-management concept. One
  project, one GitHub repository, public releases.
- Changing how `prepare`/`backup`/`stage`/`activate` work. This RFC only
  adds a new, read-only `check` step before that existing flow.

## Context and Evidence

- The trust and verification chain already exists and is qualified:
  `inspect_update()` in `sovereign-update` verifies a manifest's signature
  against the local trust store, checks channel/device/version
  compatibility, and rejects downgrades — all without touching the
  filesystem beyond reading its inputs. See
  [RFC-0014](0014-appliance-update-system.md) and the qualification
  reports under [`docs/research/`](../research/).
- `sovereign-update-prune.timer` (this session) already establishes the
  pattern for a periodic, hardened, non-interactive systemd timer calling
  into `sovereign-update` — `check` can follow the same shape.
- GitHub Releases is the only artifact host this project uses today
  (`scripts/create-update-release.py`, `.github/workflows/build-image.yml`).
  Every qualification this session downloaded manifests and bundles from
  either workflow-run artifacts or (in principle) release assets.
- No channel concept beyond the `preview`/`stable` string already in the
  manifest schema exists. There is currently exactly one channel in active
  use (`preview`).

## Proposal

### What gets published

No new artifact type. The existing signed `release-manifest.json` /
`release-manifest.sig` pair, already produced by every build, **is** the
channel metadata — this RFC does not invent a second document format for
"here's what's new." What changes is that a release intended for discovery
must actually be published (non-draft) as a GitHub Release, with those two
files (plus the update bundle and clean image) attached as release assets,
tagged `v<version>` — matching the tagging convention `CONTRIBUTING.md`
would need to document once this ships.

### How a device finds the latest one

`sovereign-update check` (new, read-only subcommand):

1. Queries the GitHub REST API for this repository's releases
   (`GET /repos/sovereignfs/sovereign-os/releases`, unauthenticated — this
   is a public repository, and the endpoint doesn't require a token for
   read access at this volume).
2. Filters to non-draft releases whose tag parses as a valid version and
   whose asset list contains `release-manifest.json` and
   `release-manifest.sig`.
3. Selects the highest version compatible with the manifest's own declared
   `compatibility.source_versions` range for the device's *currently
   installed* version — not simply "the newest tag" — mirroring the same
   compatibility rule `prepare` already enforces.
4. Downloads only the two small manifest files for that release (not the
   multi-hundred-MB update bundle or image).
5. Runs the existing `inspect_update()` path against them — full signature
   and compatibility verification, zero new trust logic.
6. Reports the result — see Interfaces below — and does nothing else.

### Frequency and network behavior

- A new `sovereign-update-check.timer`, same shape as the prune timer:
  daily, jittered, `Persistent=true`.
- Bounded timeouts and a bounded response size on every HTTP call — a
  malicious or broken endpoint must not be able to hang the timer or
  exhaust memory/disk.
- Network failure (offline household, GitHub unreachable) is not an error
  state — it's logged and the device tries again next scheduled run. This
  must not affect `sovereign-update status`'s own health reporting for
  the *installed* system.

## Interfaces and Data Flow

```text
sovereign-update-check.timer (daily, jittered)
  -> sovereign-update check
       -> GET https://api.github.com/repos/sovereignfs/sovereign-os/releases
       -> select highest compatible non-draft release
       -> GET release-manifest.json + .sig for that release only
       -> inspect_update() [existing, unchanged]
       -> write /data/sovereign/update-state/update-check.json (atomic, like update-status.json)
```

`update-check.json` (schema sketch, not final):

```json
{
  "schema_version": 1,
  "checked_at": "2026-08-01T00:00:00Z",
  "status": "update_available",
  "current_version": "0.1.0-preview.14",
  "available_version": "0.1.0-preview.15",
  "channel": "preview",
  "notes_url": "https://github.com/sovereignfs/sovereign-os/releases/tag/v0.1.0-preview.15",
  "reboot_required": false,
  "error": null
}
```

`status` is one of `up_to_date`, `update_available`, or `check_failed`
(with `error` populated only in that last case, and never containing
anything beyond an internal error code — no raw HTTP bodies, no stack
traces persisted).

`sovereign-update status` (existing command) gains the check result as an
additional read-only field, so `/api/v1/health`'s existing `update` check
can eventually surface "an update is available" — a small, additive change
to an existing, already-qualified interface, not a new health check.

## Security and Privacy

- The GitHub API call sends only what an unauthenticated HTTPS GET to a
  public repository's releases endpoint inherently sends — no device
  identifier, no household data, no query string beyond what the endpoint
  itself defines.
- No new trust root. A release is only ever reported as "available" if it
  passes the exact same signature verification `prepare` already requires.
- `check` must not download or execute anything beyond the two small,
  independently-authenticated manifest files — it never fetches the
  multi-hundred-MB bundle.
- TLS certificate verification is mandatory and not configurable off.
- `update-check.json` and the check log must not contain credentials, DNS
  query data, or household-identifying detail, matching the same rule
  already enforced for the transaction journal in
  [BACKUP_AND_JOURNAL.md](../../update/BACKUP_AND_JOURNAL.md).

## Failure and Recovery

- Every failure mode (network unreachable, malformed response, signature
  mismatch, rate-limited) writes `status: "check_failed"` with a bounded,
  non-secret error code and leaves the previous `update-check.json` result
  otherwise untouched — a transient failure must not erase yesterday's
  "update available" notice.
- `check` never touches `/opt/sovereign/releases/` or the update-transaction
  journal — a failed or interrupted check cannot leave the device in any
  state requiring `recover` or `discard`, because it never enters that
  state machine at all.

## Compatibility and Migration

- Purely additive: a new subcommand, a new timer, and a new field on an
  existing status file. No change to the `prepare`/`backup`/`stage`/
  `activate` transaction flow, its schema, or its qualified behavior.
- Devices that never run `check` (e.g. air-gapped, or before this ships)
  behave exactly as they do today.

## Operations and Observability

- `sovereign-update check` is runnable manually, same as `prune`.
- Journalctl output for `sovereign-update-check.service` follows the same
  convention as every other Sovereign systemd unit — human-readable,
  non-secret.
- This RFC does not require publishing real (non-draft) releases as a
  *precondition of merging the code* — `check` degrades to
  `check_failed`/no compatible release found against an empty or
  all-draft release list, which is exactly today's actual state and is a
  legitimate, harmless outcome. Publishing real releases is a separate
  operational decision for the project owner, orthogonal to this RFC.

## Testing Strategy

- Unit tests against a fake HTTP transport (no real network calls in CI),
  covering: no releases published, only draft releases, a compatible
  release found, an incompatible-version release skipped, a
  signature-mismatched release rejected, malformed/oversized responses
  rejected, and a network-timeout path.
- Hardware qualification once a real non-draft release exists to check
  against — deferred until that publishing decision is made, matching how
  every other command in this project got unit-tested first and
  hardware-qualified once real conditions existed to test it against.

## Alternatives Considered

### A dedicated channel-metadata document, separate from release manifests

Publish a small `channel-preview.json` pointer file (version + manifest
URL) instead of listing GitHub releases directly. Rejected for v1: it adds
a second document to keep in sync with every release, a second thing to
sign, and a second place trust can drift, for no benefit over querying
GitHub Releases directly while there is exactly one channel and one
publisher. Worth revisiting if this project ever needs a release host
other than GitHub, or per-channel metadata GitHub's API can't express.

### Poll a self-hosted or third-party update-metadata service

Rejected outright — directly contradicts the project's self-hosted,
no-mandatory-third-party-dependency values, and GitHub Releases already
serves this exact purpose for free on a public repository.

## Drawbacks and Maintenance Cost

- A new outbound network dependency (GitHub's API) on a device that
  otherwise needs no internet access for its core DNS function. Framed
  and gated as strictly opt-in-by-default-off until this RFC is accepted
  and the timer is actually enabled in a shipped image.
- GitHub API rate limits for unauthenticated requests are per-source-IP,
  not per-device from GitHub's point of view if many devices share a
  household's public IP — unlikely to matter at today's scale, but worth
  naming.

## Unresolved Questions

- Should `channel` in the device's `update-policy.json` gain an explicit
  opt-out for `check` entirely (fully air-gapped households)? Leaning
  yes, deferred to implementation.
- Exact retry/backoff behavior on GitHub rate-limiting vs. genuine
  failure — needs a decision during implementation, not this RFC.
- When (not if) real non-draft releases start being published, does that
  become part of the existing `build-image.yml` workflow's normal path,
  or a separate manual promotion step? Release-process question, not an
  architecture question — recommend deciding alongside production
  signing-key generation (ADR-0006), since both are needed together
  before this is meaningfully usable end to end.

## Acceptance Criteria

- `sovereign-update check` and `sovereign-update-check.timer` implemented,
  unit-tested per the Testing Strategy above.
- `sovereign-update status` includes the last check result.
- No change to any existing command's behavior or exit codes.
- Documented in `update/README.md` and cross-linked from
  `docs/operations/update-recovery-and-compatibility.md`.
- Explicitly does not require a Console change or a production signing key
  to merge — both remain separately gated as described above.

## Decision

Accepted by the project owner on 2026-08-01, as scoped: device-side
check-and-notify only, no Console change, no production signing key
required to merge. Publishing real (non-draft) releases and the exact
retry/backoff and air-gap opt-out details are left to implementation, per
the Unresolved Questions above.
