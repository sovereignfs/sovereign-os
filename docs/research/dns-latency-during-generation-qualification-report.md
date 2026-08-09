# DNS Latency During Generation: First Real Measurement

**Date:** 2026-08-09

**Hardware:** Same qualification device as every report in this series.

**Configuration:** llama.cpp (Docker,
`sha256:5a7d34c5a378b6f3b542e71690bd82db7b5bf31fd77d9d1582cc7f2c9043ad8c`)
serving Qwen2.5-3B-Instruct Q4_K_M
(`626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d`),
the starter corpus (5 items) — deliberately not the larger v1 corpus,
since the goal here was validating the new measurement mechanism itself
with a quick, already-thermally-characterized configuration, not
re-running the accuracy benchmark.

**Status:** First real hardware use of `DnsDuringSampler`
(`--sample-dns-during-generation`, built the same day). Closes ADR-0012's
second revisit condition **for this specific configuration** — llama.cpp
3B on the starter corpus. It does not close the condition universally;
Ollama, the v1 corpus, and 7B have not been measured with this mechanism
yet.

## Method

`DnsDuringSampler` ran a background thread issuing real `dig` queries
against Pi-hole every 0.3 seconds for the exact duration of each corpus
item's `provider.generate()` call — not before/after the whole run, the
gap every prior report in this series named.

## Results

| Item | Duration | Samples | Min | Mean | Max | Exceeded 50ms budget? |
| --- | --- | --- | --- | --- | --- | --- |
| Plain chat | 5.5s | 18 | 16.3ms | 22.3ms | 35.3ms | No |
| `system.health` | 14.8s | 46 | 15.8ms | 24.8ms | 37.9ms | No |
| `pihole.status` | 3.8s | 12 | 15.4ms | 23.1ms | 31.9ms | No |
| `pihole.summary` | 5.9s | 19 | 15.8ms | 24.8ms | 35.8ms | No |
| Goldfish (plain chat) | 13.3s | 41 | 20.4ms | 26.9ms | 41.3ms | No |

Idle baseline (before/after the whole run): 14.74ms / 15.13ms.

**The 50ms absolute budget held throughout — not one of 136 total
samples across all five items exceeded it.** The worst single sample
(41.25ms, on the longest-running item) is also within ADR-0012's 3x-
baseline sub-condition (41.25 / 14.74 ≈ 2.8x). Mean latency during active
generation sat consistently around 1.5–1.8x the idle baseline (22–27ms
vs. ~15ms) — a real, measurable, and expected degradation while the
device is under CPU load, but nowhere near either budget threshold.

Temperature (57.3°C → 83.2°C) and memory (27.8% → 28.5%) matched every
prior llama.cpp-3B starter-corpus run exactly — no new finding there,
confirming this pass didn't accidentally change the underlying
workload's behavior, only added a new measurement to it.

## What This Does and Doesn't Show

This is real, positive evidence that DNS resolution stays comfortably
responsive while llama.cpp/Qwen2.5-3B is actively generating — the
concern ADR-0012's DNS-latency budget exists to catch didn't materialize
for this configuration. It does **not** show:

- Whether Ollama's DNS-latency-during-generation behavior differs (not
  yet measured with this mechanism).
- Whether the larger, more capability-heavy v1 corpus (with its longer,
  more varied requests, including multi-turn ones) behaves the same way
  — the starter corpus was chosen deliberately for a quick validation
  pass, not a comprehensive one.
- Whether Qwen2.5-7B, already known to be slower and hotter, also stays
  within budget — a real open question given its longer per-request
  duration would mean more sustained DNS query pressure during a
  single generation.
- Behavior under concurrent multi-request load (a real household could
  plausibly have overlapping questions from different people) — this
  harness runs corpus items sequentially, one at a time.

## Conclusion

The DNS-latency-during-generation measurement gap named in every prior
report in this series, and as ADR-0012's second revisit condition, is
now closed **for llama.cpp-3B on the starter corpus specifically** —
with a genuinely reassuring result. The mechanism itself is proven to
work correctly on real hardware. Extending this same measurement to
Ollama, the v1 corpus, and 7B remains open, and the revisit condition
should not be treated as universally closed until those exist too.
