# ADR-0013: Initial Inference Runner and Model Selection

**Status:** Accepted

**Date:** 2026-08-09

**Decision owner:** Project creator

**Related RFCs/research:**
[RFC-0002](../rfcs/0002-local-conversation-and-inference-runtime.md) (Accepted),
[ADR-0004](0004-provider-neutral-assistant-and-web-search.md) (Accepted;
names this ADR as required follow-up: "Record the selected runner and
initial model in a later ADR"),
[ADR-0012](0012-local-inference-resource-and-dns-latency-budgets.md) (Accepted),
[docs/research/local-ai-options.md](../research/local-ai-options.md),
[llama.cpp 3B](../research/llamacpp-qwen2.5-3b-benchmark-report.md),
[llama.cpp 7B](../research/llamacpp-qwen2.5-7b-benchmark-report.md),
[Ollama 3B](../research/ollama-qwen2.5-3b-benchmark-report.md),
[v1 corpus](../research/v1-corpus-benchmark-report.md), and
[DNS-latency-during-generation](../research/dns-latency-during-generation-qualification-report.md)
qualification reports.

**Supersedes:** None

## Context

Six real hardware qualification passes now exist against the
qualification Raspberry Pi 5, spanning two runners (llama.cpp, Ollama),
two model sizes (Qwen2.5-3B, Qwen2.5-7B), two corpora (a 5-item starter
corpus that hit a ceiling effect, and a 28-item corpus built
specifically to break it), and a real during-generation DNS-latency
measurement. ADR-0012 turned that evidence into an accepted numeric
budget policy. This ADR makes the selection decision ADR-0004 named as
required follow-up, using that evidence and that policy together.

### The Evidence, Summarized

| | llama.cpp + Qwen2.5-3B | llama.cpp + Qwen2.5-7B | Ollama + Qwen2.5-3B |
| --- | --- | --- | --- |
| Starter corpus (5 items) | 5/5 | 5/5 | 5/5 |
| v1 corpus (28 items, 20 scored) | **17/20 (85%)** | Not run (see below) | 15/20 (75%) |
| Speed (starter corpus) | 4.7–5.3 tok/s | 0.4–2.3 tok/s (2–10x slower) | 4.5–5.2 tok/s once warm |
| First-request latency | Fast (0.18s TTFT, eager model load) | Fast (eager load) | **Slow (6.96s TTFT, lazy model load)**, reproduced twice |
| Memory | ~28% (within ADR-0012's 40% budget) | ~58% (**exceeds** the 40% budget) | ~28% once loaded |
| Peak temperature | 83.2–84.2°C | 84.8°C | 82.6–83.7°C |
| DNS latency during generation | **Measured**: 50ms budget held (max 41.25ms, 136 samples) | Not measured | Not measured |

The llama.cpp-7B v1-corpus run was deliberately never attempted — after
the llama.cpp-3B v1-corpus pass confirmed real thermal throttling for
the first time in this series, the project owner chose to skip the
heaviest remaining configuration rather than push it further. That gap
turns out not to matter for this decision: **7B already fails
ADR-0012's memory budget outright** (~58% observed vs. a 40% ceiling),
independent of any further accuracy or thermal data. No amount of
additional 7B benchmarking changes that a model already known not to
fit the accepted resource budget doesn't need more evidence to be
excluded.

## Decision

**Runner: llama.cpp**, via its official Docker server image
(`ghcr.io/ggml-org/llama.cpp:server`), speaking the OpenAI-compatible
chat-completions API `sovereign_inference.py`'s `LlamaCppProvider`
already implements against RFC-0002's Inference Provider Adapter
contract.

**Model: Qwen2.5-3B-Instruct, Q4_K_M quantization**, the specific
artifact benchmarked throughout this series:
`https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf`,
SHA-256 `626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d`,
2,104,932,768 bytes.

### Why llama.cpp Over Ollama

Both runners tied on the trivial starter corpus (a ceiling effect the
v1 corpus was built to break) and were comparably fast once an Ollama
model was warm. But two real, measured differences favor llama.cpp:

1. **Accuracy on the harder corpus.** 85% vs. 75% on the identical
   28-item v1 corpus, with Ollama showing a specific, reproducible
   pattern of defaulting to `pihole.status` regardless of what was
   actually asked. This is not attributable to a different underlying
   model — both ran Qwen2.5-3B at the same Q4_K_M quantization *level*
   — though the exact GGUF build differs (Ollama's own library vs. the
   Hugging Face community file), a disclosed and unresolved variable
   the v1-corpus report already named.
2. **No cold-start penalty.** llama-server loads its one configured
   model eagerly, before accepting any request. Ollama loads lazily on
   first use — reproduced identically across two independent runs, a
   6.96-second time-to-first-token on a question that took llama.cpp
   0.18 seconds. For a household assistant, the first question after
   any period of inactivity is not a rare edge case; it is likely the
   *typical* case. A multi-second penalty on exactly that interaction
   is a real product cost llama.cpp's eager loading avoids entirely.

Ollama's own stated advantages — simpler model acquisition, a
convenient development workflow (`docs/research/local-ai-options.md`'s
original comparison table) — remain real, but are not reasons to accept
worse measured accuracy and a real latency penalty in the *production*
path. Ollama remains available as an optional development/evaluation
tool, per ADR-0004's original framing; it is not selected as the
production runner.

### Why Qwen2.5-3B Over Qwen2.5-7B

7B matched 3B's accuracy on every corpus it was tried against (both hit
the same 5/5 ceiling on the starter corpus) — no measured benefit — at
a real, substantial cost: 2–10x slower, roughly double the memory
footprint, and the hottest peak temperature observed in this entire
series (84.8°C, within 0.2°C of the confirmed throttle point). Per
ADR-0012's accepted 40%-of-RAM budget, 7B's ~58% memory footprint
disqualifies it independent of every other finding. There is no
evidence-based reason to spend the resource headroom.

### Scope of This Decision

This selects the runner and *initial* model — not a permanent,
unchangeable choice. RFC-0002's provider-neutral contract exists
specifically so this can change without redesigning the Conversation
Service around it. This ADR also does not claim an exhaustive model
search: only Qwen2.5 at two sizes was evaluated. Other model families
(Llama, Phi, Gemma, and others) were never benchmarked. Qwen2.5-3B is
selected because it is the first candidate that was measured, met every
accepted budget, and showed no reason to look further — not because it
was proven best among all possibilities.

## Consequences

### Positive

- Unblocks the Conversation Service (RFC-0002's Delivery Sequence item
  4, "implement conversation streaming without capabilities") — the
  runner/model selection was the last thing standing between the
  already-built capability infrastructure (`sovereign_capabilities.py`,
  `sovereign_pihole.py`, `sovereign_system.py`, all hardware-qualified)
  and an actual product experience using it.
- The deferred llama.cpp-7B v1-corpus run, named as open in every prior
  report in this series, is now moot: 7B is excluded on the memory
  budget alone, and no further benchmarking of it is needed to reach
  that conclusion.
- Gives Sovereign Model Management (RFC-0002's separate, still-
  unspecified component) a concrete first artifact — digest, source,
  and quantization already recorded here — to build its manifest format
  around, rather than an abstract requirement.

### Negative

- Ollama's real advantages (simpler model acquisition/management) are
  given up in the production path. If Sovereign Model Management later
  finds llama.cpp's model lifecycle genuinely harder to build than
  expected, this tradeoff may need revisiting.
- This decision rests on Qwen2.5 exclusively. If Qwen2.5-3B's real-world
  conversation quality (as opposed to the narrow capability-selection
  accuracy this benchmark measures) proves inadequate once the
  Conversation Service is real, a broader model search is a real,
  not-yet-done piece of work this ADR doesn't preempt.
- The specific GGUF build tested is a third-party community quantization
  (`Qwen/Qwen2.5-3B-Instruct-GGUF` on Hugging Face), not an official
  Qwen release artifact — a supply-chain provenance question Sovereign
  Model Management will need to address (digest verification exists in
  this ADR's evidence trail; a broader trust policy for model sources
  does not exist yet).

### Risks

- ADR-0012's two revisit conditions are only partially validated for
  this exact configuration: the DNS-latency-during-generation budget
  is confirmed for llama.cpp-3B on the starter corpus specifically, but
  the realistic intermittent-use thermal pass has not been done at all,
  for any configuration. If that pass later shows even intermittent use
  throttles this device, it affects the selected configuration exactly
  as much as any other — this ADR does not reduce that risk, only
  documents that it remains open (see Required Follow-up).
- Committing to Qwen2.5-3B before a broader model search risks having
  to redo evaluation work if a different model family later proves
  meaningfully better. RFC-0002's provider-neutral contract bounds the
  cost of that (no architectural rework), but real benchmark and
  qualification effort would still need repeating.

## Alternatives Considered

- **Select Ollama for its operational convenience, accepting the
  cold-start penalty.** Rejected: a multi-second delay on what is
  likely the *typical* first interaction is a real, user-visible product
  cost, not a rare edge case worth trading away measured accuracy for.
- **Select Qwen2.5-7B for potential quality headroom.** Rejected: no
  benchmark run showed any accuracy benefit over 3B, and 7B fails
  ADR-0012's memory budget outright — there is no real evidence to
  weigh against that failure.
- **Wait for the realistic-use thermal pass and a broader model search
  before deciding anything.** Rejected: six real qualification passes
  already provide clear, converging, non-contradictory evidence for
  this specific choice. Per this project's own precedent (ADR-0012
  itself accepted provisional budgets rather than waiting for perfect
  data), deciding now with disclosed, non-blocking gaps unblocks real
  product work; waiting only delays it for marginal additional
  confidence in a conclusion the existing data already supports clearly.

## Required Follow-up

- The realistic, intermittent-use thermal pass ADR-0012 already named
  as an open revisit condition — now specifically important for the
  selected configuration (llama.cpp + Qwen2.5-3B), not a generic
  benchmark exercise.
- Sovereign Model Management's model-manifest format and provenance/
  trust policy (RFC-0002's still-open piece), using this ADR's recorded
  digest as its first real artifact.
- Real conversation-quality evaluation once the Conversation Service
  exists — this ADR's evidence is entirely about capability-selection
  accuracy and resource budgets, not the opened-ended chat quality a
  household would actually experience.

## Validation and Revisit Conditions

This ADR should be revisited if:

- Real Conversation Service usage reveals conversation quality problems
  this benchmark's narrow capability-selection metric couldn't have
  caught.
- The realistic intermittent-use thermal pass shows the selected
  configuration doesn't hold within ADR-0012's budget under real
  household usage patterns, not just stress-test bursts.
- A future model or runner candidate is evaluated against the same
  method and budgets and shows a clear, measured improvement — this
  selection is a starting point RFC-0002's provider-neutral contract
  makes replaceable, not a closed question.
