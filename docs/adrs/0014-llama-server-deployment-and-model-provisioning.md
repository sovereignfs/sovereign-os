# ADR-0014: llama-server Deployment and Model Provisioning

**Status:** Accepted

**Date:** 2026-08-09

**Decision owner:** Project creator

**Related RFCs/research:**
[RFC-0002](../rfcs/0002-local-conversation-and-inference-runtime.md) (Accepted;
names "Sovereign Model Management" as a real but separately-scoped
component, and requires digest verification "the same supply-chain
posture the appliance updater already applies to release bundles and
Pi-hole images"),
[ADR-0013](0013-initial-inference-runner-and-model-selection.md) (Accepted;
selects llama.cpp + Qwen2.5-3B-Instruct-Q4_K_M),
[conversation-service-smoke-test-report.md](../research/conversation-service-smoke-test-report.md)
and
[conversation-service-authentication-smoke-test-report.md](../research/conversation-service-authentication-smoke-test-report.md)
(both real-hardware passes that manually stood up llama-server via
Docker each time, with no lasting footprint on the device).

**Supersedes:** None

## Context

The Conversation Service is implemented, tested, auth-wired, and
smoke-tested twice on real hardware — but only ever against a
hand-started, throwaway `docker run` the project owner ran themselves
each time. Nothing on the device runs llama-server persistently, and
`sovereign-conversation.service` is deliberately not in
`customize90-sovereign`'s enable-units list because of exactly that gap:
enabling it today would ship a service that always returns
`PROVIDER_UNAVAILABLE`.

Closing this gap means building the piece RFC-0002 named but explicitly
did not commit to implementing there: "Sovereign Model Management —
download or offline import with checksum verification before a model is
ever loaded... persistent storage beneath `/data/sovereign/models/`."
This ADR scopes and decides a **minimal** version of that — enough to
run the one pinned runner/model ADR-0013 already selected, not the full
multi-model identity/lifecycle/rollback system RFC-0002 describes as a
later concern.

### A real constraint this decision must work within

Pi-hole's own container image is embedded directly in the base OS image
and every subsequent release bundle: `image-builder/sovereign/post-build.sh`
uses `skopeo copy` at **image build time** to fetch the exact
digest-pinned image (`pihole-image.env`) into
`/usr/lib/sovereign/artifacts/pihole-arm64.oci.tar`, which ships inside
the release the same way `appliance/bin/*` does. That works because
Pi-hole's image is small. The qualification device's actual A/B system
partition has almost no room to spare —
`df` on `sovereign.local` during this session's smoke tests showed
`/dev/disk/by-slot/active/system` at **2.9G total, only ~2.0G free**.
Qwen2.5-3B-Instruct-Q4_K_M alone is **~2GB** (`2104932768` bytes,
confirmed twice this session via real download). Embedding the model
weights the same way Pi-hole's image is embedded would not fit —
not "would be wasteful," would not physically fit next to everything
already on that partition.

llama.cpp's own container image (`ghcr.io/ggml-org/llama.cpp:server`),
by contrast, is a normal-sized container image with no model weights
baked in — the same rough size class as Pi-hole's — and has no reason
not to follow Pi-hole's existing, already-qualified embedding pattern.

## Decision

Split the runner and the model weights into two different provisioning
paths, matching where each one actually fits.

### 1. The llama.cpp runner image: embedded, exactly like Pi-hole's

Add `llama-image.env` (repository, tag, digest, platform — same shape as
`pihole-image.env`), pinned to a specific digest of
`ghcr.io/ggml-org/llama.cpp:server`. `post-build.sh` gains the same
`skopeo copy` step Pi-hole's already has, producing
`/usr/lib/sovereign/artifacts/llama-arm64.oci.tar`, shipped in the base
image and every release the same way. Three new systemd units mirror
Pi-hole's exact three-stage shape 1:1:

- `sovereign-llama-artifact.service` → `verify-llama-artifact` (sha256
  the embedded archive, mirrors `verify-pihole-artifact`)
- `sovereign-llama-import.service` → `import-llama-image` (`docker load`
  + digest + platform check + readiness marker, mirrors
  `import-pihole-image`)
- `sovereign-llama-server.service` → `start-llama-server` /
  `stop-llama-server` (mirrors `sovereign-pihole.service` /
  `start-pihole` / `stop-pihole`)

### 2. The model weights: downloaded into `/data`, verified on every start

Not embedded — RFC-0002's own words apply here, not the Pi-hole
pattern: "download or offline import with checksum verification before
a model is ever loaded... persistent storage beneath
`/data/sovereign/models/`."

`start-llama-server` gains the download/verify step inline (the same
shape `start-pihole` already uses for its own idempotent
generate-if-missing password step — no separate systemd stage needed
for something this simple):

- If `/data/sovereign/models/qwen2.5-3b-instruct-q4_k_m.gguf` is
  missing, download it from the exact URL every benchmark report's own
  "Reproduction" section already uses
  (`https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf`),
  to a `.tmp` path, atomically renamed on success (matching
  `pihole-admin-password`'s own tmp-then-`mv` pattern).
- **Verify the SHA-256 digest against a pinned value on *every* start,
  not just at download time** — an existing file that fails the check
  is treated exactly like a missing one (re-downloaded), not silently
  trusted. This is the actual trust boundary, not the URL: pointing at
  `resolve/main` (HuggingFace's mutable "current file on this branch"
  path, not an immutable commit-pinned URL) is fine specifically
  *because* nothing downstream ever trusts the file without this check
  — if the upstream file ever changed, the digest check fails closed and
  triggers a fresh download attempt, not silent use of an unverified
  artifact.
- The pinned digest is recorded the same way `PIHOLE_IMAGE_DIGEST` is:
  computed once from a real download (this project already has
  `qwen2.5-3b-instruct-q4_k_m.gguf`'s digest from two independent real
  downloads to `sovereign.local` this session, both landing on the
  identical byte count) and checked into a new `llama-model.env`.
  Confirmed a third time from a fresh download during this ADR's own
  implementation, all three landing on the identical `2104932768`-byte
  file: `sha256:626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d`
  (cross-checked against the `md5:45fc4fbbb4e49a4da2d68fd372d1e6b5` this
  project's own real-hardware smoke test reports already recorded). The
  llama.cpp runner image is pinned the same way, from a real registry
  query against `ghcr.io/ggml-org/llama.cpp:server`'s current manifest
  index: `sha256:78e8d0748ad92c3266bc72a33fe39574a9b3a6bc88d27e371a1377d39d89c68a`
  for `linux/arm64` (revision `7ba604f1cb61cd14898138e9abc0b4ff2601f180`,
  upstream version tag `b10331`, as of 2026-08-09).

### 3. Wiring `sovereign-conversation.service` to it

`sovereign-conversation.service` gains
`After=sovereign-llama-server.service` — deliberately `After=`, not
`Requires=`. The Conversation Service already has a real, tested
degraded state for this (`ProviderError` → `TurnError("PROVIDER_UNAVAILABLE", ...)`
→ HTTP 502), so a llama-server that's still downloading the model or has
failed to start should produce that existing, well-defined degraded
response, not prevent the Conversation Service itself from starting.

### 4. Auto-enabling

Both `sovereign-llama-server.service` (which pulls in the artifact/import
stages via its own `Requires=`/`Wants=`, matching Pi-hole's shape) and
`sovereign-conversation.service` are added to `customize90-sovereign`'s
enable-units list. This is the concrete change the milestone has been
blocked on.

### Explicitly out of scope

- Multiple models, model switching, activation/rollback, or any
  per-model lifecycle state — this ADR pins exactly the one runner/model
  combination ADR-0013 already selected. A real "Sovereign Model
  Management" component (RFC-0002's fuller vision) is future work this
  ADR does not attempt.
- Changing the pinned model or runner without a new ADR.
- Any mechanism to update the model independently of an appliance
  software update.

## Consequences

### Positive

- Unblocks the one thing standing between "the Conversation Service is
  a tested, working API" and "a household can actually reach it without
  the project owner hand-starting Docker containers."
- Reuses Pi-hole's exact, already-hardware-qualified embedding pattern
  for the runner image — no new mechanism to design or trust there.
- The always-re-verify-on-start rule means a corrupted or tampered model
  file self-heals (re-downloads) rather than silently degrading answer
  quality or crashing llama-server in a confusing way.

### Negative

- **A fresh install's first boot needs real internet access and a
  multi-minute, ~2GB download before conversation works at all** — a
  real regression from "fully offline after the base image is written,"
  which is how Pi-hole itself already works. This is a genuine tension
  with this project's own name and stated posture, not a minor detail.
- The model source is a third-party host (HuggingFace), not
  self-hosted — this project has already implicitly accepted that
  precedent (every benchmark report's Reproduction section already
  points there), but this ADR is the first time it becomes something
  the appliance itself does unattended, not something the project owner
  types by hand for a benchmark run.
- Re-verifying a ~2GB file's SHA-256 on every service start adds real
  time (low-single-digit seconds on this hardware class) to every
  `sovereign-llama-server.service` start, including ordinary boots once
  the file already exists and is valid.

### Risks

- If HuggingFace is unreachable on first boot (household network not
  yet configured, outage, etc.), the Conversation Service stays
  degraded indefinitely until connectivity exists and the unit is
  restarted — there is no offline-import fallback path in this
  ADR's scope, unlike Pi-hole's fully-embedded image.
- A future decision to change the pinned model requires a new ADR *and*
  a fresh multi-GB download on every existing device — there is
  currently no delta-update mechanism for model weights the way
  appliance releases have one for code.

## Alternatives Considered

- **Embed the model weights the same way as Pi-hole's image.** Rejected
  outright — does not fit in the ~2.0GB free on the real device's A/B
  system partition, confirmed this session, not a theoretical concern.
- **Use Ollama's own `pull`-and-cache mechanism instead of a manual
  curl+digest-verify step.** Rejected — ADR-0013 already selected
  llama.cpp specifically (better v1-corpus accuracy, no cold-start
  penalty); re-introducing Ollama here just to inherit its model-pull
  UX would undo that decision for a convenience this project can build
  directly in ~20 lines of shell, with an explicit verify-before-use
  guarantee Ollama's own pull flow doesn't specifically promise.
- **A separate systemd stage for model download/verify, mirroring the
  artifact/import split used for the container image.** Rejected as
  unnecessary ceremony for this scope — `start-pihole` already
  establishes the precedent that a single idempotent step inside the
  main start script is the right shape for "generate/fetch this one
  thing if it's missing," and the model-download step is no more
  complex than that.

## Validation and Revisit Conditions

- Revisit if the A/B system partition's size budget ever changes
  meaningfully (e.g., a base-OS layout change) — embedding might become
  viable and would remove the first-boot download dependency entirely.
- Revisit once a real "Sovereign Model Management" component (multi-model,
  activation, rollback) is actually built — this ADR's mechanism should
  likely be absorbed into or replaced by it, not maintained in parallel.
- Revisit if ADR-0013's runner/model selection is ever revisited — this
  ADR's pinned digests and URLs are specific to that exact selection.
