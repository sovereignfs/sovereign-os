# Ollama + Qwen2.5-3B: Third Benchmark Report (Runner Comparison)

**Date:** 2026-08-09

**Hardware:** Same qualification device, same day, back-to-back with the
[llama.cpp 3B](llamacpp-qwen2.5-3b-benchmark-report.md) and
[llama.cpp 7B](llamacpp-qwen2.5-7b-benchmark-report.md) reports.

**Runtime:** Ollama's official Docker image (`ollama/ollama`), version
`0.32.6` (from `/api/version`), model storage volume-mounted at
`/root/.ollama` on the persistent `/data` partition (same
root-partition-is-too-small constraint as the llama.cpp runs), loopback
bound (`127.0.0.1:11434`).

**Model:** `qwen2.5:3b` pulled from Ollama's own library
(`ollama pull qwen2.5:3b`, not the Hugging Face GGUF used for the
llama.cpp runs), digest
`357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`.
Ollama's own metadata (`/api/tags`) confirms `quantization_level:
Q4_K_M`, `parameter_size: 3.1B`, `format: gguf`, `capabilities:
["completion", "tools"]` — the same quantization *level* as the
llama.cpp GGUF, though not necessarily bit-identical (different
conversion/build pipeline, per Ollama's own library vs. the
community-published Hugging Face file). This is the fairest comparison
practical without hand-importing the exact same file into Ollama via a
Modelfile, which this pass didn't attempt.

**Status:** First real Ollama run, using the `OllamaProvider` adapter
built for this pass — refactored to share its OpenAI-compatible request
handling with `LlamaCppProvider` (same base class) specifically so the
streaming/tool-call bug the first llama.cpp run found couldn't
independently recur in a second, hand-copied implementation. It didn't;
this run needed no mid-benchmark fix.

## Results vs. llama.cpp 3B

| Item | llama.cpp 3B tok/s | Ollama 3B tok/s | Both correct? |
| --- | --- | --- | --- |
| Plain chat | 4.91 | 1.71 | — |
| `system.health` | 4.72 | 1.88 | ✅ |
| `pihole.status` | 4.92 | 4.49 | ✅ |
| `pihole.summary` | 4.79 | 4.70 | ✅ (both correctly extracted `period: last_24h`) |
| Goldfish (no tool expected) | 5.29 | 5.20 | ✅ (neither proposed one) |

**Accuracy: identical, 5/5**, matching both llama.cpp runs exactly —
same ceiling-effect caveat as the 7B report applies here too.

**Speed has a real, notable shape difference, not just a magnitude
one.** Ollama's first two calls (1.71, 1.88 tok/s) are markedly slower
than llama.cpp's (4.91, 4.72), but its last three (4.49, 4.70, 5.20)
land within noise of llama.cpp's numbers. This isn't random variance —
**memory usage jumped from 14.2% to 28.6% partway through the run**,
whereas llama.cpp's 3B run held steady at ~28% throughout. Ollama loads
a model lazily on first request rather than eagerly at server start the
way llama-server does; the first call's measured duration includes real
model-load time, not just generation time. The plain-chat item's
**time-to-first-token was 6.96 seconds**, against llama.cpp's 0.18
seconds for the equivalent question — almost entirely load latency, not
a genuine per-token speed difference.

**Operational implication:** a real deployment using Ollama would need
either a warm-up request after starting the service (so the first real
household question isn't the one that eats a multi-second load penalty)
or `OLLAMA_KEEP_ALIVE`-style tuning to keep the model resident — neither
of which llama-server needs, since it loads its one configured model
before accepting any request at all. This is a genuine operational
tradeoff this benchmark surfaced, not a flaw in either runner.

**Temperature: 57.9°C → 82.6°C**, closely matching llama.cpp 3B's
57.3°C → 83.2°C — thermal behavior looks driven by the workload and
device, not the runtime, for this model size.

**DNS latency:** 13.69ms → 14.98ms, comparable to llama.cpp 3B's
14.32ms → 15.37ms. No runtime-specific signal here either, subject to
the same before/after-only sampling limitation every report in this
series has named.

## Limitations

- Same starter-corpus ceiling effect as the other two reports: cannot
  distinguish answer *quality*, only structured-proposal correctness.
- The model is not bit-identical to the llama.cpp GGUF (same
  quantization level, different build) — a real, disclosed caveat on
  how directly "runtime speed" numbers can be compared apples-to-apples,
  separate from the load-latency effect above (which is a genuine
  runtime-behavior difference, not a model-difference artifact).
- Only one Ollama run — the load-latency effect wasn't independently
  re-verified with a second cold-start run before concluding it's
  reproducible, unlike the llama.cpp findings (which were consistent
  across two separate model runs). Worth confirming before treating it
  as settled rather than probable.

## Conclusion

Ollama matches llama.cpp's accuracy exactly and, once its model is
warm, its per-token speed too — but its lazy model loading imposes a
real, multi-second first-request penalty llama-server's eager loading
doesn't have. Thermal and DNS-latency behavior look runtime-independent
at this model size. Combined with the two llama.cpp reports, this is
three real data points now: still not a final selection (per the
project owner's own sequencing, Ollama was benchmarked after llama.cpp
alone, and a larger evaluation corpus remains undecided), but llama.cpp
now has a real, measured operational edge specifically around
cold-start responsiveness that any Ollama-based design would need to
account for.
