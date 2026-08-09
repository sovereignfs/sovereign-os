#!/usr/bin/env python3

# Reproducible runner/model benchmark harness (RFC-0002's Runner
# Evaluation section; docs/research/local-ai-options.md's Benchmark
# Method). Meant to run ON the qualification Raspberry Pi (via SSH, the
# same way every real hardware pass in this project's docs/research/
# reports has been driven) against a real provider adapter's real,
# loopback-only HTTP port -- resource/thermal/DNS-latency measurements
# below are only meaningful against the device actually running
# inference, not a developer's own machine.
#
# No runner or model selection is made by this script or baked into it.
# It is the measurement method RFC-0002 and local-ai-options.md commit
# to; the result of running it is recorded in an ADR after real
# hardware measurement, not decided here.

import argparse
import datetime
import json
import pathlib
import subprocess
import sys
import time


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "image-builder/sovereign/appliance/lib"))

import sovereign_capabilities as capabilities  # noqa: E402
import sovereign_inference as inference  # noqa: E402
import sovereign_pihole as pihole  # noqa: E402
import sovereign_system as system  # noqa: E402


def real_capability_catalog():
    # Built from the real registries -- construction alone does no I/O
    # (PiholeSession() reads no file and opens no connection until an
    # invocation actually needs a session), so this reflects exactly what
    # a real Conversation Service would present to the model, not a
    # hand-copied approximation that could drift from RFC-0003's actual
    # registered schemas.
    registry = capabilities.Registry()
    system.register(registry)
    pihole.register(registry)
    return registry.catalog()


def timestamp():
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_memory_used_percent():
    # Same read as console-health's memory_summary() -- deliberately not
    # imported from there (an extension-less script, not importable) but
    # small enough that duplicating it here is simpler than restructuring
    # console-health to accommodate a second consumer for three lines.
    try:
        values = {}
        for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0]) * 1024
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        if not total:
            return None
        return round((total - available) * 100 / total, 1)
    except (OSError, UnicodeError, ValueError):
        return None


def read_temperature_celsius():
    try:
        raw = pathlib.Path("/sys/class/thermal/thermal_zone0/temp").read_text()
        return round(int(raw.strip()) / 1000, 1)
    except (OSError, ValueError):
        return None


def measure_dns_latency_ms(dig_path, target):
    start = time.perf_counter()
    try:
        subprocess.run(
            [dig_path, "+short", "+time=2", "+tries=1", "@127.0.0.1", target],
            check=True, capture_output=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return round((time.perf_counter() - start) * 1000, 2)


def run_corpus_item(provider, item, stream, catalog):
    start = time.perf_counter()
    first_token_at = None
    text_parts = []
    proposals = []
    usage = None
    error = None
    uses_capabilities = item.get("use_capabilities", True)
    # A capability proposal can only be read back from a single-shot
    # response (LlamaCppProvider.generate() refuses stream=True with a
    # catalog present, for exactly this reason) -- an item measuring
    # tool-selection accuracy must not silently fall back to streaming
    # and lose it. Pure-chat items still measure token-rate/TTFT via
    # streaming, per the harness's --no-stream flag.
    item_stream = stream and not uses_capabilities
    try:
        for chunk in provider.generate(
            item["messages"],
            capability_catalog=catalog if uses_capabilities else None,
            timeout_seconds=item.get("timeout_seconds", 30),
            stream=item_stream,
        ):
            if not inference.validate_chunk(chunk):
                raise ValueError(f"provider yielded a malformed chunk: {chunk!r}")
            kind = chunk["kind"]
            if kind == "token":
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                text_parts.append(chunk["text"])
            elif kind == "capability_proposal":
                proposals.append(chunk)
            elif kind == "usage":
                usage = chunk
            elif kind == "error":
                raise inference.ProviderError(chunk["code"], chunk["message"])
    except inference.ProviderError as caught:
        error = {"code": caught.code, "message": str(caught)}
    end = time.perf_counter()

    completion_text = "".join(text_parts)
    reported_tokens = usage.get("completion_tokens") if usage else None
    approx_tokens = reported_tokens if reported_tokens else (len(completion_text.split()) or None)
    duration = end - start

    result = {
        "id": item["id"],
        "error": error,
        "time_to_first_token_seconds": round(first_token_at - start, 4) if first_token_at else None,
        "total_duration_seconds": round(duration, 4),
        "completion_tokens": approx_tokens,
        "completion_tokens_are_reported": bool(reported_tokens),
        "tokens_per_second": round(approx_tokens / duration, 2) if duration > 0 and approx_tokens else None,
        "completion_text": completion_text,
        "capability_proposals": [
            {"name": proposal.get("name"), "arguments": proposal.get("arguments")}
            for proposal in proposals
        ],
    }
    # expected_capability has three meaningful states: a capability name
    # (correct iff that name was proposed), `false` (correct iff nothing
    # was proposed -- for prompts where no registered capability applies,
    # including adversarial ones), or absent/null (not scored -- for
    # genuinely ambiguous items where either answer, or none, is
    # reasonable and forcing a verdict would just be noise).
    expected = item.get("expected_capability")
    if expected is False:
        result["capability_selection_correct"] = len(proposals) == 0
    elif expected is not None:
        result["capability_selection_correct"] = any(
            proposal.get("name") == expected for proposal in proposals
        )
    return result


def run_benchmark(provider, corpus, stream=True, dns_target="example.com", dig_path="/usr/bin/dig", catalog=None):
    catalog = real_capability_catalog() if catalog is None else catalog
    report = {
        "schema_version": 1,
        "started_at": timestamp(),
        "corpus_id": corpus.get("id"),
        "corpus_version": corpus.get("version"),
        "capability_catalog_names": sorted({entry["name"] for entry in catalog}),
        "provider_health_before": provider.health(),
        "memory_used_percent_before": read_memory_used_percent(),
        "temperature_celsius_before": read_temperature_celsius(),
        "dns_latency_ms_before": measure_dns_latency_ms(dig_path, dns_target),
        "items": [run_corpus_item(provider, item, stream, catalog) for item in corpus["items"]],
    }
    report["memory_used_percent_after"] = read_memory_used_percent()
    report["temperature_celsius_after"] = read_temperature_celsius()
    report["dns_latency_ms_after"] = measure_dns_latency_ms(dig_path, dns_target)
    report["provider_health_after"] = provider.health()
    report["finished_at"] = timestamp()
    return report


def build_provider(args):
    if args.provider == "llama-cpp":
        return inference.LlamaCppProvider(base_url=args.base_url)
    if args.model is None:
        raise SystemExit("--model is required for --provider ollama")
    return inference.OllamaProvider(model=args.model, base_url=args.base_url)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=pathlib.Path)
    parser.add_argument("--provider", choices=["llama-cpp", "ollama"], default="llama-cpp")
    parser.add_argument("--model", help="Required for --provider ollama; ignored for llama-cpp (one model per process)")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--no-stream", action="store_true")
    parser.add_argument("--dig", default="/usr/bin/dig")
    parser.add_argument("--dns-target", default="example.com")
    args = parser.parse_args()
    if args.base_url is None:
        args.base_url = "http://127.0.0.1:8081" if args.provider == "llama-cpp" else "http://127.0.0.1:11434"

    corpus = json.loads(args.corpus.read_text())
    provider = build_provider(args)
    report = run_benchmark(
        provider, corpus, stream=not args.no_stream,
        dns_target=args.dns_target, dig_path=args.dig,
    )
    report["provider"] = args.provider
    report["model"] = args.model
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
