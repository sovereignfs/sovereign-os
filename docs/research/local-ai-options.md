# Local AI Options for Sovereign OS

**Status:** Direction selected; hardware benchmark pending

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

1. Approve the normalized inference API and model-manifest format.
2. Define measurable Raspberry Pi resource and DNS latency budgets.
3. Select the benchmark model set and tool-call corpus.
4. Run llama.cpp and Ollama on the target device.
5. Record the runner/model selection in an ADR.
