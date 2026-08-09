# llama.cpp + Qwen2.5-7B-Instruct: Second Benchmark Report (Comparison)

**Date:** 2026-08-09

**Hardware:** Same qualification device as the
[Qwen2.5-3B report](llamacpp-qwen2.5-3b-benchmark-report.md): Raspberry
Pi 5 Model B Rev 1.1, official Active Cooler, Debian 13 (trixie),
`aarch64`, default power mode, same day, back-to-back with the 3B run.

**Runtime:** Same llama.cpp Docker image and digest as the 3B run
(`ghcr.io/ggml-org/llama.cpp:server`,
`sha256:5a7d34c5a378b6f3b542e71690bd82db7b5bf31fd77d9d1582cc7f2c9043ad8c`),
same `-c 4096 -t 4`, same loopback-only binding. Only the model changed.

**Model:** `Qwen/Qwen2.5-7B-Instruct-GGUF`, Q4_K_M quantization, split
across two GGUF shards (unlike the 3B model, which fit in one file):

| File | SHA-256 | Bytes |
| --- | --- | --- |
| `qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf` | `dfce12e3862a5283ccfb88221b48480e58745165de856439950d0f22590580db` | 3,993,201,344 |
| `qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf` | `539cf93f78e887edea1c04e2d7d8cdaca9d01dae9c9025bcb8accbe29df3d72a` | 689,872,288 |

Both digests captured before use this time — the 3B report's noted gap
(digest not captured before cleanup) is fixed here. Sourced from
`https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/`,
magic bytes verified as real GGUF on both shards before use. llama.cpp
loads the shard set automatically given the first file's path.

**Status:** Direct, same-day, same-device, same-corpus comparison
against the [3B report](llamacpp-qwen2.5-3b-benchmark-report.md) — the
project owner's explicit next step after that first pass. No process
bugs this time; the streaming/tool-call fix from the 3B pass already
covered this run.

## Results, Side by Side

| Item | 3B tokens/s | 7B tokens/s | 3B correct | 7B correct |
| --- | --- | --- | --- | --- |
| Plain chat | 4.91 | 1.47 | — | — |
| `system.health` | 4.72 | 0.41 | ✅ | ✅ |
| `pihole.status` | 4.92 | 1.98 | ✅ | ✅ |
| `pihole.summary` | 4.79 | 1.95 | ✅ (period arg correct) | ✅ (period arg correct) |
| Goldfish (no tool expected) | 5.29 | 2.27 | ✅ (none proposed) | ✅ (none proposed) |

**Accuracy: identical, 5/5 for both models** on this corpus, including
the same correct `period: "last_24h"` argument extraction. This starter
corpus is small and only measures structured-proposal correctness, not
answer quality — a ceiling effect where both models already score
perfectly means this pass cannot show whether 7B writes measurably
better prose or handles harder/ambiguous cases more reliably. That
distinction needs the larger, still-undecided evaluation corpus
`docs/research/local-ai-options.md`'s Follow-up Decisions names, not
this starter one.

**Speed: 7B is roughly 2–10x slower** across every item, most severely
on `system.health` (4.72 → 0.41 tokens/s, an 11x slowdown) — total
corpus duration went from ~26 seconds (3B) to ~97 seconds (7B) for
functionally identical output.

**Memory:** 27.9–28.5% used throughout the 3B run vs. **57.9–58.5% for
7B** — roughly double, consistent with the larger weight count and KV
cache, and a real capacity concern if this device needs headroom for
Pi-hole, Console, and future capability-invocation memory simultaneously
with inference.

**Temperature: 57.3°C → 84.8°C**, slightly higher than 3B's 83.2°C peak,
reached over a longer (~97s vs ~25s) run. **84.8°C is within ~0.2°C of
the Pi 5's documented throttle point (~85°C)** — this run was on the
edge of thermal throttling actually kicking in, not just approaching it
in the abstract. Both runs plateau in the low-to-mid 80s°C rather than
climbing without bound in the time observed, suggesting something closer
to a steady-state than a runaway — but neither run sampled temperature
*during* generation, only before/after, so the actual peak and how long
it's sustained remain uncharacterized. A real gap for any future pass
attempting sustained (not burst) load.

**DNS latency:** 13.94ms → 19.76ms (7B) vs. 14.32ms → 15.37ms (3B) — a
larger delta for the heavier, longer-running workload, consistent with
more sustained CPU contention against Pi-hole's own resolution work,
though still only a before/after sample, not a during-generation one
(the same limitation the 3B report already named).

## Interpretation

For this milestone's actual use case — quick answers to household
questions about system/Pi-hole status, on a device that must keep
serving DNS reliably — 7B's cost (2-10x slower, ~2x memory, marginally
hotter, right at the thermal edge) bought **no measured accuracy
improvement** on this corpus. That is a real, meaningful data point
toward 3B being the more practical choice for this appliance, but not a
final answer: the corpus's ceiling effect means a real quality
difference could exist and simply isn't visible here. Any selection
decision should wait for the larger corpus and, per the project owner's
own stated plan, a comparison against Ollama as well — this report
still only speaks to llama.cpp.

## Reproduction

Same method as the [3B report](llamacpp-qwen2.5-3b-benchmark-report.md#reproduction),
substituting the two shard files above (download both, keep their exact
filenames in the same directory, point `-m` at the `00001-of-00002` file).

## Conclusion

Both models are equally, perfectly accurate on this small corpus; 7B is
substantially slower, roughly twice the memory footprint, and pushes the
device to within a fraction of a degree of its throttle point. Combined
with the 3B report, this is now two real data points — not a completed
comparison (Ollama and a larger evaluation corpus remain), but enough to
say 7B's cost is real and its benefit, on the evidence gathered so far,
isn't.
