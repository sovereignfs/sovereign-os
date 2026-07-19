# Local AI Options for the Preview

**Status:** Planned

## Question

Which AI-provider path gives the preview acceptable tool-selection reliability, latency, privacy, and operational simplicity?

## Alternatives

- Fully local inference on the Raspberry Pi
- User-configured remote provider
- Local default with explicit remote option
- Remote preview default with a stable local-provider boundary

## Evaluation Criteria

- Correct selection of supported capabilities
- Correct structured arguments
- Safe rejection of unsupported requests
- End-to-end response latency
- Memory, CPU, thermal, and storage requirements
- Model and runtime licensing
- Offline behavior
- Data transmitted to remote providers
- Setup and maintenance burden
- Replaceability of provider and model

## Required Method

Use a versioned prompt and test corpus covering successful, ambiguous, malformed, adversarial, and unsupported requests. Record exact model, quantization, runtime, parameters, hardware, and results.

## Decision Informed

AI capability invocation and runtime architecture RFCs.

