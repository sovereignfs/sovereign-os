import argparse
import json
import runpy
import sys
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts/benchmark-inference-runner.py"
CORPUS_PATH = ROOT / "scripts/benchmark-inference-corpus-starter.json"
LIB = ROOT / "image-builder/sovereign/appliance/lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import sovereign_inference as inference  # noqa: E402


class FakeProvider:
    def __init__(self, chunks=None, health=None, raise_error=None, delay_seconds=0):
        self._chunks = chunks if chunks is not None else [{"kind": "done"}]
        self._health = health if health is not None else {"healthy": True, "model_name": "fake", "runtime_version": "0"}
        self._raise_error = raise_error
        self._delay_seconds = delay_seconds
        self.last_capability_catalog = None
        self.last_stream = None

    def health(self):
        return self._health

    def generate(self, messages, capability_catalog=None, max_tokens=None, timeout_seconds=30, stream=True):
        self.last_capability_catalog = capability_catalog
        self.last_stream = stream
        if self._delay_seconds:
            time.sleep(self._delay_seconds)
        if self._raise_error is not None:
            raise self._raise_error
        yield from self._chunks


class BenchmarkRunnerTestCase(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(SCRIPT_PATH), run_name="not_main")


class RunCorpusItemTests(BenchmarkRunnerTestCase):
    def item(self, **overrides):
        base = {"id": "test-item", "messages": [{"role": "user", "content": "hi"}]}
        base.update(overrides)
        return base

    def test_computes_time_to_first_token_and_tokens_per_second(self):
        provider = FakeProvider(chunks=[
            {"kind": "token", "text": "hello"},
            {"kind": "token", "text": " world"},
            {"kind": "done"},
        ])
        result = self.module["run_corpus_item"](provider, self.item(), stream=True, catalog=[])
        self.assertIsNotNone(result["time_to_first_token_seconds"])
        self.assertGreaterEqual(result["total_duration_seconds"], 0)
        self.assertEqual(result["completion_text"], "hello world")
        self.assertFalse(result["completion_tokens_are_reported"])
        self.assertIsNotNone(result["tokens_per_second"])

    def test_prefers_reported_usage_over_word_count(self):
        provider = FakeProvider(chunks=[
            {"kind": "token", "text": "hello world"},
            {"kind": "usage", "prompt_tokens": 3, "completion_tokens": 42},
            {"kind": "done"},
        ])
        result = self.module["run_corpus_item"](provider, self.item(), stream=True, catalog=[])
        self.assertEqual(result["completion_tokens"], 42)
        self.assertTrue(result["completion_tokens_are_reported"])

    def test_no_tokens_yields_none_time_to_first_token(self):
        provider = FakeProvider(chunks=[{"kind": "done"}])
        result = self.module["run_corpus_item"](provider, self.item(), stream=True, catalog=[])
        self.assertIsNone(result["time_to_first_token_seconds"])

    def test_collects_capability_proposals(self):
        provider = FakeProvider(chunks=[
            {"kind": "capability_proposal", "name": "system.health", "arguments": {}},
            {"kind": "done"},
        ])
        result = self.module["run_corpus_item"](provider, self.item(), stream=False, catalog=[])
        self.assertEqual(result["capability_proposals"], [{"name": "system.health", "arguments": {}}])

    def test_capability_selection_correct_true_on_match(self):
        provider = FakeProvider(chunks=[
            {"kind": "capability_proposal", "name": "system.health", "arguments": {}},
            {"kind": "done"},
        ])
        result = self.module["run_corpus_item"](
            provider, self.item(expected_capability="system.health"), stream=False, catalog=[]
        )
        self.assertTrue(result["capability_selection_correct"])

    def test_capability_selection_correct_false_on_mismatch(self):
        provider = FakeProvider(chunks=[
            {"kind": "capability_proposal", "name": "pihole.status", "arguments": {}},
            {"kind": "done"},
        ])
        result = self.module["run_corpus_item"](
            provider, self.item(expected_capability="system.health"), stream=False, catalog=[]
        )
        self.assertFalse(result["capability_selection_correct"])

    def test_no_expected_capability_key_omits_selection_field(self):
        provider = FakeProvider(chunks=[{"kind": "done"}])
        result = self.module["run_corpus_item"](provider, self.item(), stream=True, catalog=[])
        self.assertNotIn("capability_selection_correct", result)

    def test_expected_capability_false_correct_when_nothing_proposed(self):
        provider = FakeProvider(chunks=[{"kind": "done"}])
        result = self.module["run_corpus_item"](
            provider, self.item(expected_capability=False), stream=False, catalog=[]
        )
        self.assertTrue(result["capability_selection_correct"])

    def test_expected_capability_false_incorrect_when_something_proposed(self):
        # The important adversarial case: expected_capability=false means
        # "no registered capability applies here" -- a model proposing
        # anything at all, including something unregistered/hallucinated,
        # must score as wrong, not merely unscored.
        provider = FakeProvider(chunks=[
            {"kind": "capability_proposal", "name": "pihole.disable", "arguments": {}},
            {"kind": "done"},
        ])
        result = self.module["run_corpus_item"](
            provider, self.item(expected_capability=False), stream=False, catalog=[]
        )
        self.assertFalse(result["capability_selection_correct"])

    def test_provider_error_is_captured_not_raised(self):
        provider = FakeProvider(raise_error=inference.ProviderError("PROVIDER_UNREACHABLE", "down"))
        result = self.module["run_corpus_item"](provider, self.item(), stream=True, catalog=[])
        self.assertEqual(result["error"], {"code": "PROVIDER_UNREACHABLE", "message": "down"})

    def test_malformed_chunk_raises_rather_than_silently_continuing(self):
        # Deliberate: a benchmark harness should surface an adapter bug
        # loudly, not paper over it the way a live capability executor
        # must isolate failures per-invocation.
        provider = FakeProvider(chunks=[{"kind": "not_a_real_kind"}])
        with self.assertRaises(ValueError):
            self.module["run_corpus_item"](provider, self.item(), stream=True, catalog=[])

    def test_use_capabilities_false_passes_no_catalog(self):
        provider = FakeProvider()
        self.module["run_corpus_item"](
            provider, self.item(use_capabilities=False), stream=True, catalog=[{"name": "system.health"}]
        )
        self.assertIsNone(provider.last_capability_catalog)

    def test_use_capabilities_default_true_passes_catalog(self):
        provider = FakeProvider()
        catalog = [{"name": "system.health"}]
        self.module["run_corpus_item"](provider, self.item(), stream=True, catalog=catalog)
        self.assertEqual(provider.last_capability_catalog, catalog)

    def test_capability_items_always_run_single_shot_even_if_harness_streams(self):
        # Regression test for a real bug this exact scenario hit on real
        # hardware: LlamaCppProvider can't read tool calls from a
        # streamed response, so a capability-using item must never be
        # sent with stream=True regardless of the harness-wide flag, or
        # a real capability proposal silently disappears.
        provider = FakeProvider()
        self.module["run_corpus_item"](provider, self.item(), stream=True, catalog=[{"name": "system.health"}])
        self.assertFalse(provider.last_stream)

    def test_plain_chat_items_respect_the_harness_stream_flag(self):
        provider = FakeProvider()
        self.module["run_corpus_item"](
            provider, self.item(use_capabilities=False), stream=True, catalog=[{"name": "system.health"}]
        )
        self.assertTrue(provider.last_stream)

    @mock.patch("subprocess.run")
    def test_dns_during_generation_absent_by_default(self, subprocess_run):
        provider = FakeProvider()
        result = self.module["run_corpus_item"](provider, self.item(), stream=True, catalog=[])
        self.assertIsNone(result["dns_latency_during_generation"])

    @mock.patch("subprocess.run")
    def test_dns_during_generation_populated_when_configured(self, subprocess_run):
        provider = FakeProvider(delay_seconds=0.15)
        config = {"dig_path": "/usr/bin/dig", "target": "example.com", "interval_seconds": 0.03}
        result = self.module["run_corpus_item"](
            provider, self.item(), stream=True, catalog=[], dns_during_config=config
        )
        summary = result["dns_latency_during_generation"]
        self.assertIsNotNone(summary)
        self.assertGreaterEqual(summary["count"], 1)


