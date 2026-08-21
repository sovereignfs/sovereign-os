# SearXNG Deployment Assessment

**Status:** Concluded
**Author:** Project creator and Claude
**Started:** 2026-08-21
**Concluded:** 2026-08-21
**Decision informed:** [RFC-0017](../rfcs/0017-web-search-and-fetch-capability-mapping.md) (Draft), the same relationship [pihole-api-assessment.md](pihole-api-assessment.md) had to [RFC-0006](../rfcs/0006-pihole-capability-mapping.md). See the Addendum below for a later live-verification pass that closed several of this document's original Unresolved Questions and fed the real image-builder implementation (`image-builder/sovereign/searxng-image.env` and `appliance/searxng/`).

## Question

[ADR-0004](../adrs/0004-provider-neutral-assistant-and-web-search.md) already
decided *that* SearXNG is the initial `web.search` provider. It left
"document SearXNG deployment, upstream configuration, retention, and failure
behavior" as an open Required Follow-up item, and
[ROADMAP.md](../../ROADMAP.md) names that undocumented decision as the
reason `web.search`/`web.fetch` haven't been implemented. This document
answers the deployment question: which container image, which local port,
which `settings.yml` overrides, and which defaults are wrong for a private,
single-user, on-device instance rather than the public instances SearXNG's
own documentation and defaults are written for.

## Context

This project has embedded two other third-party containerized services the
same way already — Pi-hole (`image-builder/sovereign/pihole-image.env`) and
llama.cpp's server (`image-builder/sovereign/llama-image.env`) — both
pinned by repository, tag, and a real `skopeo`-verified digest, both
imported and run through the same artifact/import/server three-stage
systemd shape. A SearXNG deployment would extend that established pattern,
not invent a new one. There is no Raspberry Pi hardware available in this
session to run `skopeo inspect` against the real registry or to measure
actual resource usage alongside the device's existing Pi-hole and
llama-server load, so this document is a documentation-grounded desk
assessment, not a hardware qualification report — see Limitations.

## Evaluation Criteria

- Official container image source, and whether an ARM64 build exists.
- Local port allocation, checked against every port this project's own
  `nginx/sovereign.conf` already binds to.
- Which `settings.yml` defaults are wrong for "private, single-user,
  never-exposed-beyond-loopback" versus SearXNG's own public-instance-tuned
  defaults.
- Whether the machine-readable JSON output RFC-0004's `web.search`
  capability would need to parse is available by default.
- Realistic resource footprint on a 16GB Raspberry Pi 5 that already runs
  Pi-hole and llama-server under
  [ADR-0012](../adrs/0012-local-inference-resource-and-dns-latency-budgets.md)'s
  40%-of-RAM ceiling.
- License obligations from running it, given this project's own AGPL/GPL
  precedent with Pi-hole.

## Sources and Environment

Desk research only, against SearXNG's own official documentation and
source, not a running instance:

- [SearXNG Docker installation guide](https://docs.searxng.org/admin/installation-docker.html)
- [SearXNG settings.yml reference](https://docs.searxng.org/admin/settings/settings.html)
- [SearXNG's default `settings.yml` source](https://github.com/searxng/searxng/blob/master/searx/settings.yml)
- [SearXNG limiter/botdetection documentation](https://docs.searxng.org/admin/searx.limiter.html)
- [SearXNG JSON search API documentation](https://docs.searxng.org/dev/search_api.html) (already cited as a source in [local-ai-options.md](local-ai-options.md))
- [searxng/searxng `.env.example`](https://github.com/searxng/searxng/blob/master/container/.env.example)
- [searxng/searxng LICENSE](https://github.com/searxng/searxng/blob/master/LICENSE)
- [GitHub Discussion #2359 — "8+ GB of memory usage for a fresh searxng/searxng docker pull?"](https://github.com/searxng/searxng/discussions/2359)
- [GitHub Discussion #3884 — "Recommended Specs for hosting"](https://github.com/searxng/searxng/discussions/3884)
- This repository's own `image-builder/sovereign/pihole-image.env`,
  `image-builder/sovereign/llama-image.env`, and
  `image-builder/sovereign/appliance/nginx/sovereign.conf`, read directly.

## Findings

Findings are separated into what SearXNG's own documentation/source states
(observed) versus what follows from applying it to this project (inference).

### Observed: container image and deployment shape

- Official images are published to both `docker.io/searxng/searxng` and
  `ghcr.io/searxng/searxng`; the docs recommend the GHCR mirror over
  DockerHub to avoid DockerHub's unauthenticated pull rate limits.
  `llama-image.env` already pins from `ghcr.io` for the same class of
  reason (`ghcr.io/ggml-org/llama.cpp`), so `ghcr.io/searxng/searxng` is the
  consistent choice for a `searxng-image.env`.
- The default container port is `8080` (`SEARXNG_PORT` in
  `container/.env.example`). **This collides directly with this project's
  own port allocation**: `nginx/sovereign.conf` already proxies `/dns/` to
  Pi-hole's container on `127.0.0.1:8080`. SearXNG's container port must be
  remapped. Following this project's existing loopback-port convention
  (`8080` Pi-hole, `8081` llama-server, `8090` console-health, `8091`
  console-auth, `8092` sovereign-conversation), the next free port is
  `8093`.
- Persistent state lives in two volumes: `/etc/searxng` (`settings.yml`,
  `limiter.toml`, `favicons.toml`) and `/var/cache/searxng`. Neither needs
  to be exposed outside the container's own filesystem — no equivalent of
  Pi-hole's `/data/sovereign/pihole` persistent-DATA mount is obviously
  required, since a metasearch proxy holds no household-specific state by
  design (RFC-0004's "no silent private-context mixing" requirement is
  about what's ever *sent* to it, not what it retains).
- `SEARXNG_SECRET` is a required environment variable at container start —
  a random per-instance secret, the same operational shape as
  `sovereign-pihole-password`/`sovereign-console-password`: generated once
  at first boot, not baked into the image.

### Observed: defaults that are wrong for a private, loopback-only instance

SearXNG's shipped defaults are written for public instances that must
defend themselves from being mistaken for bot traffic by upstream engines,
and from being scraped by other people's automation. A single-user instance
that never leaves `127.0.0.1` doesn't have either problem, and some of
those defaults would actively work against this project's own commitments:

- **JSON output is disabled by default.** `search.formats` defaults to
  `[html]` only, per the default `settings.yml`'s own comment: `# remove
  format to deny access, use lower case.` Requesting `format=json` against
  an instance that hasn't added it returns `403 Forbidden` — the SearXNG
  docs explicitly warn "many public instances have these formats
  disabled." RFC-0004's `web.search` capability needs structured results,
  not an HTML page to scrape, so `settings.yml` must explicitly set
  `formats: [html, json]` (keeping `html` costs nothing and preserves a
  human-debuggable fallback).
- **Autocomplete defaults to a live external backend** (`autocomplete:
  "duckduckgo"`). Unlike the main search, autocomplete fires on partial
  keystrokes, not an explicit submitted query. Left at its default, that
  is a second, undisclosed channel sending partial query text to an
  external engine — in direct tension with ADR-0004's "must not silently
  incorporate private household context" and RFC-0004's requirement to
  show the exact query before or while it's sent. This project's own
  `web.search` capability's request/response contract governs what's
  disclosed to the user, not SearXNG's UI autocomplete, so the fix is
  simply to turn it off at the SearXNG layer: `autocomplete: ""`.
- **The rate limiter defaults to off** (`server.limiter: false`), which is
  the *right* default here, just for a different reason than upstream's:
  the limiter exists to stop an instance's own users from getting the
  instance's IP blocked by upstream engines, and additionally requires
  standing up a Valkey/Redis database to function at all. RFC-0003/0004's
  per-capability invocation budgets already bound how often the model can
  call `web.search` per turn at the Sovereign executor layer, which is a
  tighter and more relevant control for this deployment than SearXNG's own
  bot-defense limiter. No Valkey dependency is needed. This should be
  recorded as a deliberate choice in whatever RFC follows this document,
  not left implicit.
- **Image proxying defaults to off** (`server.image_proxy: false`). Left
  off, image results in a search response link directly to the original
  external host, which the browser would fetch outside Sovereign's control
  the moment a user's device renders them. Turning it on would route image
  fetches through the local SearXNG instance instead, which is more
  private but adds real request/bandwidth load to every image-bearing
  search. Documentation alone can't settle this trade-off for the target
  hardware — recorded here as an open question for the eventual RFC, not
  resolved by this document.

### Observed: JSON search API shape

- Both `GET /search?q=<query>&format=json` and `POST /search` with
  `q`/`format=json` form-encoded work. Optional parameters observed in the
  docs: `categories`, `language`, `pageno`, `time_range` (`day`/`month`/
  `year`), `safesearch` (`0`/`1`/`2`), `theme`.
  This project's `web.fetch`/`web.search` capability schemas (still to be
  defined) can map fairly directly onto `q`, `categories`, and
  `time_range`.
- The documentation page fetched for this assessment did not itself
  enumerate the full JSON response schema (top-level `results`/`answers`/
  `infoboxes`/`suggestions` fields) in enough verifiable detail to record
  here as observed fact rather than paraphrase. That schema needs
  confirming against a real response body, not the prose docs — see
  Limitations.

### Observed: resource footprint

- Community-reported baseline: roughly 512MB–600MB RAM at idle/light load,
  1 vCPU, ~300MB container disk footprint, no built-in result caching by
  default (favicon caching, a newer optional feature, adds modest disk
  use if enabled). One collaborator reported running multiple instances on
  512MB VMs "with zero problems with speed."
- One maintainer-answered report of "8+ GB" Docker-reported memory usage
  turned out to be a measurement artifact, not real consumption: Docker's
  default memory display includes the OS page cache, and the maintainer's
  own guidance was to read the resident-set (RES) value instead. Worth
  recording explicitly so a future real measurement on this project's own
  Pi 5 isn't misread the same way against `docker stats` output.
- None of these figures were measured against this project's actual
  concurrent load (Pi-hole + llama-server + Console services all running
  at once on the same 16GB device, against ADR-0012's 40%-of-RAM ceiling).
  They establish a plausible order of magnitude, not a qualified number.

### Observed: license

- SearXNG is AGPL-3.0-licensed. This project already runs Pi-hole
  (itself GPL-licensed) as an unmodified third-party container consumed
  over its own API/network surface, not linked into Sovereign OS's own
  code — the same relationship a SearXNG deployment would have. AGPL's
  network-use clause obligates *SearXNG's own* source to stay available to
  users interacting with it over a network, which it already is
  (upstream); it does not obligate Sovereign OS's own code, unless
  Sovereign OS forks and modifies SearXNG's source directly, which nothing
  in this document proposes.

## Alternatives

Considered and rejected without further evaluation, since ADR-0004 already
closed this question:

- **A hosted third-party search API** — explicitly rejected in ADR-0004's
  own "Rejected Alternatives" ("Use a hosted search API by default"): would
  introduce a mandatory external processor for every search query,
  conflicting with the local-first default.
- **A different self-hosted metasearch engine** (e.g., Whoogle) — out of
  scope for this document; ADR-0004 already selected SearXNG specifically,
  and revisiting the provider choice itself is not this document's
  question.

## Limitations

This document is desk research against SearXNG's published documentation
and source, not a hardware qualification report, and should not be read as
one:

- No real ARM64 image digest was pinned. `searxng-image.env` would need a
  real `skopeo inspect --raw` (or equivalent) run against
  `ghcr.io/searxng/searxng` for `linux/arm64`, the same way
  `pihole-image.env` and `llama-image.env` were populated, before any
  image-builder work starts.
- No real memory/CPU/thermal measurement was taken on this project's own
  Raspberry Pi 5 device, and none of the cited community figures reflect
  running concurrently with this device's real Pi-hole and llama-server
  load under ADR-0012's budgets.
- The JSON response schema was not confirmed against a live query — only
  the request shape and a documentation warning about the 403-when-disabled
  behavior were directly verifiable from the fetched docs page.
- Real upstream-engine behavior when queries originate from a residential
  IP (occasional CAPTCHA/soft-blocking some public search backends apply
  to automated-looking traffic) was not tested and isn't addressed by any
  source cited here.
- No systemd unit design (artifact/import/server staging, health-check
  shape, `ReadWritePaths=`/capability grants) was attempted here — that is
  implementation work for the eventual RFC and its own qualification pass,
  not this document's job.

## Recommendation

Proceed to drafting an RFC for the `web.search`/`web.fetch` capability
mapping (mirroring RFC-0006's shape for Pi-hole: registered capability
schemas, the deterministic executor's validation/authorization/audit
requirements, and citation/disclosure UI requirements from RFC-0004 §6),
citing this document for the deployment specifics:

1. Embed SearXNG the same way Pi-hole and llama.cpp are embedded: pin
   `ghcr.io/searxng/searxng` by digest in a new `searxng-image.env`, with
   the same artifact/import/server three-stage systemd shape.
2. Bind the container to local port `8093` (loopback-only; no nginx
   location should expose it directly — only the `web.search`/`web.fetch`
   capability handlers should ever call it, the same way `pihole.status`
   calls Pi-hole's own API rather than exposing it to the model directly).
3. Ship a `settings.yml` overriding exactly three defaults away from
   upstream's public-instance tuning: `formats: [html, json]` (JSON
   required for the capability to parse results), `autocomplete: ""`
   (disabled — a public commitment, not an optimization, per ADR-0004),
   and leave `limiter: false` (already the default, and correct here for
   the reason stated above, not merely inherited).
4. Leave `image_proxy` as an explicit open question for the RFC itself,
   not pre-decided by this document.
5. Generate `SEARXNG_SECRET` at first boot, following the
   `sovereign-pihole-password`/`sovereign-console-password` pattern
   already established for other per-device secrets.

## Unresolved Questions

- ~~Real pinned ARM64 digest (needs registry access this session doesn't
  have).~~ Resolved — see Addendum.
- Real resource footprint on this project's actual Raspberry Pi 5 under
  real concurrent load (Pi-hole + llama-server + Console all running),
  against ADR-0012's 40%-of-RAM ceiling. **Still open** — the Addendum's
  memory reading is illustrative only, from a non-Pi host with no
  concurrent load.
- ~~The real JSON response schema, confirmed against a live query.~~
  Resolved — see Addendum.
- Whether `image_proxy` should be enabled (privacy) or left off
  (resource/latency cost) — resolved by
  [RFC-0017](../rfcs/0017-web-search-and-fetch-capability-mapping.md)'s
  Proposal (`false`, off).
- Real upstream-engine blocking/CAPTCHA behavior from a residential IP,
  and what failure mode the `web.search` capability should surface to the
  model/user when an upstream engine blocks the request entirely. **Still
  open** — the Addendum's live query succeeded against real upstream
  engines from this session's own network egress, which says nothing
  about a real device's residential IP reputation.

## Addendum: Live Verification (2026-08-21, non-Pi host)

A later session in the same day had real Docker and outbound network
access (this document's original research above did not), and used it to
close several of the Unresolved Questions above against the real,
pinned image — not just its published documentation. This is genuine
image/registry verification, but **not** Raspberry Pi hardware
qualification: it ran on this session's own host, not the target device,
under no concurrent Pi-hole/llama-server load, and is recorded as such,
not overclaimed as a qualification pass.

- **Real pinned digest captured.** `docker manifest inspect
  ghcr.io/searxng/searxng:latest` returned a real multi-arch index; its
  `linux/arm64` entry is
  `sha256:f90ba0d666af9856e5ed1e4f486fdbf9a329dbd6f5bc55a09ba1a280564970a7`
  (image created 2026-08-20 per its own annotations — one day before this
  verification). Confirmed this is the arm64-specific single-platform
  manifest digest, not the top-level multi-arch index digest, matching
  how `LLAMA_IMAGE_DIGEST` is pinned (the same distinction
  `llama-server-deployment-qualification-report.md` confirmed for
  llama.cpp: a loaded image's own `image_id` equals the pinned digest,
  which only holds for a single-platform manifest digest). Now pinned in
  `image-builder/sovereign/searxng-image.env`.
- **`SEARXNG_SECRET` confirmed as a real, working override, not
  assumption.** Reading the pinned image's own
  `searx/settings_defaults.py` directly: `secret_key` is a
  `SettingsValue(str, environ_name='SEARXNG_SECRET')` — the Python
  settings loader reads this environment variable unconditionally at
  load time, regardless of what's literally written in `settings.yml`.
  There is **no `_FILE` suffix convention** (confirmed by reading the
  same source) — unlike Pi-hole's `WEBPASSWORD_FILE`, the secret must be
  passed as a real environment variable, not a Docker-secrets file
  mount. This shaped `compose.yaml.in`'s `SEARXNG_SECRET: ${SEARXNG_SECRET}`
  interpolation and `start-searxng`'s `SEARXNG_SECRET=$(cat
  "$secret_file") docker compose ...` pattern.
- **No Docker `HEALTHCHECK`** in the pinned image (`docker inspect`'s
  `Config.Healthcheck` is `null`) — confirms `start-searxng` needs
  llama-server's manual curl-polling pattern, not Pi-hole's
  `docker inspect --format '{{.State.Health.Status}}'` pattern. The
  readiness probe polls the homepage (`GET /`), not a search query, so
  a boot-time readiness check never itself sends a real query to an
  external engine.
- **Real JSON response schema confirmed** via a live `GET
  /search?q=raspberry+pi&format=json` against the pinned image (real
  upstream engines, real results returned): top-level keys are `query`,
  `results`, `answers`, `infoboxes`, `suggestions`, `corrections`,
  `unresponsive_engines`. Each `results[]` entry carries far more than
  RFC-0017's minimal `title`/`url`/`snippet` capability result schema
  needs (`engine`, `engines`, `score`, `positions`, `img_src`,
  `thumbnail`, `category`, and more) — confirming the capability
  implementation's job is to select down to `title`/`url`/`content`
  (mapped to `snippet`) and discard the rest, not that those three
  fields don't exist. `content` is the field that maps to this project's
  `snippet`.
- **Illustrative-only memory reading:** `docker stats` showed the running
  container at 156MiB RSS shortly after startup, on this session's
  non-Pi host, alongside no other Sovereign services. Consistent with
  the ~512MB–600MB community range's low end, but explicitly **not** a
  substitute for real measurement on the actual Raspberry Pi 5 under real
  concurrent load.
- **Confirmed real internal port is 8080**, matching this document's
  original recommendation to bind the host side to `8093` — the
  container's own `Config.ExposedPorts` is `8080/tcp` and its default
  `GRANIAN_PORT=8080` env var, independent of the unrelated
  `server.port: 8888` key that appears in `settings.yml` (a leftover
  config surface for an older non-`granian` deployment method this
  image's entrypoint doesn't use).

## Decision Impact

This document does not itself authorize implementation — per this
project's workflow, an RFC proposes what to build and a project-owner
acceptance decides it. It unblocked drafting
[RFC-0017](../rfcs/0017-web-search-and-fetch-capability-mapping.md), the
same relationship `pihole-api-assessment.md` had to RFC-0006, and its
Addendum's live findings fed directly into the real image-builder
implementation under `image-builder/sovereign/searxng-image.env` and
`image-builder/sovereign/appliance/searxng/` — deployed and unit-tested
(`tests/test_searxng_deployment.py`), not yet hardware-qualified on a
real Raspberry Pi 5.
