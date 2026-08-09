# llama.cpp + Qwen2.5-3B-Instruct: First Real Runner/Model Benchmark Report

**Date:** 2026-08-09

**Hardware:** Raspberry Pi 5 Model B Rev 1.1, official Raspberry Pi Active
Cooler (fan + heatsink), Debian 13 (trixie), `aarch64`. Default power mode
(not modified). This is the project's sole qualification device — the
same one every other real-hardware report in this directory targets,
running its normal Pi-hole/Console workload throughout.

**Runtime:** llama.cpp server, official Docker image
`ghcr.io/ggml-org/llama.cpp:server`, digest
`sha256:5a7d34c5a378b6f3b542e71690bd82db7b5bf31fd77d9d1582cc7f2c9043ad8c`,
`data-root` already configured to `/data/docker` (the large persistent
partition — the root A/B system slot has only ~2GB free, not enough for
a model-serving image). Launched with `-c 4096 -t 4`, loopback-only
(`127.0.0.1:8081`), per RFC-0002's "must not expose an inference HTTP
port to the LAN."

**Model:** `Qwen/Qwen2.5-3B-Instruct-GGUF`, `qwen2.5-3b-instruct-q4_k_m.gguf`
(Q4_K_M quantization), downloaded from
`https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf`,
2,104,932,768 bytes, magic bytes verified as a real GGUF file before use.
Selected as the first candidate for its balance of CPU-only ARM64
inference speed and explicit function/tool-calling support — chosen by
the assistant per the project owner's direction ("pick the most suitable
model"), not yet compared against any larger model or against Ollama.

