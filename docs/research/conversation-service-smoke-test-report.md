# Conversation Service Smoke Test Report

**Date:** 2026-08-09

**Hardware:** Raspberry Pi 5 (`sovereign.local`), the project's qualification
device, running its real Pi-hole instance and a locally deployed
llama.cpp server serving Qwen2.5-3B-Instruct (Q4_K_M) — the runner and
model [ADR-0013](../adrs/0013-initial-inference-runner-and-model-selection.md)
selected.

**Status:** First real-hardware execution of the Conversation Service
(`sovereign_conversation.py` + `bin/sovereign-conversation`) as an actual
HTTP service, driving RFC-0003's six-stage executor and both real
capabilities (`system.health`, `pihole.status`, `pihole.summary`) through
a real caller for the first time — closing the gap both prior capability
smoke test reports flagged ("no Conversation Service yet to invoke
these"). No test doubles anywhere in the path: real inference, real
`urllib` calls, real Pi-hole API, real console-health service, real audit
log.

## Method

`bin/sovereign-conversation` and the five `lib/*.py` files it depends on
were copied unmodified to `/data/sovereign-smoke/{bin,lib}/` on the
device (plain `scp`, no privilege needed). Qwen2.5-3B-Instruct-Q4_K_M
(~2GB) was downloaded fresh (no prior benchmark artifacts survived —
those runs were explicitly cleaned up, see the benchmark reports'
"Reproduction" sections) and llama-server started via the same Docker
invocation the benchmark reports document.

Reading the Pi-hole credential requires root (this device is still on
release `0.1.0-proof.3`, predating this session's `sovereign-pihole-secrets`
group — the DynamicUser/group access path this session added is verified
by [the unit tests](../../tests/test_conversation_service.py) and code
review, not by this manual run). The project owner ran the service
themselves via `sudo env ... python3 /data/sovereign-smoke/bin/sovereign-conversation`,
matching the same "root reads the secret, the assistant never does"
split the pihole capability smoke test established. The assistant made
all subsequent HTTP calls against the service's loopback port over a
separate, unprivileged SSH session — a live demonstration that this
service's stated network boundary (loopback-only, RFC-0002) actually
holds: reaching it needs no more privilege than reaching any other
loopback port on the box.

Four real conversational turns were sent to `POST /api/v1/conversation/message`:
a plain-chat turn with no capability involved, and three capability
proposal/execute/narrate round trips.

## Results

**Plain chat (no capability):**

```json
{"text":"I am an AI assistant created by Alibaba Cloud to help with various tasks and provide information.","capability_events":[],"citations":[],"rounds_used":1}
```

Reached the model in one round, no proposal, `capability_events` empty
as expected. (The self-identification as "created by Alibaba Cloud" is
Qwen's own base-model training talking, not a bug — no system prompt
establishing a Sovereign persona exists anywhere in this implementation;
that's disclosed, unbuilt scope, not a regression.)

**`system.health` round trip:**

The model correctly proposed `system.health` with no arguments,
received the real registry's real result (74.9°C, 16.1% memory, all
five checks healthy), and narrated it accurately — including catching
that no check was degraded. `rounds_used: 2`, one `capability_events`
entry (`{"name": "system.health", "outcome": "executed"}`).

**`pihole.summary` round trip** (arguments this time — the model chose
`{"period": "today"}` on its own):

```
"Pi-hole is currently blocking ads. Based on the summary for today, it
has blocked approximately 27.88% of the queries. In the last 24 hours,
Pi-hole blocked about 453 queries out of 1,625 total queries..."
```

The narrated percentage matches the raw result's `blocked_percentage`
(27.876...%) to Pi-hole's own rounding, and the model correctly
extracted a structured argument the schema defines rather than
hallucinating one.

**`pihole.status` round trip:** proposed with no arguments (correct — the
schema takes none), executed, narrated as a terse "Yes" to a yes/no
question — a reasonable model choice, not a pipeline behavior.

**Audit log**, made readable for inspection after the run:

```
{"capability":"system.health","duration_seconds":0.020777,"network":"local","outcome":"executed","result_bytes":827,"side_effect":"read_only","stage_reached":"audited","timestamp":"2026-08-09T19:10:23Z","version":1}
{"capability":"pihole.summary","duration_seconds":0.187697,"network":"local","outcome":"executed","result_bytes":179,"side_effect":"read_only","stage_reached":"audited","timestamp":"2026-08-09T19:11:33Z","version":1}
{"capability":"pihole.status","duration_seconds":0.001487,"network":"local","outcome":"executed","result_bytes":78,"side_effect":"read_only","stage_reached":"audited","timestamp":"2026-08-09T19:12:08Z","version":1}
```

Exactly three entries for exactly the three executed invocations, each
reaching `stage_reached: "audited"` with no query content, domain names,
or client identities recorded — matching what the pihole capability
smoke test already established, now proven from a real Conversation
Service caller rather than a hand-written driver script.

**Error handling:** a malformed (non-JSON) body and a body missing
`message` both correctly returned `400 INVALID_REQUEST` rather than a
500 or a hang.

**Cleanup verified, not just assumed:** after the project owner stopped
the service and removed the llama-server container, both
`127.0.0.1:8092` and `127.0.0.1:8081` were confirmed unreachable
(`curl` timeout, not a captured response) before the scratch directory
was deleted — no orphaned listener left behind.

## A real testability/config gap found and fixed before this run

While preparing the smoke test it became clear `bin/sovereign-conversation`
had no way to redirect its audit log: it called `process_turn(...)`
without passing `audit_log_path`, silently falling back to whatever
`sovereign_capabilities.AUDIT_LOG_PATH` happened to already be bound to
at that process's first import of the module (production-correct, but
untestable in isolation the way every other capability-invoking test in
this project explicitly overrides that path). Fixed by adding
`SOVEREIGN_CONVERSATION_AUDIT_LOG_PATH` (read fresh at the script's own
top level, mirroring the existing `SOVEREIGN_INFERENCE_BASE_URL`
pattern) and passing it explicitly into `process_turn()`. Also fixed:
the service's `sys.path.insert` pointed at a hardcoded production-only
path (`/opt/sovereign/current/appliance/lib`) instead of a path computed
relative to the script's own location, which would have made this exact
smoke test (files living at `/data/sovereign-smoke/`, not
`/opt/sovereign/...`) impossible without a throwaway hack. Both fixes
shipped in the same commit as the Conversation Service itself, caught
by writing the HTTP-layer tests before this hardware run, not by this
run.

