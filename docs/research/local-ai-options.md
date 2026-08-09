# Local AI Options for Sovereign OS

**Status:** Direction selected; hardware benchmarking underway (five
real passes across two corpora — see Follow-up Decisions below);
resource/DNS-latency budgets accepted ([ADR-0012](../adrs/0012-local-inference-resource-and-dns-latency-budgets.md));
runner/model selection ADR still pending the deferred 7B v1-corpus run
and validating ADR-0012's revisit conditions

**Target:** Raspberry Pi 5 with 16 GB RAM

**Informs:** Runtime architecture, model management, and AI capability invocation RFCs

## Question

Which architecture gives Sovereign OS acceptable local inference, structured
capability selection, privacy, reproducibility, and operational simplicity
without coupling the product to one model runner or chat application?

## Decision Direction

Sovereign OS will own a provider-neutral inference boundary and model lifecycle.
The product will not expose Ollama, llama.cpp, Open WebUI, or any other third-party
runtime as its architectural contract.

For the first Raspberry Pi benchmark:

- **llama.cpp** is the preferred production candidate because its native ARM64
  runtime is comparatively small, it provides direct control of GGUF artifacts,
  and `llama-server` exposes chat, structured output, and tool-calling features
  through an OpenAI-compatible HTTP API.
- **Ollama** is the main comparison candidate and may remain an optional provider.
  It offers a convenient ARM64 installation and model-management experience but
  introduces its own model packaging, storage, and lifecycle abstractions.
- **Open WebUI** is useful for development and model evaluation but will not be
  the Sovereign product interface. Its user, conversation, tool, and
  administration concerns overlap with platform responsibilities Sovereign must
  control itself.

No final runner or model is selected until the benchmark passes on the target
device.

## Functional Requirements

### Inference

- Local chat/generation without an internet connection
- Token streaming and cancellation
- Structured JSON and capability-call proposals
- Bounded context, output, concurrency, and runtime resources
- Health, model identity, and runtime-version reporting
- Replaceable local and explicitly configured remote providers

### Model Lifecycle

- Sovereign-controlled model manifest
- Source and license disclosure
- Cryptographic digest verification
- Offline import and controlled download
- Compatibility, activation, and rollback metadata
- Persistent model storage independent of the replaceable runner

### Safety

- Treat all generated text and tool proposals as untrusted
- Validate capability schemas outside the model runtime
- No direct runner access to shell, Docker socket, service credentials, or
  unrestricted network operations
- Do not expose the inference HTTP port to the LAN
- Preserve Pi-hole responsiveness under inference load

## Candidate Comparison

| Candidate | Best fit | Principal advantage | Principal tradeoff | Planned role |
| --- | --- | --- | --- | --- |
| llama.cpp | Lean local inference | Direct GGUF and resource control; ARM64 server | Sovereign must supply model lifecycle and template compatibility | Preferred benchmark candidate |
| Ollama | Development and convenient model operations | Simple installation, API, and model acquisition | Additional runner-specific packaging and management layer | Comparison and optional adapter |
| Open WebUI | Interactive model evaluation | Mature browser interface for compatible providers | Duplicates product identity, conversation, tool, and administration concerns | Optional development profile only |
| Sovereign conversation UI | Product experience | Can enforce Sovereign privacy, citations, permissions, and confirmations | Must be implemented and maintained | Required product interface |

Broader inference servers aimed primarily at discrete GPUs or multi-user
throughput are not initial Raspberry Pi candidates. They may be reconsidered for
future hardware profiles without changing the provider contract.

## Benchmark Method

Run the same versioned corpus and, where supported, the same model artifact and
quantization through each runner. Record:

- exact hardware, cooling, power mode, OS, runtime, and model digest;
- time to first token and tokens per second;
- peak/steady memory and storage overhead;
- model load and service recovery time;
- temperature and throttling during sustained requests;
- structured argument correctness and tool-selection accuracy;
- rejection of malformed, ambiguous, adversarial, and unsupported requests;
- timeout and cancellation behavior; and
- DNS latency and failure rate with and without active inference.

The runner passes only if it remains inside explicit resource and DNS-service
budgets. Convenience alone is not a selection criterion.

## Web-Augmented Answers

Model inference and web retrieval are separate functions. The model does not get
generic outbound network access.

SearXNG is the selected initial provider for the registered `web.search`
capability. It is self-hosted locally, replaceable behind a Sovereign contract,
and disabled or explicitly enabled according to onboarding policy. Queries still
leave the device for configured upstream search engines, so the UI must disclose
the exact query and external communication. Result pages are accessed only
through a separately constrained `web.fetch` capability.