**Status:** First genuine, live-hardware run of
`scripts/benchmark-inference-runner.py` — the harness
[the previous session](https://github.com/sovereignfs/sovereign-os/commit/340ec30)
built and only unit-tested against a fake in-process provider until now.
Found and fixed one real bug along the way (below) before the numbers in
this report can be trusted.

## A Real Bug the First Run Found

The very first run against real hardware produced **empty completions for
every capability-eliciting prompt** — `capability_proposals: []`,
`capability_selection_correct: false` across the board, despite plain
chat working fine. A raw `curl` of the identical request (same messages,
same `tools` payload) showed the model had, in fact, correctly proposed
`system.health` every time. The harness's default streaming mode was
silently discarding it: `LlamaCppProvider`'s streaming path only ever
parsed token/usage deltas and never implemented incremental tool-call
reassembly — a deliberate scoping decision from when the adapter was
built, but one nothing enforced, so a real capability proposal vanished
with no error, no warning, nothing in the logs.

Fixed (commit `6e67f3f`) at the layer that should have caught it:
`LlamaCppProvider.generate()` now refuses `stream=True` combined with a
capability catalog outright, before making any request, and the harness
forces single-shot mode for any corpus item that uses capabilities
regardless of its global streaming flag. Re-running after the fix, on
the same cooled-down device, produced the real results below. This is
recorded here rather than quietly folded into "the benchmark works"
because it's exactly the kind of gap this project's culture treats as
worth naming: a mocked test suite that never combined streaming with
tool-calling in one scenario couldn't have caught it, and it took a real
`curl` against a real server to prove the model, not the harness, was
right.

## Results (post-fix run)

| Item | Result | TTFT | Tokens/s | Notes |
| --- | --- | --- | --- | --- |
| Plain chat ("what does a Pi-hole do") | Correct, coherent answer | 0.18s | 4.91 | No tools offered |
| `system.health` question | **Correct** capability proposed | n/a (single-shot) | 4.72 | `{}` arguments, matching the schema |
| `pihole.status` question | **Correct** capability proposed | n/a (single-shot) | 4.92 | `{}` arguments |
| `pihole.summary` question | **Correct** capability proposed | n/a (single-shot) | 4.79 | `{"period": "last_24h"}` — correctly extracted from "last 24 hours" in the prompt, not just the right capability name |
| Unrelated goldfish-naming question | No capability proposed (correct) | 10.40s | 5.29 | Slow TTFT outlier, no clear cause identified this pass |

**5/5 correct on this starter corpus**, including one real structured-
argument extraction, not just capability-name selection. Full report:
`report-2.json` (not checked in — regenerate by re-running the harness;
see Reproduction below).

Resource sampling, before → after this ~25-second, 5-item run:

- **Memory:** 28.3% → 28.2% used — negligible, no pressure at this model
  size.
- **DNS latency** (`dig` against Pi-hole, real query): 14.32ms → 15.37ms
  — a small increase, but this only samples immediately before/after the
  whole run, not *during* active generation, which is the actually
  DNS-latency-sensitive window RFC-0002's budget concerns itself with.
  Named as a real harness limitation below, not a clean result.
- **Temperature: 58.4°C → 83.2°C.** Reproduced consistently — the first
  (bug-affected but thermally identical) run showed the same jump,
  56.8°C → 83.7°C. This is **with the official Active Cooler installed**,
  the best stock cooling option, after roughly 25 seconds of light,
  intermittent CPU work (five short generations, not sustained
  inference). The Raspberry Pi 5 SoC begins throttling near 85°C. This
  is the most significant finding in this report: even brief inference
  bursts push this shared appliance (which also needs to keep serving
  DNS reliably) close to its thermal ceiling with the best cooling
  Raspberry Pi sells for it. Sustained conversation load, not just
  isolated benchmark bursts, needs real thermal-budget measurement
  before any conclusion about production viability.

## Limitations of This Pass

- **One model, one runner, one small corpus.** This is the first data
  point, not a comparison. Qwen2.5-3B was not benchmarked against a
  larger model or against Ollama — both remain, per the project owner's
  explicit direction to start with llama.cpp alone.
- **No model digest recorded.** The downloaded GGUF file was deleted
  during cleanup before its SHA-256 was captured — a real process gap
  against RFC-0002/`local-ai-options.md`'s stated requirement to record
  "the exact model, GGUF digest." The file size (2,104,932,768 bytes)
  and source URL are recorded instead; computing and recording the
  digest is a concrete fix for the next run reusing this model.
- **DNS latency was only sampled before/after the whole run, not during
  individual generations.** The harness doesn't yet measure DNS latency
  concurrently with an in-flight request, which is the scenario that
  actually matters for the stated DNS-service budget. A real gap to
  close before this benchmark's DNS numbers can inform a budget
  decision.
- **Thermal measurement was a single ~25-second burst**, not sustained
  load. The 83°C finding is real and reproduced twice, but doesn't yet
  answer "what happens after ten minutes of continuous conversation" —
  the more operationally relevant question for an always-on appliance.
- **The slow-TTFT outlier** on the unrelated question (10.40s vs. 0.18s
  for the other plain-chat-shaped item) was not investigated — could be
  cache-related, could be noise from a single sample. Not enough data
  to say.

## Reproduction

The model and container were both removed after this run (no lasting
footprint on the device — Docker's `data-root` is `/data/docker`, but
nothing was left running or resident). To reproduce:

```bash
# On the device, download the model (~2GB) and start the server:
curl -L -o qwen2.5-3b-instruct-q4_k_m.gguf \
  "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
sudo docker run -d --name sovereign-benchmark-llama \
  -p 127.0.0.1:8081:8080 -v "$PWD":/models \
  ghcr.io/ggml-org/llama.cpp:server \
  -m /models/qwen2.5-3b-instruct-q4_k_m.gguf --host 0.0.0.0 --port 8080 -c 4096 -t 4

# Copy image-builder/sovereign/appliance/lib/*.py and
# scripts/benchmark-inference-runner.py + the starter corpus over, then:
PYTHONPATH=<lib dir> python3 benchmark-inference-runner.py \
  --corpus benchmark-inference-corpus-starter.json \
  --base-url http://127.0.0.1:8081 --output report.json
```

## Conclusion

llama.cpp + Qwen2.5-3B-Instruct correctly handles this project's real,
registered capabilities on real Raspberry Pi 5 hardware — 5/5 on a small
starter corpus, including correct structured-argument extraction, at a
modest but usable ~4.7–5.3 tokens/second. The thermal finding is the one
that should shape what happens next: this device runs close to its
throttle point under even brief inference load with the best stock
cooling available, which matters more for an always-on household DNS
appliance than raw token throughput does. No runner or model selection
is made here — this is one real data point toward that decision, not
the decision itself.

**Update, same day:** a direct comparison against Qwen2.5-7B on the same
device and corpus followed — see the
[Qwen2.5-7B benchmark report](llamacpp-qwen2.5-7b-benchmark-report.md).
7B matched this model's accuracy exactly but was substantially slower,
used roughly double the memory, and ran hotter still. Ollama running
the same-quantization-level model was then benchmarked for comparison —
see the [Ollama benchmark report](ollama-qwen2.5-3b-benchmark-report.md):
matching accuracy and comparable steady-state speed, but a real
multi-second first-request penalty from Ollama's lazy model loading
that llama-server's eager loading doesn't have.
