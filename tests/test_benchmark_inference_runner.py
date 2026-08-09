import json
import runpy
import sys
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
    def __init__(self, chunks=None, health=None, raise_error=None):
        self._chunks = chunks if chunks is not None else [{"kind": "done"}]
        self._health = health if health is not None else {"healthy": True, "model_name": "fake", "runtime_version": "0"}
        self._raise_error = raise_error
        self.last_capability_catalog = None

    def health(self):
        return self._health

    def generate(self, messages, capability_catalog=None, max_tokens=None, timeout_seconds=30, stream=True):
        self.last_capability_catalog = capability_catalog
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


if __name__ == "__main__":
    unittest.main()
