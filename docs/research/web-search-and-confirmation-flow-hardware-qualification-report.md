# SearXNG, `web.search`/`web.fetch`, and the Confirmation Flow — Hardware Qualification Report

**Date:** 2026-08-21

**Hardware:** Raspberry Pi 5 (`sovereign.local`), the project's standing
qualification device, still on release `0.1.0-proof.3` (unchanged since
the [llama-server deployment qualification report](llama-server-deployment-qualification-report.md)
— this project's own precedent of qualifying ahead of a real signed
release continues here).

**Status:** First real-hardware exercise of RFC-0017's full scope —
SearXNG deployment, `web.search`/`web.fetch` capability implementation,
the confirmation pause/resume flow, the `external_enabled` policy toggle,
and Console's Chat UI for all of the above. A real, previously-unknown
bug was found and fixed live during this pass (see Findings).

## Method

`0.1.0-proof.3` predates the entire Conversation Service/llama-server/
Console-Chat stack — none of it had ever been deployed to this specific
device (confirmed: zero matching systemd unit files, no
`sovereign-conversation`/`start-llama-server` binaries present). A real
`rpi-image-gen` rebuild and signed release were out of scope for this
pass (as they were for the prior llama-server report). Instead, this
pass:

1. Staged the real appliance source (`lib/*.py`, `bin/sovereign-conversation`,
   `bin/console-auth`, `console/index.html`, `console/assets/*`,
   `llama/`, `searxng/`) under a writable path,
   `/data/sovereign/smoke-test-0017/`, since the device's root filesystem
   is genuinely read-only (`ext4 (ro,relatime,commit=30)`, confirmed by
   a failed `touch`) — the versioned release under `/opt/sovereign/current`
   was never modified.
2. Pulled both real pinned digests directly on the device — genuinely
   native ARM64 pulls, not a `--platform` override from another host —
   and ran everything through real `docker`/`docker compose`, not
   simulated.