class DnsDuringSamplerTests(BenchmarkRunnerTestCase):
    @mock.patch("subprocess.run")
    def test_collects_samples_while_running(self, subprocess_run):
        sampler = self.module["DnsDuringSampler"]("/usr/bin/dig", "example.com", 0.03)
        sampler.start()
        time.sleep(0.15)
        samples = sampler.stop()
        self.assertGreaterEqual(len(samples), 1)

    @mock.patch("subprocess.run")
    def test_stop_returns_promptly_even_with_a_slow_interval(self, subprocess_run):
        # Event.wait(timeout) wakes immediately on set() -- stop() must
        # not block for anywhere near the full interval.
        sampler = self.module["DnsDuringSampler"]("/usr/bin/dig", "example.com", 10)
        sampler.start()
        time.sleep(0.02)
        start = time.perf_counter()
        sampler.stop()
        self.assertLess(time.perf_counter() - start, 1)

    def test_no_samples_when_dig_is_unavailable(self):
        # measure_dns_latency_ms() itself is what's mocked away here (via
        # a nonexistent dig path with no subprocess mock), confirming the
        # sampler thread survives failed samples rather than crashing.
        sampler = self.module["DnsDuringSampler"]("/nonexistent/dig", "example.com", 0.02)
        sampler.start()
        time.sleep(0.1)
        samples = sampler.stop()
        self.assertEqual(samples, [])


