"""Pruebas unitarias de proveedores locales (Ollama, llama.cpp/KoboldCpp y LM Studio)."""

from __future__ import annotations

import asyncio
import json

import httpx

from agente_ia.config import AppSettings
from agente_ia.providers import LocalLLMClient


def test_ollama_stream_native_tools_and_legacy_options() -> None:
    captured_payloads: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            body = json.loads(request.content.decode("utf-8"))
            captured_payloads.append(body)
            lines = [
                json.dumps({"message": {"role": "assistant", "content": "Voy a revisar "}, "done": False}),
                json.dumps(
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {"id": "tc_1", "function": {"name": "read_file", "arguments": {"path": "app.py"}}}
                            ],
                        },
                        "done": True,
                        "eval_count": 18,
                        "eval_duration": 1_000_000_000,
                    }
                ),
            ]
            return httpx.Response(200, text="\n".join(lines) + "\n")
        return httpx.Response(404)

    async def run() -> None:
        client = LocalLLMClient(transport=httpx.MockTransport(handler))
        settings = AppSettings(provider="ollama", model="qwen2.5-coder:1.5b", hardware_profile="legacy_i5_1gb")
        tokens: list[str] = []

        async def on_tok(t: str) -> None:
            tokens.append(t)

        resp = await client.stream_chat(
            settings=settings,
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hola"}],
            tools=[{"type": "function", "function": {"name": "read_file"}}],
            on_token=on_tok,
        )
        assert "".join(tokens) == "Voy a revisar "
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "read_file"
        assert resp.tool_calls[0].arguments == {"path": "app.py"}
        assert resp.tok_per_sec == 18.0
        opts = captured_payloads[0]["options"]
        assert opts["num_ctx"] == settings.num_ctx
        assert opts["num_batch"] == 128
        assert opts["num_thread"] == 2
        assert opts["num_gpu"] == 0
        assert opts["num_predict"] == 512

    asyncio.run(run())


def test_ollama_auto_fallback_to_xml_on_400() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = json.loads(request.content.decode("utf-8"))
        if calls == 1:
            assert "tools" in body
            return httpx.Response(400, json={"error": "model does not support tools"})
        assert "tools" not in body
        assert "<tool_call>" in body["messages"][0]["content"]
        ndjson = json.dumps(
            {
                "message": {
                    "role": "assistant",
                    "content": 'Revisando...\n<tool_call>{"name": "list_files", "arguments": {"path": "."}}</tool_call>',
                },
                "done": True,
                "eval_count": 12,
                "eval_duration": 500_000_000,
            }
        )
        return httpx.Response(200, text=ndjson + "\n")

    async def run() -> None:
        client = LocalLLMClient(transport=httpx.MockTransport(handler))
        settings = AppSettings(provider="ollama", model="qwen2.5-coder:0.5b", tool_mode="auto")
        resp = await client.stream_chat(
            settings=settings,
            messages=[{"role": "system", "content": "Base"}, {"role": "user", "content": "lista"}],
            tools=[{"type": "function", "function": {"name": "list_files"}}],
        )
        assert calls == 2
        assert resp.used_tool_mode == "xml"
        assert resp.content == "Revisando..."
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "list_files"
        assert resp.tool_calls[0].arguments == {"path": "."}

    asyncio.run(run())


def test_llamacpp_and_lmstudio_fragmented_sse_and_detect() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:0.5b", "size": 417333248}]})
        if request.url.path == "/v1/models":
            if request.url.port == 8080:
                return httpx.Response(200, json={"data": [{"id": "qwen2.5-coder-1.5b.gguf"}]})
            return httpx.Response(503)
        if request.url.path == "/v1/chat/completions":
            sse_lines = [
                'data: {"choices":[{"delta":{"content":"Listo. "}}]}',
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"read_file","arguments":"{\\"path\\": "}}]}}]}',
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"main.py\\"}"}}]}}]}',
                "data: [DONE]",
            ]
            return httpx.Response(200, text="\n".join(sse_lines) + "\n")
        return httpx.Response(404)

    async def run() -> None:
        client = LocalLLMClient(transport=httpx.MockTransport(handler))
        statuses = await client.detect_providers(
            "http://127.0.0.1:11434",
            "http://127.0.0.1:8080/v1",
            "http://127.0.0.1:1234/v1",
        )
        assert statuses["ollama"].online is True
        assert statuses["ollama"].models[0]["size_mb"] == 398
        assert statuses["llamacpp"].online is True
        assert statuses["lmstudio"].online is False

        settings = AppSettings(provider="llamacpp", model="qwen2.5-coder-1.5b.gguf")
        resp = await client.stream_chat(
            settings=settings,
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "lee"}],
            tools=[{"type": "function", "function": {"name": "read_file"}}],
        )
        assert resp.content == "Listo."
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].id == "c1"
        assert resp.tool_calls[0].name == "read_file"
        assert resp.tool_calls[0].arguments == {"path": "main.py"}

    asyncio.run(run())
