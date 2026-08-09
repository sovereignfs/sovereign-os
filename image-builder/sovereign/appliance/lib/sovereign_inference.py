import json
import time
import urllib.error
import urllib.request


# RFC-0002's Inference Provider Adapter contract, as a plain duck-typed
# interface (matching this codebase's existing style -- no ABC/Protocol
# machinery, no typing decorations, plain classes and dicts, same as
# sovereign_capabilities.py): any provider must offer
#
#   health() -> {"healthy": bool, "model_name": str | None,
#                "runtime_version": str | None}
#
#   generate(messages, capability_catalog=None, max_tokens=None,
#             timeout_seconds=30, stream=True) -> iterator of chunks
#
# Each streamed chunk is one of:
#   {"kind": "token", "text": str}
#   {"kind": "capability_proposal", "name": str, "arguments": dict}
#   {"kind": "usage", "prompt_tokens": int | None, "completion_tokens": int | None}
#   {"kind": "done"}
#   {"kind": "error", "code": str, "message": str}
#
# health() deliberately reports only what the runner itself can say about
# itself -- model digest/license/quantization identity is Sovereign Model
# Management's job (a separate future component, RFC-0002's "Sovereign
# Model Management" section), not the provider adapter's.

CHUNK_KINDS = {"token", "capability_proposal", "usage", "done", "error"}


def validate_chunk(chunk):
    # A generic structural sanity check any adapter's output can be run
    # through -- matches this project's standing "validate everything"
    # posture rather than trusting an adapter's output unchecked.
    if not isinstance(chunk, dict) or "kind" not in chunk:
        return False
    return chunk["kind"] in CHUNK_KINDS


class ProviderError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class LlamaCppProvider:
    # llama-server's OpenAI-compatible HTTP API
    # (docs/research/local-ai-options.md's cited server documentation).
    # Streaming uses the standard OpenAI chat-completions SSE shape
    # ("data: {...}\n\n" lines, terminated by "data: [DONE]\n\n"); tool
    # calls are requested and read non-streamed, since incremental
    # streamed tool-call argument reassembly is real production-adapter
    # work this benchmark harness does not need to measure structured-
    # output accuracy.
    def __init__(self, base_url="http://127.0.0.1:8081", request_timeout_seconds=60):
        self.base_url = base_url.rstrip("/")
        self.request_timeout_seconds = request_timeout_seconds

    def health(self):
        request = urllib.request.Request(f"{self.base_url}/health", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read(8192))
        except (urllib.error.URLError, OSError, ValueError):
            return {"healthy": False, "model_name": None, "runtime_version": None}
        return {
            "healthy": payload.get("status") == "ok",
            "model_name": None,
            "runtime_version": None,
        }

    def _post(self, body, stream):
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            return urllib.request.urlopen(request, timeout=self.request_timeout_seconds)  # noqa: S310
        except (urllib.error.URLError, OSError) as error:
            raise ProviderError("PROVIDER_UNREACHABLE", "Could not reach the inference provider") from error

    def generate(self, messages, capability_catalog=None, max_tokens=None, timeout_seconds=30, stream=True):
        body = {"messages": messages, "stream": stream}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if capability_catalog:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": entry["name"],
                        "description": entry.get("description", ""),
                        "parameters": entry["argument_schema"],
                    },
                }
                for entry in capability_catalog
            ]
        if stream:
            yield from self._generate_streaming(body)
        else:
            yield from self._generate_single_shot(body)

    def _generate_streaming(self, body):
        response = self._post(body, stream=True)
        try:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    yield {"kind": "done"}
                    return
                try:
                    event = json.loads(data)
                except ValueError:
                    continue
                choice = (event.get("choices") or [{}])[0]
                delta = choice.get("delta", {})
                content = delta.get("content")
                if content:
                    yield {"kind": "token", "text": content}
                usage = event.get("usage")
                if usage:
                    yield {
                        "kind": "usage",
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                    }
        finally:
            response.close()

    def _generate_single_shot(self, body):
        response = self._post(body, stream=False)
        try:
            payload = json.loads(response.read())
        finally:
            response.close()
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message", {})
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function", {})
            try:
                arguments = json.loads(function.get("arguments", "{}"))
            except ValueError:
                arguments = None
            yield {"kind": "capability_proposal", "name": function.get("name"), "arguments": arguments}
        if message.get("content"):
            yield {"kind": "token", "text": message["content"]}
        usage = payload.get("usage")
        if usage:
            yield {
                "kind": "usage",
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
            }
        yield {"kind": "done"}
