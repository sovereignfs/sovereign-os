# Contributing to Sovereign OS

Thank you for your interest in contributing. This document covers everything
you need to get started.

## Contents

- [Development setup](#development-setup)
- [Branching and commits](#branching-and-commits)
- [Pull requests](#pull-requests)
- [Proposing a change (research, RFCs, ADRs)](#proposing-a-change-research-rfcs-adrs)
- [Hardware qualification](#hardware-qualification)

---

## Development setup

**Requirements:** Python 3 (standard library only — the update client and its
tests take no external dependencies), `shellcheck`, `zstd`, `openssl`, `tar`,
and Git. No virtualenv or `pip install` step is needed.

```bash
git clone https://github.com/sovereignfs/sovereign-os.git
cd sovereign-os
python3 -m unittest discover -s tests -v
```

**Shell scripts:** every shell script under `scripts/` and `image-builder/`
must pass strict shellcheck, matching CI:

```bash
find scripts image-builder -type f -name '*.sh' -print0 \
  | xargs -0 shellcheck --severity=error
```

(CI checks every file whose shebang matches `sh`/`bash`, not just `*.sh`
names — see `.github/workflows/ci.yml`.)

**Building the Raspberry Pi image:** the full image build requires
`rpi-image-gen` on an ARM64 Debian/Ubuntu host and is normally run via the
**Build Raspberry Pi image** GitHub Actions workflow
(`.github/workflows/build-image.yml`, `workflow_dispatch`), not locally. See
[docs/operations/image-build-and-release.md](docs/operations/image-build-and-release.md)
and [docs/operations/image-release-checklist.md](docs/operations/image-release-checklist.md).
Most contributions — docs, RFCs/ADRs, the `sovereign-update` Python client,
and its tests — need none of that.

### Running the tests

```bash
python3 -m unittest discover -s tests -v
```

This is the same command CI runs (`.github/workflows/ci.yml`, the
`Validate` workflow), alongside shellcheck and a repository whitespace check.
There is no separate lint/format/typecheck step — Python here is
standard-library-only and kept deliberately simple.

Tests that exercise real archive/signing behavior (e.g.
`tests/test_update_restore.py`, `tests/test_update_prune.py`,
`tests/test_trust_rotation.py`) build fixtures with the real `openssl` and
`zstd` binaries rather than mocking them, so those tools must be on `PATH`
for the full suite to run; tests skip themselves cleanly if they're missing.

---

## Branching and commits

Always branch from an up-to-date `main`:

```bash
git switch main && git pull
git switch -c feat/your-change-name
```

**Branch prefixes:**

| Prefix   | Use for                                          |
| -------- | ------------------------------------------------- |
| `feat/`  | New features or capabilities                       |
| `fix/`   | Bug fixes                                          |
| `docs/`  | Documentation only                                 |
| `chore/` | Tooling, scaffolding, dependencies, maintenance    |

Branch names, commit messages, PR titles, and PR descriptions describe the
work by what it changes — not by roadmap slot versions or task numbers,
which shift as the roadmap evolves.

**Commit messages** should explain *why*, not just *what*. Keep the subject
line under 72 characters; wrap body lines around 100.

If an AI assistant helped write the change, include its co-author trailer:

```text
Co-Authored-By: Codex <noreply@openai.com>
```

```text
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

Use whichever trailer matches the assistant that actually did the work; see
`AGENTS.md` for agent-specific conventions (branch/commit rules there are
authoritative for agents working unattended — this document is the
human-facing superset).

---

## Pull requests

- **One logical change per PR.** Keep scope tight.
- All CI checks must pass before review: shellcheck (`--severity=error` over
  every shell script), the full `unittest` suite, and the repository
  whitespace check (`.github/workflows/ci.yml`).
- If your change touches an accepted RFC or ADR, cite the relevant section in
  the PR description.
- Include verification output in the description — test results, and for
  anything touching the appliance updater or image, hardware qualification
  evidence (see [Hardware qualification](#hardware-qualification) below).
- When an agent opens a PR, it defaults to **draft** unless the user
  explicitly asks for ready-for-review (see `AGENTS.md`).
- Update the relevant docs in the same PR as the behavior they describe —
  `ROADMAP.md`, the affected `docs/roadmap/`, `docs/rfcs/`, or
  `docs/operations/` file, and any research/qualification report the change
  produces. Docs are part of the change, not a follow-up.

---

## Proposing a change (research, RFCs, ADRs)

The full process — roles, the planning chain, document types, and definition
of done — is defined in
[docs/development/workflow.md](docs/development/workflow.md). In short:

- **Just an idea or a question?** Open a GitHub issue, or, for an
  open-ended question with no concrete proposal yet, write a
  [research note](docs/templates/research-note.md) under
  [`docs/research/`](docs/research/).
- **Want to propose what the project should build?** Write an RFC using the
  [RFC template](docs/templates/rfc.md), add it under
  [`docs/rfcs/`](docs/rfcs/) with the next unused zero-padded number, and add
  a row to [`docs/rfcs/README.md`](docs/rfcs/README.md). An RFC is a
  proposal, not a decision — do not mark it Accepted yourself; that requires
  project-owner approval.
- **Recording an accepted architectural decision?** Write an ADR using the
  [ADR template](docs/templates/adr.md), add it under
  [`docs/adrs/`](docs/adrs/) with the next sequential number, and add a row
  to [`docs/adrs/README.md`](docs/adrs/README.md).

Not every change needs an RFC or ADR — see "Work Item Readiness" in
`docs/development/workflow.md` for when implementation can begin directly.

---

## Hardware qualification

Sovereign OS is a flashable Raspberry Pi appliance image, not a hosted
service — a change that only passes unit tests has not been verified the
same way it will actually run. Anything that touches the appliance updater
(`sovereign-update`), the image-builder overlay, systemd units, or Console/
Nginx/Pi-hole routing is not considered done from code review and unit tests
alone; **real-hardware verification is part of the definition of done** (see
`docs/development/workflow.md`).

Precedent for how to run and record this lives under
[`docs/operations/`](docs/operations/) (e.g.
[versioned-appliance-update-qualification.md](docs/operations/versioned-appliance-update-qualification.md))
and prior evidence is recorded as research reports under
[`docs/research/`](docs/research/) (e.g.
[restore-hardware-qualification-report.md](docs/research/restore-hardware-qualification-report.md)).
Follow that pattern: state what was tested, the exact commands/results, and
what remains unverified — do not claim hardware qualification without it.