3. Ran `sovereign-conversation` and (temporarily) an updated
   `console-auth` as manually-started root processes rather than under
   their real `DynamicUser`-sandboxed systemd units — the same
   documented limitation the original Conversation Service smoke test
   already disclosed ("ran as root via `sudo`, not the real `DynamicUser`
   sandbox").
4. Added a new nginx site file (`/etc/nginx/sovereign-smoke-test.conf`,
   backed up the original one-line include first) that repoints
   Console's static-file roots at the staging directory and adds the one
   new route (`/api/v1/conversation/policy`) this session's work
   introduced — every other route, including the real `/dns/` proxy and
   Pi-hole's own DNS service (port 53, entirely separate from nginx),
   was left untouched throughout.
5. Real end-to-end verification happened at two levels: direct Python
   calls against the real registry/executor (no HTTP layer, but real
   Pi-hole/SearXNG/llama-server), and a full authenticated HTTP pass
   driven by the project owner signing into the real Console in their
   own browser with their own credential — never shared with or entered
   by the assistant, matching this project's standing password-handling
   convention (`sovereign-console-password`/`sovereign-pihole-password`
   run by the operator, not the assistant).

A temporary, explicitly-scoped `NOPASSWD` sudoers rule
(`/etc/sudoers.d/sovereign-temp-agent`) was added by the project owner
for the duration of this pass, given the volume of privileged steps
involved; see Cleanup for its removal.

## Results

**llama-server** — `docker pull ghcr.io/ggml-org/llama.cpp@sha256:78e8d0748ad9...`
succeeded as a genuine native ARM64 pull. The real model
(`qwen2.5-3b-instruct-q4_k_m.gguf`, downloaded from Hugging Face)
matched its pinned SHA-256
(`626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d`)
exactly and reached the declared size (2,104,932,768 bytes) exactly. The
container reported `healthy`, and a real chat-completion request
returned a real, coherent response
(`system_fingerprint: "b10331-7ba604f1c"`).

**SearXNG** — `docker pull ghcr.io/searxng/searxng@sha256:f90ba0d666af...`
succeeded natively. With the real `settings.yml` overrides deployed
(`formats: [html, json]`, `autocomplete: ""`, `limiter: false`), a real
JSON search (`q=sovereign+os+raspberry+pi&format=json`) returned 28 real
results from real upstream engines, including this project's own GitHub
repository — the SearXNG deployment assessment's own claims, now
verified against a live query for the first time (the assessment's
Addendum had only verified this from this session's own development
machine, not the target hardware).

**Full capability registry, direct executor calls** — all five
registered capabilities exercised through the real
`sovereign_conversation.build_registry()` /
`sovereign_capabilities.invoke()` pipeline on-device:

- `system.health`: real device state — 57.9°C, 16.7% memory used, real
  network interface state. Both well inside
  [ADR-0012](../adrs/0012-local-inference-resource-and-dns-latency-budgets.md)'s
  80°C thermal and 40%-of-RAM budgets.
- `pihole.status`/`pihole.summary`: real Pi-hole, real aggregate DNS
  stats for the household's actual 12-day-uptime container (not
  reproduced here — household query volume/blocking figures are exactly
  the kind of aggregate-but-real data RFC-0006's own privacy boundary
  governs, so this report doesn't reproduce them, consistent with the
  audit log's own design choice below).
- `web.search`: policy-off correctly rejected with `CAPABILITY_DISABLED`
  before any confirmation was offered; policy-on with no token correctly
  raised `CONFIRMATION_REQUIRED`; issuing and consuming a real
  `ConfirmationStore` token then executed a real search and returned
  real trimmed results.
- `web.fetch` (SSRF policy) — the concrete, real version of the threat
  model RFC-0017 described in the abstract: `_fetch()` was pointed at
  every one of this device's own actual running loopback services
  (console-health `:8090`, console-auth `:8091`, the Conversation
  Service itself `:8092`, llama-server `:8081`, SearXNG `:8093`) and
  correctly rejected all five with `FETCH_TARGET_REJECTED`, before any
  connection was attempted. A genuine external fetch
  (`https://example.com/`) succeeded normally in the same run.
- The real on-device audit log (`/data/sovereign/capabilities/audit.jsonl`)
  confirmed the privacy-safe-by-design claim directly: every entry
  records capability/version/classification/outcome/stage/duration/result
  size, and never argument or result content — verified by reading the
  real file after real Pi-hole and search calls, not just by code
  inspection.

**Confirmation flow and policy toggle, real authenticated HTTP** — after
upgrading the live `sovereign-console-auth.service` (see Findings; done
with explicit, separately-obtained approval, since it meant restarting a
service the household's real Console sign-in depends on), the project
owner signed into the real Console in their own browser and drove the
full flow themselves: the "Allow web search" toggle, a plain chat
question, and (per their own confirmation) the search-confirmation
Approve/Deny cards. `nginx`'s real access log shows the real request
sequence (`GET`/`POST /api/v1/conversation/policy`, `POST
/api/v1/conversation/message`) from their browser's real session, and
the real audit log recorded a real `pihole.summary` invocation from that
session specifically (distinguishable from this report's own earlier
direct-Python calls by timestamp). Console, Pi-hole's admin page, and
Pi-hole's DNS service (verified live via `dig @127.0.0.1 pi.hole`
throughout) were never disrupted by any of this.

## Findings

**A real bug, caught live: `GET /api/v1/conversation/policy` always
failed with `CSRF_MISMATCH`.** `bin/sovereign-conversation`'s
`_handle_get_policy` requires the same `verify-mutating` (session **and**
CSRF) check as every other mutating-adjacent endpoint here — a
deliberate design choice (this is administrative configuration, not
liveness data). `console.js`'s `loadWebSearchPolicy()` sent
`credentials: "same-origin"` but never attached `X-CSRF-Token`, so
*every* real page load of Chat failed to read the real policy state,
surfacing as "Could not read this setting" and (per the real nginx
access log) a `403` on every single `GET /api/v1/conversation/policy`
request from the moment the project owner first loaded the page. The
`POST` (the toggle's own change handler) already included the header
correctly and worked throughout — only the read path was affected.
Fixed by adding the header to the `GET` request too, redeployed, and
reverified live: nginx's access log shows `403` on every request before
the fix and `200` on every request after it, for the identical endpoint
and identical browser session. A regression test
(`tests/test_console.py::test_toggle_reads_and_writes_the_real_policy_endpoint`)
now asserts the header is present in `loadWebSearchPolicy()`'s own
request, not just the change handler's.

**A second, structural gap, found and resolved with the project owner's
explicit approval, not worked around silently:** the device's
already-running `console-auth` predates `/api/v1/auth/verify-mutating`
(confirmed: a direct request 404'd) — meaning the Conversation Service's
entire authenticated surface was unreachable until `console-auth` itself
was upgraded. This was flagged explicitly as a more invasive action than
anything done up to that point (it meant restarting the live service
gating real Console sign-in) and only proceeded after the project owner
said so directly. Done via a systemd drop-in
(`sovereign-console-auth.service.d/smoke-test-override.conf`)
repointing `ExecStart` at the staged, updated binary — cleanly reversible
(see Cleanup), and the rest of the unit's real hardening
(`DynamicUser`, `ProtectSystem=strict`, etc.) was left completely intact,
so this specific piece *was* exercised under the real sandbox, unlike
the manually-run Conversation Service itself.

**`docker stats`' memory column reported `0B` for every container**,
including `llama-server` with a genuine ~2GB model resident — a stats-
reporting artifact of this device's cgroup configuration, not a real
zero. Recorded here so a future pass doesn't misread it as a positive
"low memory use" finding without checking another source (e.g.
`/sys/fs/cgroup` directly, or `system.health`'s own memory figures,
which reported real, sane numbers throughout via a different code path).

**`vcgencmd get_throttled` read `0xe0000`** (throttling, frequency
capping, and the soft temperature limit have each occurred *at some
point* since the device's last boot ~12 days ago) **but all four
currently-active bits were clear** — not throttled at the time of this
pass, and the live temperature reading (57.1–57.9°C) stayed well under
ADR-0012's 80°C budget throughout. Recorded as observed, not
attributed to this session's own load, since the device's own multi-day
uptime makes it impossible to tell from this bit alone when the
historical event happened.

## Limitations

- Not a substitute for a real `rpi-image-gen` build, flash, and signed
  update — every artifact/import systemd path (`verify-searxng-artifact`,
  `import-searxng-image`, `sovereign-searxng-artifact.service`, etc.)
  remains unexercised, the same disclosed gap the original llama-server
  qualification left open for its own equivalents.
- `sovereign-conversation.service` was run manually as root, not under
  its real `DynamicUser` sandbox — `ReadWritePaths=/data/sovereign/capabilities`
  genuinely creating that directory under the actual sandbox on a truly
  fresh device (rather than root's own unrestricted write access) is
  still unverified, as disclosed when this policy-state design was
  built.
- DNS-latency-during-generation and thermal budgets were not measured
  under real *concurrent* chat + search load (ADR-0012's own Required
  Follow-up already named a "realistic intermittent-use thermal pass" as
  open, unrelated to this session).
- The confirmation Approve/Deny cards specifically were verified by the
  project owner's own real browser session and their direct confirmation
  ("Works!"), not by a fresh post-fix audit-log entry captured in this
  report — the audit log's one real post-fix entry from their session is
  a `pihole.summary` call, not a `web.search` approval. The mechanism
  itself was separately, directly verified end-to-end (issue → reject
  without token → consume → execute) via direct Python calls against the
  real registry, reported above.
- `console-auth`'s upgrade was a targeted systemd override, not a real
  release — the base OS's own copy at `/opt/sovereign/current/appliance/bin/console-auth`
  is unchanged and still lacks `verify-mutating`.

## Cleanup

Everything deployed in this pass was removed after this report was
written: both containers (`sovereign-llama-server`, `sovereign-searxng`)
stopped and removed, the downloaded model deleted, the `console-auth`
systemd override removed and the service restarted back onto the
original read-only-release binary, the nginx site file reverted to its
original one-line include (config re-validated with `nginx -t` and
reloaded), the `/data/sovereign/smoke-test-0017` staging directory
removed, and the temporary `NOPASSWD` sudoers rule deleted. Pi-hole and
its DNS service were never touched at any point in this pass or its
cleanup.
