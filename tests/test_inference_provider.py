import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "image-builder/sovereign/appliance/lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import sovereign_inference as inference  # noqa: E402


def sse_response(lines):
    response = mock.MagicMock()
    response.__iter__.return_value = iter([f"{line}\n".encode("utf-8") for line in lines])
    response.close = mock.MagicMock()
    return response


def json_response(payload):
    response = mock.MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.close = mock.MagicMock()
    return response


class ValidateChunkTests(unittest.TestCase):
    def test_accepts_known_kinds(self):
        for kind in inference.CHUNK_KINDS:
            self.assertTrue(inference.validate_chunk({"kind": kind}))

    def test_rejects_unknown_kind(self):
        self.assertFalse(inference.validate_chunk({"kind": "made_up"}))

    def test_rejects_non_dict(self):
        self.assertFalse(inference.validate_chunk("token"))

    def test_rejects_missing_kind(self):
        self.assertFalse(inference.validate_chunk({"text": "hi"}))


class HealthTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_healthy_reports_true(self, urlopen):
        # health() uses `with urlopen(...) as response:`, unlike _post()'s
        # callers -- the mock must configure __enter__ accordingly.
        urlopen.return_value.__enter__.return_value = json_response({"status": "ok"})
        provider = inference.LlamaCppProvider()
        self.assertEqual(provider.health()["healthy"], True)

    @mock.patch("urllib.request.urlopen")
    def test_unreachable_reports_false_not_raise(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("connection refused")
        provider = inference.LlamaCppProvider()
        result = provider.health()
        self.assertEqual(result["healthy"], False)


class StreamingGenerationTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_yields_tokens_in_order_then_done(self, urlopen):
        urlopen.return_value = sse_response([
            'data: {"choices":[{"delta":{"content":"Hel"}}]}',
            'data: {"choices":[{"delta":{"content":"lo"}}]}',
            'data: [DONE]',
        ])
        provider = inference.LlamaCppProvider()
        chunks = list(provider.generate([{"role": "user", "content": "hi"}]))
        self.assertEqual([c["kind"] for c in chunks], ["token", "token", "done"])
        self.assertEqual(chunks[0]["text"], "Hel")
        self.assertEqual(chunks[1]["text"], "lo")

    @mock.patch("urllib.request.urlopen")
    def test_emits_usage_chunk_when_present(self, urlopen):
        urlopen.return_value = sse_response([
            'data: {"choices":[{"delta":{"content":"hi"}}]}',
            'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":5,"completion_tokens":1}}',
            'data: [DONE]',
        ])
        provider = inference.LlamaCppProvider()
        chunks = list(provider.generate([{"role": "user", "content": "hi"}]))
        usage = [c for c in chunks if c["kind"] == "usage"]
        self.assertEqual(usage, [{"kind": "usage", "prompt_tokens": 5, "completion_tokens": 1}])

    @mock.patch("urllib.request.urlopen")
    def test_ignores_malformed_sse_lines(self, urlopen):
        urlopen.return_value = sse_response([
            'data: not valid json',
            'data: {"choices":[{"delta":{"content":"ok"}}]}',
            'data: [DONE]',
        ])
        provider = inference.LlamaCppProvider()
        chunks = list(provider.generate([{"role": "user", "content": "hi"}]))
        self.assertEqual([c["kind"] for c in chunks], ["token", "done"])

    @mock.patch("urllib.request.urlopen")
    def test_unreachable_raises_provider_error(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("connection refused")
        provider = inference.LlamaCppProvider()
        with self.assertRaises(inference.ProviderError) as caught:
            list(provider.generate([{"role": "user", "content": "hi"}]))
        self.assertEqual(caught.exception.code, "PROVIDER_UNREACHABLE")

    def test_streaming_with_capability_catalog_is_refused(self):
        # LlamaCppProvider cannot parse tool calls from a streamed
        # response -- silently dropping a real proposal would be exactly
        # the kind of surprising failure this project avoids elsewhere.
        # It must refuse loudly, and before ever making a request.
        provider = inference.LlamaCppProvider()
        catalog = [{"name": "system.health", "version": 1, "argument_schema": {}}]
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(inference.ProviderError) as caught:
                list(provider.generate([{"role": "user", "content": "hi"}], capability_catalog=catalog, stream=True))
            self.assertEqual(caught.exception.code, "STREAMING_WITH_TOOLS_UNSUPPORTED")
            urlopen.assert_not_called()


class SingleShotGenerationTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_capability_catalog_becomes_tools_in_request_body(self, urlopen):
        urlopen.return_value = json_response({"choices": [{"message": {"content": "ok"}}]})
        provider = inference.LlamaCppProvider()
        catalog = [{"name": "system.health", "version": 1, "argument_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}]
        list(provider.generate([{"role": "user", "content": "hi"}], capability_catalog=catalog, stream=False))
        request = urlopen.call_args[0][0]
        body = json.loads(request.data)
        self.assertEqual(body["tools"][0]["function"]["name"], "system.health")

    @mock.patch("urllib.request.urlopen")
    def test_yields_capability_proposal_from_tool_call(self, urlopen):
        urlopen.return_value = json_response({
            "choices": [{"message": {"tool_calls": [
                {"function": {"name": "system.health", "arguments": "{}"}},
            ]}}],
        })
        provider = inference.LlamaCppProvider()
        chunks = list(provider.generate([{"role": "user", "content": "hi"}], stream=False))
        proposals = [c for c in chunks if c["kind"] == "capability_proposal"]
        self.assertEqual(proposals, [{"kind": "capability_proposal", "name": "system.health", "arguments": {}}])

    @mock.patch("urllib.request.urlopen")
    def test_malformed_tool_call_arguments_do_not_crash(self, urlopen):
        urlopen.return_value = json_response({
            "choices": [{"message": {"tool_calls": [
                {"function": {"name": "system.health", "arguments": "not json"}},
            ]}}],
        })
        provider = inference.LlamaCppProvider()
        chunks = list(provider.generate([{"role": "user", "content": "hi"}], stream=False))
        proposals = [c for c in chunks if c["kind"] == "capability_proposal"]
        self.assertIsNone(proposals[0]["arguments"])

    @mock.patch("urllib.request.urlopen")
    def test_ends_with_done(self, urlopen):
        urlopen.return_value = json_response({
            "choices": [{"message": {"content": "hello"}}],
        })
        provider = inference.LlamaCppProvider()
        chunks = list(provider.generate([{"role": "user", "content": "hi"}], stream=False))
        self.assertEqual(chunks[-1], {"kind": "done"})


if __name__ == "__main__":
    unittest.main()