## Limitations

Ran as `root` via `sudo`, not under the real `DynamicUser` +
`sovereign-pihole-secrets` group the systemd unit specifies — this
device predates that group's deployment. The unit itself
(hardening flags, group membership, `After=` ordering) is validated by
[`tests/test_conversation_service.py`](../../tests/test_conversation_service.py)'s
provisioning tests and code review, not exercised live here. No
confirmation-required capability exists yet to exercise that refusal
path live (already covered by 26 unit tests). No streaming, no
multi-turn history continuity across separate HTTP calls, and no
authentication were tested — all are disclosed, unbuilt scope for this
pass, not gaps found here. Thermal load from a genuinely concurrent
DNS + inference + capability-execution workload (all three at once, not
sequentially as in this run) remains unmeasured beyond
[the existing DNS-latency-during-generation report](dns-latency-during-generation-qualification-report.md).

## Conclusion

The Conversation Service works end to end against real inference, real
capabilities, and real Pi-hole/system state on the qualification
device: correct capability selection (including structured argument
extraction the model wasn't spoon-fed), correct untrusted-forever
handling of capability results (they flow back through the loop as
plain `tool`-role content and get narrated, never treated as
instructions), a compliant audit trail, and correct error handling on
malformed input. No behavioral discrepancy from the unit tests' mocked
expectations was found. What remains before this is genuinely
production-ready is auth integration and running it under its actual
`DynamicUser` identity on a device that has the `sovereign-pihole-secrets`
group deployed — both already tracked in ROADMAP.md.