class SummarizeDnsSamplesTests(BenchmarkRunnerTestCase):
    def test_empty_samples(self):
        summary = self.module["summarize_dns_samples"]([])
        self.assertEqual(summary, {"count": 0, "min_ms": None, "max_ms": None, "mean_ms": None, "exceeded_budget": None})

    def test_computes_min_max_mean(self):
        summary = self.module["summarize_dns_samples"]([10, 20, 30])
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["min_ms"], 10)
        self.assertEqual(summary["max_ms"], 30)
        self.assertEqual(summary["mean_ms"], 20.0)

    def test_exceeded_budget_true_when_max_over_threshold(self):
        summary = self.module["summarize_dns_samples"]([10, 60], budget_ms=50)
        self.assertTrue(summary["exceeded_budget"])

    def test_exceeded_budget_false_when_within_threshold(self):
        summary = self.module["summarize_dns_samples"]([10, 40], budget_ms=50)
        self.assertFalse(summary["exceeded_budget"])

    def test_default_budget_matches_adr_0012(self):
        # ADR-0012's accepted DNS-latency budget is 50ms -- pinning this
        # here means a future edit to the default can't silently drift
        # from the accepted policy without a test noticing.
        summary_at_budget = self.module["summarize_dns_samples"]([50])
        summary_over_budget = self.module["summarize_dns_samples"]([50.1])
        self.assertFalse(summary_at_budget["exceeded_budget"])
        self.assertTrue(summary_over_budget["exceeded_budget"])


