# ADR-0012: Local-Inference Resource and DNS-Latency Budgets

**Status:** Accepted

**Date:** 2026-08-09

**Decision owner:** Project creator

**Related RFCs/research:**
[RFC-0002](../rfcs/0002-local-conversation-and-inference-runtime.md) (Accepted),
[ADR-0004](0004-provider-neutral-assistant-and-web-search.md) (Accepted, names
this exact budget as required follow-up),
[docs/research/local-ai-options.md](../research/local-ai-options.md)
(Follow-up Decision #2),
[llama.cpp 3B](../research/llamacpp-qwen2.5-3b-benchmark-report.md),
[llama.cpp 7B](../research/llamacpp-qwen2.5-7b-benchmark-report.md),
[Ollama 3B](../research/ollama-qwen2.5-3b-benchmark-report.md), and
[v1 corpus](../research/v1-corpus-benchmark-report.md) qualification reports.

**Supersedes:** None

## Context

Four real benchmark passes now exist against the qualification Raspberry
Pi 5, but nothing has turned their numbers into an accepted policy a
runner/model configuration must pass. Both `local-ai-options.md`
("The runner passes only if it remains inside explicit resource and DNS-
service budgets... convenience alone is not a selection criterion") and
RFC-0002's Runner Evaluation section committed to this being a real
gate, not an afterthought — but the actual thresholds have never been
written down.

This is not a hypothetical concern. The v1-corpus benchmark pass
confirmed real thermal throttling on this device via
`vcgencmd get_throttled` (`0xe0000`: frequency capping, throttling, and
soft temperature limit bits all set) — the first genuine confirmation
in this project's history, not an estimate. This device also serves the
household's DNS through Pi-hole; a policy here is about protecting that
responsibility, not just inference performance.

### What the Evidence Actually Shows

| Metric | Idle baseline | Under sustained inference (3B) | Under sustained inference (7B) |
| --- | --- | --- | --- |
| Temperature | 56–59°C (consistent across every pass) | Plateaus 82–85°C over 3–5 min continuous generation; real throttling confirmed | Peaked 84.8°C on a shorter (~100s) run; not tested on the longer v1 corpus (deliberately skipped, see below) |
| Memory used | ~14–28% (varies by what's already resident) | ~28% steady | ~58% steady, roughly double 3B |
| DNS latency (`dig`, before/after only) | 13.6–14.5ms | 15.0–19.8ms after a run | 15.4–19.8ms after a run |

Two honest gaps in this evidence, both inherited from the benchmark
harness's current limitations (named in every qualification report to
date):

1. **DNS latency has only ever been sampled before and after a run, never
   during active generation.** The actual concern — does Pi-hole stay
   responsive *while the household is asking a question* — has not been
   directly measured. The numbers above bound the before/after delta,
   not the worst case.
2. **Every benchmark run so far used back-to-back requests with zero
   idle time between them** — a genuine stress test, not a realistic
   household usage pattern. Real conversational use almost certainly has
   far more idle time between questions than any pass has modeled. The
   throttling observed is real, but it was produced under a harsher
   pattern than actual use is likely to be.

This ADR sets a policy anyway, grounded in what's actually known, rather
than waiting for a perfect measurement that doesn't exist yet — but it
names both gaps as concrete, tracked follow-up work, not swept under the
policy.

## Decision

### Thermal

Raspberry Pi 5's own thermal throttling is a *safe*, designed protective
mechanism — it reduces clock speed, it does not risk hardware damage.
"Throttling occurred" is therefore treated here as a **product-quality
signal, not a safety failure**: a household would notice slower
responses, not a broken device.

- A configuration that throttles under a **realistic, intermittent**
  household conversation pattern fails this budget. A configuration that
  only throttles under **continuous, back-to-back generation sustained
  for multiple minutes** (the pattern every benchmark pass to date has
  actually used) does not automatically fail it, because that pattern is
  not representative of real use — but it is flagged as a real risk that
  needs the Conversation Service to actively manage (see Consequences).
- **Numeric budget:** sustained temperature must not exceed 80°C under a
  realistic usage pattern (a household asking occasional questions with
  normal gaps between them, not a benchmark corpus run end to end).
  80°C is chosen deliberately below the ~85°C point where throttling was
  actually observed, to leave real margin rather than a budget the
  device is already known to violate under stress-test conditions.
- This 80°C figure has **not yet been validated against a realistic
  intermittent-use pattern** — only against continuous stress-test runs,
  which is a different question. Validating it is required follow-up
  (see Validation and Revisit Conditions), not assumed to already hold.

### Memory

- **Numeric budget:** a selected model's steady-state memory footprint
  must not exceed **40% of total system RAM**, leaving real headroom for
  Pi-hole, Console, the OS, and the capability executor to run
  concurrently without contention.
- Qwen2.5-3B (~28% observed) is within this budget with real margin.
  Qwen2.5-7B (~58% observed) is not — this is a concrete, evidence-based
  reason 7B does not currently meet this policy, independent of the
  accuracy/speed findings the benchmark reports already named.

### DNS Latency

- **Numeric budget (provisional):** DNS resolution latency, measured
  locally against Pi-hole, must not exceed **50ms** and must not regress
  more than **3x** over the device's own idle baseline, during any
  window where inference is active.
- This budget is explicitly **provisional** given the before/after-only
  measurement gap named above. It is set with real margin above every
  before/after delta observed to date (worst case ~20ms absolute, ~1.4x
  the idle baseline) specifically *because* the true concurrent-load
  number is unmeasured and could be worse. Closing that measurement gap
  (see Validation and Revisit Conditions) may tighten or loosen this
  number once real data exists.

### Scope

This budget applies to the **runner + model combination as a whole**,
not to either in isolation — a fast runner with a model too large to fit
the memory budget still fails, and vice versa. It is evaluated during
real hardware qualification (per this project's standing practice), not
estimated.

## Consequences

### Positive

- Turns "convenience alone is not a selection criterion" from a stated
  intention into an actual, checkable gate future runner/model
  qualification passes (including the still-open llama.cpp-7B v1-corpus
  data point) can be measured against.
- Gives the eventual Conversation Service a concrete design constraint:
  since realistic-use thermal behavior isn't validated yet, it should
  actively avoid the continuous-generation pattern that's known to
  throttle — e.g., no unbounded back-to-back tool-calling loops without
  a cooldown, bounded per-turn capability-invocation counts (already a
  RFC-0003/RFC-0004 requirement for other reasons), and surfacing a
  "the assistant is still catching up" state rather than silently
  queuing requests during a hot stretch.
- Makes Qwen2.5-7B's disqualification concrete and evidence-based (memory
  budget), not just "seemed worse" from the earlier benchmark reports'
  softer framing.

### Negative

- The thermal and DNS budgets are both explicitly provisional pending
  measurements this project doesn't have yet — this ADR is honest about
  that rather than presenting false precision, but it does mean the
  numbers here may need real revision, not just fine-tuning, once a
  realistic-pattern thermal test and a during-generation DNS-latency
  measurement actually exist.
- A 40%-of-RAM memory ceiling is a real constraint on future model
  selection — it rules out larger, potentially more capable models
  without additional hardware (more RAM) or architecture changes (e.g.,
  swap, model offloading) neither of which this ADR proposes.

### Risks

- If the realistic-use thermal validation (follow-up, below) shows even
  intermittent household use throttles this device, the entire local-
  inference approach for this hardware generation may need reconsidering
  — a scope well beyond this ADR, but a real possibility this budget is
  designed to surface early rather than discover after Milestone 4 ships.
- Setting the DNS-latency budget from before/after data alone risks it
  being too lenient if concurrent-load latency turns out much worse than
  the delta observed — the explicit provisional status is meant to keep
  this risk visible, not hide it.

## Alternatives Considered

- **Wait for a during-generation DNS-latency measurement before setting
  any budget at all.** Rejected: this project's own research doc already
  named "define measurable budgets" as a required decision, and four
  real qualification passes already exist with real data. A provisional,
  clearly-labeled budget that can be tightened later is more useful than
  no budget while a perfect measurement is pending.
- **Set the thermal budget at the observed throttle point (~85°C) rather
  than below it.** Rejected: that would define "safe" as "exactly the
  point we already confirmed causes throttling," which isn't a real
  margin — it's rubber-stamping stress-test behavior as normal.
- **Set the memory budget higher (e.g., 60%) to allow 7B.** Rejected:
  the benchmark reports already found no measured accuracy benefit from
  7B on any corpus tried, at roughly double the memory cost and a real
  (if reproducible-shape, not definitively climbing) thermal cost —
  there's no evidence-based reason to spend the headroom.

## Validation and Revisit Conditions

This ADR should be revisited when either of the following becomes
available, and the numbers above should be treated as provisional until
then:

1. **A realistic, intermittent-use thermal pass** — a benchmark run (or
   real household use, once the Conversation Service exists) with actual
   gaps between requests, not back-to-back generation, measuring whether
   80°C genuinely holds under real conditions rather than only being
   inferred from stress-test data.
2. **A during-generation DNS-latency measurement** — the harness
   mechanism now exists (`DnsDuringSampler`,
   `--sample-dns-during-generation`, background `dig` sampling for the
   duration of each item's generation, checked against this ADR's 50ms
   budget), but no real hardware run has used it yet. This condition
   isn't closed until a real qualification pass reports real
   during-generation numbers, not just that the capability to measure
   them exists.

Until then, this ADR's numbers are the accepted policy, but explicitly a
starting point grounded in real evidence rather than a final, precisely
validated figure.