## Sources

- [llama.cpp project and feature overview](https://github.com/ggml-org/llama.cpp)
- [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [llama.cpp container images](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md)
- [Ollama Linux and ARM64 installation](https://docs.ollama.com/linux)
- [Open WebUI installation and provider support](https://docs.openwebui.com/getting-started/)
- [SearXNG search API](https://docs.searxng.org/dev/search_api.html)

## Follow-up Decisions

1. ✅ The normalized inference API is implemented as `sovereign_inference.py`
   against [RFC-0002](../rfcs/0002-local-conversation-and-inference-runtime.md)
   (Accepted) — a shared `_OpenAICompatibleProvider` base class, with
   `LlamaCppProvider` and `OllamaProvider` subclasses. The
   model-manifest format (Sovereign Model Management's own ownership of
   digest/license/lifecycle) remains undecided — a separate, still-open
   piece of RFC-0002.
2. ✅
   [ADR-0012](../adrs/0012-local-inference-resource-and-dns-latency-budgets.md)
   (Accepted, 2026-08-09) sets numeric thresholds grounded in the four
   real benchmark passes' data: 80°C sustained-temperature budget
   (deliberately below the ~85°C point where real throttling was
   confirmed), a 40%-of-RAM memory ceiling (Qwen2.5-3B fits with margin,
   7B does not), and a provisional 50ms/3x-baseline DNS-latency budget.
   Explicitly names two open measurement gaps (realistic intermittent-
   use thermal behavior, and DNS latency *during* generation rather than
   only before/after) as revisit conditions, not treated as final. The
   second is now closed for llama.cpp-3B on the starter corpus — the
   50ms budget held across all 136 real during-generation samples taken
   (max 41.25ms) — see the
   [DNS-latency-during-generation report](dns-latency-during-generation-qualification-report.md).
   Not yet closed universally: Ollama, the v1 corpus, and 7B remain
   unmeasured with this mechanism.
3. ✅ The tool-call corpus half is done —
   [`scripts/benchmark-inference-corpus-v1.json`](../../scripts/benchmark-inference-corpus-v1.json),
   28 items across plain chat, per-capability phrasing variation,
   deliberately-ambiguous, unsupported/mutating, adversarial (including
   a prompt-injection-in-a-prior-tool-result case exercising RFC-0004's
   untrusted-forever boundary), and multi-turn categories. The
   *model set* half remains open — only Qwen2.5-3B/7B have been tried;
   a real "set" selection (how many candidates, which families) hasn't
   been decided as its own question.
4. 🟡 Partially done: llama.cpp (Qwen2.5-3B and Qwen2.5-7B) and Ollama
   (Qwen2.5-3B) have all run for real on the qualification device
   against the starter corpus — see the
   [3B](llamacpp-qwen2.5-3b-benchmark-report.md),
   [7B](llamacpp-qwen2.5-7b-benchmark-report.md), and
   [Ollama](ollama-qwen2.5-3b-benchmark-report.md) reports. llama.cpp
   3B and Ollama 3B have now also run against the larger v1 corpus —
   see the [v1 corpus report](v1-corpus-benchmark-report.md), which
   finally broke the starter corpus's ceiling effect (85% vs. 75% on
   the identical 28-item set) and confirmed real thermal throttling via
   `vcgencmd get_throttled`. llama.cpp-7B on the v1 corpus was
   deliberately skipped (project owner's explicit choice, given
   confirmed throttling and 7B's already-worse thermal profile) — that
   data point remains open.
5. ⚪ Not yet done: no runner/model selection ADR exists. Real data now
   spans both corpora: accuracy ties on the trivial starter corpus but
   diverges meaningfully on the richer v1 one (llama.cpp ahead, each
   runtime with a distinct and reproducible failure pattern); Ollama's
   lazy model loading vs. llama.cpp's eager loading is now confirmed
   reproducible (seen identically across two separate runs); 7B's cost
   with no measured accuracy benefit over 3B holds on every corpus
   tried so far. Item 2 above is now closed (ADR-0012 Accepted). Still
   missing before a runner/model selection ADR: the llama.cpp-7B
   v1-corpus data point, and validating ADR-0012's two revisit
   conditions (realistic-use thermal behavior, during-generation DNS
   latency) so the selection isn't made against numbers already known
   to be provisional.