class RunBenchmarkTests(BenchmarkRunnerTestCase):
    # measure_dns_latency_ms() shells out to a real `dig`; on a machine
    # with nothing listening on 127.0.0.1:53 that's a real multi-second
    # timeout per call, twice per run_benchmark() call. Mocking
    # subprocess.run keeps this suite fast and independent of whatever
    # DNS state the machine running it happens to have.
    @mock.patch("subprocess.run")
    def test_report_shape_and_item_count(self, subprocess_run):
        provider = FakeProvider(chunks=[{"kind": "token", "text": "ok"}, {"kind": "done"}])
        corpus = {"id": "unit-test-corpus", "version": 1, "items": [
            {"id": "a", "messages": [{"role": "user", "content": "hi"}]},
            {"id": "b", "messages": [{"role": "user", "content": "hi again"}]},
        ]}
        report = self.module["run_benchmark"](provider, corpus, catalog=[])
        self.assertEqual(report["corpus_id"], "unit-test-corpus")
        self.assertEqual(report["corpus_version"], 1)
        self.assertEqual(len(report["items"]), 2)
        self.assertIn("provider_health_before", report)
        self.assertIn("provider_health_after", report)
        self.assertIn("dns_latency_ms_before", report)
        self.assertIn("memory_used_percent_before", report)

    @mock.patch("subprocess.run")
    def test_builds_real_catalog_when_none_provided(self, subprocess_run):
        provider = FakeProvider()
        corpus = {"id": "x", "version": 1, "items": [{"id": "a", "messages": [{"role": "user", "content": "hi"}]}]}
        report = self.module["run_benchmark"](provider, corpus)
        self.assertIn("system.health", report["capability_catalog_names"])
        self.assertIn("pihole.status", report["capability_catalog_names"])
        self.assertIn("pihole.summary", report["capability_catalog_names"])

    @mock.patch("subprocess.run")
    def test_dns_during_generation_off_by_default(self, subprocess_run):
        provider = FakeProvider()
        corpus = {"id": "x", "version": 1, "items": [{"id": "a", "messages": [{"role": "user", "content": "hi"}]}]}
        report = self.module["run_benchmark"](provider, corpus, catalog=[])
        self.assertIsNone(report["items"][0]["dns_latency_during_generation"])
        self.assertNotIn("dns_latency_during_generation_any_item_exceeded_budget", report)

    @mock.patch("subprocess.run")
    def test_dns_during_generation_aggregates_across_items(self, subprocess_run):
        provider = FakeProvider(delay_seconds=0.1)
        corpus = {"id": "x", "version": 1, "items": [{"id": "a", "messages": [{"role": "user", "content": "hi"}]}]}
        report = self.module["run_benchmark"](
            provider, corpus, catalog=[], sample_dns_during_generation=True, dns_sample_interval_seconds=0.03,
        )
        self.assertIsNotNone(report["items"][0]["dns_latency_during_generation"])
        self.assertIn("dns_latency_during_generation_any_item_exceeded_budget", report)


class RealCapabilityCatalogTests(BenchmarkRunnerTestCase):
    def test_includes_all_registered_capabilities(self):
        catalog = self.module["real_capability_catalog"]()
        names = {entry["name"] for entry in catalog}
        self.assertEqual(names, {"system.health", "pihole.status", "pihole.summary"})

    def test_each_entry_has_an_argument_schema(self):
        catalog = self.module["real_capability_catalog"]()
        for entry in catalog:
            self.assertIn("argument_schema", entry)
            self.assertNotIn("side_effect", entry)  # RFC-0004: not exposed to the model


class BuildProviderTests(BenchmarkRunnerTestCase):
    def args(self, **overrides):
        base = {"provider": "llama-cpp", "model": None, "base_url": "http://127.0.0.1:8081"}
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_llama_cpp_provider(self):
        provider = self.module["build_provider"](self.args())
        self.assertIsInstance(provider, inference.LlamaCppProvider)

    def test_ollama_provider_with_model(self):
        provider = self.module["build_provider"](
            self.args(provider="ollama", model="qwen2.5:3b", base_url="http://127.0.0.1:11434")
        )
        self.assertIsInstance(provider, inference.OllamaProvider)
        self.assertEqual(provider.model, "qwen2.5:3b")

    def test_ollama_without_model_is_a_usage_error(self):
        with self.assertRaises(SystemExit):
            self.module["build_provider"](self.args(provider="ollama", model=None))


