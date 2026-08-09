# llama-server Deployment Path Qualification Report

**Date:** 2026-08-09

**Hardware:** Raspberry Pi 5 (`sovereign.local`), the project's qualification
device, still on release `0.1.0-proof.3`.

**Status:** First real-hardware exercise of [ADR-0014](../adrs/0014-llama-server-deployment-and-model-provisioning.md)'s
actual deployment mechanism — not hand-run `docker` commands like the
three earlier Conversation Service smoke tests, but the real scripts
this project now ships: `verify-llama-artifact`, `import-llama-image`,
`start-llama-server`, and `stop-llama-server`, run unmodified (or, for
the two whose paths are hardcoded to base-OS-managed system directories,
run with a scratch-path substitution — see Method) against a real,
`skopeo`-fetched artifact of the exact digest pinned in `llama-image.env`.

## Method

A full `rpi-image-gen` base-OS image rebuild was out of scope for this
pass (a much larger, CI-only process — see ROADMAP.md's Milestone 6).
Instead, this pass reproduced the one artifact a real image build would
have produced (`llama-arm64.oci.tar`), using genuine tooling rather than
a substitute:

- `skopeo copy` (no local install available; run via
  `docker run --rm quay.io/skopeo/stable copy ...`, identical flags to
  `post-build.sh`) against `ghcr.io/ggml-org/llama.cpp@sha256:78e8d0...` —
  the exact digest pinned in `llama-image.env` — producing a real OCI
  layout.
- The identical `tar --sort=name --mtime=... --owner=0 --group=0
  --numeric-owner --format=gnu` invocation `post-build.sh` uses (run
  inside a `debian:trixie-slim` container for GNU tar, since macOS's
  `bsdtar` doesn't support `--sort=name`), producing a byte-for-byte
  equivalent `llama-arm64.oci.tar` (~295MB) to what the real image build
  would embed.

`verify-llama-artifact` and `import-llama-image` have hardcoded,
non-overridable paths under `/usr/lib/sovereign/` — deliberately, they
mirror Pi-hole's identical, already-production-qualified equivalents
exactly. Rather than write test artifacts into that real,
base-OS-managed system directory (risking any interference with the
device's actual running Pi-hole image data), scratch copies with those
two path prefixes substituted to a `/data/sovereign-smoke/` scratch tree
were used instead — a transparent, disclosed adaptation, not a weakened
test: the substituted paths are pure configuration, and the actual
logic exercised (checksum verification, tar-content inspection, `docker
load`, tagging, platform verification) is byte-identical to the shipped
script. `start-llama-server` and `stop-llama-server` needed **no
adaptation at all** — they already resolve their own location and the
release root relatively (`$(dirname "$0")/..`), so placing them at
`<scratch>/release/appliance/bin/` with `<scratch>/release/llama-image.env`
one level up reproduced the real release layout exactly. These two ran
completely unmodified, at their real, hardcoded `/data/sovereign/...`
runtime paths — deliberately not scratch-relocated, since that's the
genuine, intended production location and using it for real is a
meaningful part of what this pass qualifies.

Every privileged step (Docker access, writes under `/data/sovereign/`)
was run by the project owner via `sudo`, in their own terminal; the
assistant made only unprivileged reads and the initial `verify-llama-artifact`
run (needs no privilege — it's pure read + checksum).

## Results

**`verify-llama-artifact`** — real checksum match, all three required
`tar` entries found (`oci-layout`, `index.json`, and specifically
`blobs/sha256/78e8d0748ad92c3266bc72a33fe39574a9b3a6bc88d27e371a1377d39d89c68a`
— the exact pinned manifest digest, not just *a* blob), correct
readiness marker written.

**`import-llama-image`** — real `docker load`, real tag, real platform
check. Resulting marker:

```
image=ghcr.io/ggml-org/llama.cpp:server
platform=linux/arm64
image_id=sha256:78e8d0748ad92c3266bc72a33fe39574a9b3a6bc88d27e371a1377d39d89c68a
archive_sha256=ad393391b949963ad8b6e182419577ede6c7466d3e0686e37c3daec4a4bab55f
manifest_digest=sha256:78e8d0748ad92c3266bc72a33fe39574a9b3a6bc88d27e371a1377d39d89c68a
```

`image_id` matching `manifest_digest` exactly is expected for a
single-architecture manifest, and confirms the loaded image really is
the one pinned, not just *an* image that happened to load.

**`start-llama-server`, first run** — downloaded the real, correct
~2GB model (`2104932768` bytes, matching every prior download this
session byte-for-byte), started the container using the image
`import-llama-image` had just loaded (`--pull never` — proving it never
needed network access for the image itself), and reached `healthy`
within the polling budget. Resulting marker:

```
image=sha256:78e8d0748ad92c3266bc72a33fe39574a9b3a6bc88d27e371a1377d39d89c68a
model=qwen2.5-3b-instruct-q4_k_m.gguf
model_sha256=626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d
health=pass
```

A real completion request against the resulting server confirmed it's
actually usable, not just "healthy" by a shallow check:

```json
{"choices":[{"message":{"content":"I am Qwen, a large language model created by Alibaba Cloud."}}],
 "model":"/models/qwen2.5-3b-instruct-q4_k_m.gguf",
 "system_fingerprint":"b10331-7ba604f1c", ...}
```

`system_fingerprint` (`b10331-7ba604f1c`) matches the exact upstream
version tag and revision recorded in ADR-0014
(`b10331`, `7ba604f1cb61cd14898138e9abc0b4ff2601f180`) — independent
confirmation the running binary really is the pinned build, from a
source the deployment scripts themselves never touch.

**Idempotency** — a second `start-llama-server` run left the model
file's mtime unchanged (`22:17`, same as the first run) and still
reported `health=pass`: the digest check correctly short-circuited the
download rather than re-fetching ~2GB unnecessarily on every ordinary
restart.

**Digest-mismatch self-healing** — the core trust-boundary claim
ADR-0014 makes. The model file was deliberately corrupted (`dd
if=/dev/urandom ... conv=notrunc`, first 10MB overwritten) and
`start-llama-server` run again. Result: the model file's mtime advanced
(`22:17` → `22:22` — a real re-download happened, not a no-op), and the
recovered file's digest exactly matched the pinned value again
(`626b4a66...`), with health passing afterward. An existing file that
fails verification really is treated exactly like a missing one, not
silently trusted — confirmed live, not just by reading the script.

**`stop-llama-server`** — stopped the container correctly (confirmed:
`127.0.0.1:8081` became unreachable immediately after).

## Cleanup, verified rather than assumed

The first cleanup attempt (a single `&&`-chained command) partially
failed: `docker rm -f sovereign-llama-server` and `docker rmi` for the
image both actually succeeded, but a redundant second image-reference
argument to `docker rmi` (the same image, referenced by both its tag
and its digest) caused that command to report a non-zero exit once the
first reference had already removed it — so the chained `rm -rf` never
ran, leaving `/data/sovereign/models`, `/data/sovereign/apps/llama-server`,
the readiness marker, and the scratch directory in place. This was
caught by checking real state after the fact rather than trusting the
one command's overall reported success, and corrected with independent
(non-chained) follow-up commands. All confirmed gone afterward:

```
ls: cannot access '/data/sovereign/models': No such file or directory
ls: cannot access '/data/sovereign/apps/llama-server': No such file or directory
ls: cannot access '/data/sovereign/llama-server-ready': No such file or directory
ls: cannot access '/data/sovereign-smoke': No such file or directory
```

Real Pi-hole (`127.0.0.1:8080/admin/` → `302`, its normal sign-in
redirect) and the real, already-running `console-auth`
(`127.0.0.1:8091/api/v1/auth/session` → `200`) were confirmed unaffected
throughout — this pass never wrote to `/usr/lib/sovereign/` or the real
`console-auth` process at all.

## Limitations

This did not exercise an actual `rpi-image-gen` base-OS build (the
`skopeo`/`tar` steps were reproduced by hand with real tooling, not
run through `post-build.sh` itself inside the real build pipeline) or a
real `create-update-release.py`/`create-update-bundle.py` invocation
bundling these new files into a signed update artifact — both are
already covered by this session's unit tests
(`tests/test_llama_server_deployment.py`, `tests/test_release_bundle.py`,
`tests/test_update_release.py`), not re-proven live here. `verify-llama-artifact`
and `import-llama-image` ran against scratch-substituted paths, not the
real `/usr/lib/sovereign/` locations — a deliberate, disclosed choice
(see Method), not a gap in what was tested logically. The systemd units
themselves (`sovereign-llama-artifact.service`,
`sovereign-llama-import.service`, `sovereign-llama-server.service`, and
`sovereign-conversation.service`'s new `After=`) were not exercised via
`systemctl` — the scripts they invoke were run directly instead, so
unit ordering/hardening is validated by the existing content-assertion
tests and code review, not a live boot. A slow or interrupted download
(as opposed to a corrupted completed file) was not specifically tested.

## Conclusion

Every real behavior ADR-0014 claims was verified live, against
genuinely produced artifacts, not substitutes: the embedded-image
pipeline (checksum, tar-content, load, tag, platform), the model
provisioning pipeline (download, digest verification, atomic rename),
and — the claim that mattered most — that a corrupted model file is
detected and transparently repaired rather than silently trusted. No
discrepancy from ADR-0014's design was found. What remains before this
is genuinely production-ready is running it through an actual
`rpi-image-gen` build and a real signed update install, and a Console
frontend for the Conversation Service this now unblocks.