class StarterCorpusTests(unittest.TestCase):
    def test_is_well_formed_json_with_expected_shape(self):
        corpus = json.loads(CORPUS_PATH.read_text())
        self.assertEqual(corpus["id"], "starter")
        self.assertTrue(corpus["items"])
        for item in corpus["items"]:
            self.assertIn("id", item)
            self.assertIn("messages", item)

    @mock.patch("subprocess.run")
    def test_runs_end_to_end_against_a_fake_provider(self, subprocess_run):
        module = runpy.run_path(str(SCRIPT_PATH), run_name="not_main")
        corpus = json.loads(CORPUS_PATH.read_text())
        provider = FakeProvider(chunks=[{"kind": "token", "text": "sure, here's an answer"}, {"kind": "done"}])
        report = module["run_benchmark"](provider, corpus, catalog=[])
        self.assertEqual(len(report["items"]), len(corpus["items"]))


V1_CORPUS_PATH = ROOT / "scripts/benchmark-inference-corpus-v1.json"


class V1CorpusTests(unittest.TestCase):
    def corpus(self):
        return json.loads(V1_CORPUS_PATH.read_text())

    def test_is_well_formed_json_with_expected_shape(self):
        corpus = self.corpus()
        self.assertEqual(corpus["id"], "v1")
        self.assertTrue(corpus["items"])
        seen_ids = set()
        for item in corpus["items"]:
            self.assertIn("id", item)
            self.assertIn("messages", item)
            self.assertNotIn(item["id"], seen_ids, f"duplicate item id: {item['id']}")
            seen_ids.add(item["id"])

    def test_is_larger_than_the_starter_corpus(self):
        starter = json.loads(CORPUS_PATH.read_text())
        self.assertGreater(len(self.corpus()["items"]), len(starter["items"]))

    def test_covers_every_registered_capability_plus_negative_and_ambiguous_cases(self):
        corpus = self.corpus()
        expectations = [item.get("expected_capability") for item in corpus["items"]]
        # At least one item positively expects each real, registered
        # capability -- the corpus can't claim to evaluate a capability
        # it never actually exercises.
        self.assertIn("system.health", expectations)
        self.assertIn("pihole.status", expectations)
        self.assertIn("pihole.summary", expectations)
        # At least one item explicitly expects *no* proposal (distinct
        # from unscored/ambiguous items) -- the false sentinel this
        # corpus depends on to test unsupported/adversarial prompts.
        self.assertIn(False, expectations)
        # At least one item is deliberately left unscored (ambiguous).
        self.assertIn(None, expectations)

    def test_includes_multi_turn_items(self):
        corpus = self.corpus()
        multi_turn = [item for item in corpus["items"] if len(item["messages"]) > 1]
        self.assertTrue(multi_turn, "expected at least one multi-turn item")

    @mock.patch("subprocess.run")
    def test_runs_end_to_end_against_a_fake_provider(self, subprocess_run):
        module = runpy.run_path(str(SCRIPT_PATH), run_name="not_main")
        corpus = self.corpus()
        provider = FakeProvider(chunks=[{"kind": "token", "text": "a plausible answer"}, {"kind": "done"}])
        report = module["run_benchmark"](provider, corpus, catalog=[])
        self.assertEqual(len(report["items"]), len(corpus["items"]))

    @mock.patch("subprocess.run")
    def test_expected_capability_false_items_score_correct_against_a_silent_fake(self, subprocess_run):
        # A provider that never proposes anything should score "correct"
        # on every expected_capability: false item -- confirms the
        # sentinel is wired all the way from the corpus file through to
        # scoring, not just present in the JSON.
        module = runpy.run_path(str(SCRIPT_PATH), run_name="not_main")
        corpus = self.corpus()
        provider = FakeProvider(chunks=[{"kind": "token", "text": "a plausible answer"}, {"kind": "done"}])
        report = module["run_benchmark"](provider, corpus, catalog=[])
        false_expectation_ids = {
            item["id"] for item in corpus["items"] if item.get("expected_capability") is False
        }
        for result in report["items"]:
            if result["id"] in false_expectation_ids:
                self.assertTrue(result["capability_selection_correct"], result["id"])


if __name__ == "__main__":
    unittest.main()
