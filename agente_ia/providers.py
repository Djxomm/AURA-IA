"""Cliente asíncrono para motores locales gratuitos: Ollama, llama.cpp/KoboldCpp y LM Studio."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

from .config import AppSettings
from .tools import COMPACT_TOOL_SUMMARY, parse_xml_tool_calls


OnTokenCallback = Callable[[str], Awaitable[None] | None]


@dataclass
class ToolCall:
    """Llamada a herramienta normalizada independiente del proveedor."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ProviderResponse:
    """Respuesta completa de un turno del modelo local con métricas de rendimiento."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_generated: int = 0
    elapsed_ms: int = 0
    tok_per_sec: float = 0.0
    used_tool_mode: str = "native"
    raw_content: str = ""


@dataclass
class ProviderStatus:
    """Estado de disponibilidad de un motor local y sus modelos cargados."""

    id: str
    name: str
    url: str
    online: bool
    models: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


class ProviderError(Exception):
    """Error de comunicación o respuesta de un motor LLM local."""


def _normalize_ollama_url(url: str) -> str:
    return url.strip().rstrip("/")


def _normalize_v1_url(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    if not cleaned.endswith("/v1"):
        cleaned = f"{cleaned}/v1"
    return cleaned


def _format_size_mb(size_bytes: int | float | None) -> int | None:
    if not size_bytes:
        return None
    return max(1, round(float(size_bytes) / (1024 * 1024)))


async def _maybe_call_on_token(cb: OnTokenCallback | None, token: str) -> None:
    if not cb or not token:
        return
    res = cb(token)
    if asyncio.iscoroutine(res):
        await res


def _is_tool_unsupported_status(status_code: int, body_text: str) -> bool:
    if status_code not in (400, 404, 422):
        return False
    low = body_text.lower()
    keywords = (
        "tool",
        "tools",
        "function",
        "not support",
        "unsupported",
        "invalid_request",
        "grammar",
    )
    return any(k in low for k in keywords) or status_code == 400


def _adapt_messages_for_xml(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepara mensajes para motores sin tool-calling nativo inyectando protocolo XML."""
    xml_suffix = (
        "\n\nCuando necesites usar una herramienta, responde ÚNICAMENTE con bloques:\n"
        '<tool_call>{"name": "read_file", "arguments": {"path": "app.py"}}</tool_call>\n'
        f"{COMPACT_TOOL_SUMMARY}\n"
        "Usa JSON válido dentro de <tool_call>...</tool_call>."
    )
    adapted: list[dict[str, Any]] = []
    for idx, msg in enumerate(messages):
        role = msg.get("role", "user")
        content = msg.get("content") or ""
        if idx == 0 and role == "system":
            if "<tool_call>" not in content:
                content = content + xml_suffix
            adapted.append({"role": "system", "content": content})
        elif role == "tool":
            tool_name = msg.get("name", "herramienta")
            adapted.append(
                {
                    "role": "user",
                    "content": f"[Resultado de {tool_name}]:\n{content}",
                }
            )
        elif role == "assistant" and msg.get("tool_calls"):
            calls = msg.get("tool_calls") or []
            calls_txt = "\n".join(
                f'<tool_call>{json.dumps({"name": c.get("function", {}).get("name", c.get("name", "")), "arguments": c.get("function", {}).get("arguments", c.get("arguments", {}))}, ensure_ascii=False)}</tool_call>'
                for c in calls
            )
            merged = f"{content}\n{calls_txt}".strip()
            adapted.append({"role": "assistant", "content": merged})
        else:
            adapted.append({"role": role, "content": content})
    return adapted


def _normalize_native_tool_calls(raw_calls: list[dict[str, Any]]) -> list[ToolCall]:
    parsed: list[ToolCall] = []
    for tc in raw_calls:
        fn = tc.get("function") or {}
        name = str(fn.get("name") or tc.get("name") or "").strip()
        if not name:
            continue
        raw_args = fn.get("arguments", tc.get("arguments", {}))
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}
        tc_id = str(tc.get("id") or f"call_{uuid.uuid4().hex[:10]}")
        parsed.append(ToolCall(id=tc_id, name=name, arguments=args))
    return parsed


class LocalLLMClient:
    """Cliente unificado para Ollama, llama.cpp/KoboldCpp y LM Studio."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, auth_provider=None) -> None:
        self._transport = transport
        self._auth_provider = auth_provider

    def _auth_headers(self, base):
        token = self._auth_provider(base) if self._auth_provider else "local"
        return {"Authorization": "Bearer " + token}

    def _client(self, *, streaming: bool = False) -> httpx.AsyncClient:
        timeout = (
            httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
            if streaming
            else httpx.Timeout(2.5)
        )
        kwargs: dict[str, Any] = {"timeout": timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def check_ollama(self, url: str) -> ProviderStatus:
        base = _normalize_ollama_url(url)
        try:
            async with self._client(streaming=False) as client:
                resp = await client.get(f"{base}/api/tags")
                resp.raise_for_status()
                data = resp.json()
            models: list[dict[str, Any]] = []
            for item in data.get("models", []):
                name = item.get("name") or item.get("model") or ""
                if not name:
                    continue
                models.append(
                    {
                        "id": name,
                        "name": name,
                        "size_mb": _format_size_mb(item.get("size")),
                    }
                )
            return ProviderStatus(
                id="ollama",
                name="Ollama",
                url=base,
                online=True,
                models=models,
            )
        except Exception as exc:
            return ProviderStatus(
                id="ollama",
                name="Ollama",
                url=base,
                online=False,
                error=str(exc),
            )

    async def check_openai_compat(self, provider_id: str, name: str, url: str) -> ProviderStatus:
        base = _normalize_v1_url(url)
        try:
            async with self._client(streaming=False) as client:
                resp = await client.get(
                    f"{base}/models",
                    headers=self._auth_headers(base),
                )
                resp.raise_for_status()
                data = resp.json()
            models: list[dict[str, Any]] = []
            for item in data.get("data", []):
                mid = item.get("id") or ""
                if not mid:
                    continue
                models.append({"id": mid, "name": mid, "size_mb": None})
            return ProviderStatus(
                id=provider_id,
                name=name,
                url=base,
                online=True,
                models=models,
            )
        except Exception as exc:
            return ProviderStatus(
                id=provider_id,
                name=name,
                url=base,
                online=False,
                error=str(exc),
            )

    async def detect_providers(
        self,
        ollama_url: str,
        llamacpp_url: str,
        lmstudio_url: str,
    ) -> dict[str, ProviderStatus]:
        ollama_res, llamacpp_res, lmstudio_res = await asyncio.gather(
            self.check_ollama(ollama_url),
            self.check_openai_compat("llamacpp", "llama.cpp / KoboldCpp", llamacpp_url),
            self.check_openai_compat("lmstudio", "LM Studio", lmstudio_url),
        )
        return {
            "ollama": ollama_res,
            "llamacpp": llamacpp_res,
            "lmstudio": lmstudio_res,
        }

    async def stream_chat(
        self,
        settings: AppSettings,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        on_token: OnTokenCallback | None = None,
    ) -> ProviderResponse:
        """Envía el turno al proveedor local seleccionado con fallback automático a XML."""
        mode = settings.tool_mode
        if mode == "xml":
            return await self._dispatch_once(
                settings,
                _adapt_messages_for_xml(messages),
                tools=None,
                used_mode="xml",
                on_token=on_token,
            )

        try:
            return await self._dispatch_once(
                settings,
                messages,
                tools=tools,
                used_mode="native",
                on_token=on_token,
            )
        except _ToolModeFallbackError:
            if mode == "native":
                raise ProviderError(
                    f"El modelo '{settings.model}' o servidor no soporta herramientas nativas en modo 'native'."
                )
            return await self._dispatch_once(
                settings,
                _adapt_messages_for_xml(messages),
                tools=None,
                used_mode="xml",
                on_token=on_token,
            )

    async def _dispatch_once(
        self,
        settings: AppSettings,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None,
        used_mode: str,
        on_token: OnTokenCallback | None,
    ) -> ProviderResponse:
        if settings.provider == "ollama":
            return await self._stream_ollama(
                settings, messages, tools=tools, used_mode=used_mode, on_token=on_token
            )
        base_url = settings.llamacpp_url if settings.provider == "llamacpp" else settings.lmstudio_url
        return await self._stream_openai_compat(
            settings,
            base_url,
            messages,
            tools=tools,
            used_mode=used_mode,
            on_token=on_token,
        )

    async def _stream_ollama(
        self,
        settings: AppSettings,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None,
        used_mode: str,
        on_token: OnTokenCallback | None,
    ) -> ProviderResponse:
        base = _normalize_ollama_url(settings.ollama_url)
        payload: dict[str, Any] = {
            "model": settings.model,
            "messages": messages,
            "stream": True,
            "keep_alive": "5m",
            "options": {
                "temperature": settings.temperature,
                "num_ctx": settings.num_ctx,
                "num_batch": settings.num_batch,
                "num_thread": settings.num_thread,
                "num_gpu": settings.num_gpu,
                "num_predict": settings.max_predict_tokens or -1,
            },
        }
        # Reserve room for input; requesting the full context as output made the
        # old backend crop prompts to 128 tokens and appear to hang.
        prompt_estimate = sum(len(str(m.get("content") or "")) for m in messages) // 2 + 12 * len(messages) + 64
        if tools:
            prompt_estimate += len(json.dumps(tools)) // 2
        available = settings.num_ctx - prompt_estimate - 64
        if available < 32:
            raise ProviderError("El contexto está lleno. Abre una conversación nueva, adjunta menos código o amplía el contexto en Modelos.")
        defaults = {"rapido": 256, "equilibrado": 512, "profundo": 2048}
        requested = settings.max_predict_tokens or defaults[settings.thinking_effort]
        payload["max_tokens"] = max(32, min(requested, available))
        if settings.reasoning_supported:
            payload["chat_template_kwargs"] = {"enable_thinking": settings.thinking_effort == "profundo"}
        if tools:
            payload["tools"] = tools

        started = time.perf_counter()
        content_chunks: list[str] = []
        raw_tool_calls: list[dict[str, Any]] = []
        eval_count = 0
        eval_duration_ns = 0

        try:
            async with self._client(streaming=True) as client:
                async with client.stream("POST", f"{base}/api/chat", json=payload) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", errors="replace")
                        if tools and _is_tool_unsupported_status(resp.status_code, body):
                            raise _ToolModeFallbackError(body)
                        raise ProviderError(f"Ollama respondió HTTP {resp.status_code}: {body[:400]}")

                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if chunk.get("error"):
                            err_msg = str(chunk["error"])
                            if tools and "tool" in err_msg.lower():
                                raise _ToolModeFallbackError(err_msg)
                            raise ProviderError(f"Ollama error: {err_msg}")

                        msg = chunk.get("message") or {}
                        delta = msg.get("content") or ""
                        if delta:
                            content_chunks.append(delta)
                            await _maybe_call_on_token(on_token, delta)
                        if msg.get("tool_calls"):
                            raw_tool_calls.extend(msg["tool_calls"])

                        if chunk.get("done"):
                            eval_count = int(chunk.get("eval_count") or 0)
                            eval_duration_ns = int(chunk.get("eval_duration") or 0)
        except (_ToolModeFallbackError, ProviderError):
            raise
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"No se pudo conectar con Ollama en {base}. Verifica que Ollama esté ejecutándose."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Error de red con Ollama: {exc}") from exc

        return _finalize_response(
            raw_text="".join(content_chunks),
            native_calls=_normalize_native_tool_calls(raw_tool_calls),
            started=started,
            eval_count=eval_count,
            eval_duration_ns=eval_duration_ns,
            used_mode=used_mode,
        )

    async def _stream_openai_compat(
        self,
        settings: AppSettings,
        raw_base_url: str,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None,
        used_mode: str,
        on_token: OnTokenCallback | None,
    ) -> ProviderResponse:
        base = _normalize_v1_url(raw_base_url)
        payload: dict[str, Any] = {
            "model": settings.model,
            "messages": messages,
            "temperature": settings.temperature,
            "stream": True,
            "cache_prompt": True,
        }
        # Reserve room for input; requesting the full context as output made the
        # old backend crop prompts to 128 tokens and appear to hang.
        prompt_estimate = sum(len(str(m.get("content") or "")) for m in messages) // 2 + 12 * len(messages) + 64
        if tools:
            prompt_estimate += len(json.dumps(tools)) // 2
        available = settings.num_ctx - prompt_estimate - 64
        if available < 32:
            raise ProviderError("El contexto está lleno. Abre una conversación nueva, adjunta menos código o amplía el contexto en Modelos.")
        defaults = {"rapido": 256, "equilibrado": 512, "profundo": 2048}
        requested = settings.max_predict_tokens or defaults[settings.thinking_effort]
        payload["max_tokens"] = max(32, min(requested, available))
        if settings.reasoning_supported:
            payload["chat_template_kwargs"] = {"enable_thinking": settings.thinking_effort == "profundo"}
        if tools:
            payload["tools"] = tools

        started = time.perf_counter()
        content_chunks: list[str] = []
        partial_calls: dict[int, dict[str, Any]] = {}
        token_chunks_count = 0

        try:
            async with self._client(streaming=True) as client:
                async with client.stream(
                    "POST",
                    f"{base}/chat/completions",
                    json=payload,
                    headers=self._auth_headers(base),
                ) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", errors="replace")
                        if tools and _is_tool_unsupported_status(resp.status_code, body):
                            raise _ToolModeFallbackError(body)
                        raise ProviderError(
                            f"El motor ({settings.provider}) respondió HTTP {resp.status_code}: {body[:400]}"
                        )

                    async for line in resp.aiter_lines():
                        stripped = line.strip()
                        if not stripped or not stripped.startswith("data:"):
                            continue
                        data_str = stripped[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        text_piece = delta.get("content") or ""
                        if text_piece:
                            token_chunks_count += 1
                            content_chunks.append(text_piece)
                            await _maybe_call_on_token(on_token, text_piece)

                        for tc_delta in delta.get("tool_calls") or []:
                            idx = int(tc_delta.get("index", 0))
                            entry = partial_calls.setdefault(
                                idx,
                                {"id": "", "function": {"name": "", "arguments": ""}},
                            )
                            if tc_delta.get("id"):
                                entry["id"] = tc_delta["id"]
                            fn_delta = tc_delta.get("function") or {}
                            if fn_delta.get("name"):
                                entry["function"]["name"] += fn_delta["name"]
                            if fn_delta.get("arguments"):
                                entry["function"]["arguments"] += fn_delta["arguments"]
        except (_ToolModeFallbackError, ProviderError):
            raise
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"No se pudo conectar con {settings.provider} en {base}. Inicia el servidor local primero."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Error de red con {settings.provider}: {exc}") from exc

        ordered_raw_calls = [partial_calls[i] for i in sorted(partial_calls)]
        return _finalize_response(
            raw_text="".join(content_chunks),
            native_calls=_normalize_native_tool_calls(ordered_raw_calls),
            started=started,
            eval_count=token_chunks_count,
            eval_duration_ns=0,
            used_mode=used_mode,
        )


class _ToolModeFallbackError(Exception):
    """Señal interna para reintentar sin parámetro tools usando protocolo XML."""


def _finalize_response(
    *,
    raw_text: str,
    native_calls: list[ToolCall],
    started: float,
    eval_count: int,
    eval_duration_ns: int,
    used_mode: str,
) -> ProviderResponse:
    elapsed_sec = max(0.001, time.perf_counter() - started)
    elapsed_ms = int(elapsed_sec * 1000)

    final_calls = native_calls
    clean_text = raw_text
    effective_mode = used_mode

    if not final_calls:
        stripped_text, xml_calls = parse_xml_tool_calls(raw_text)
        if xml_calls:
            clean_text = stripped_text
            effective_mode = "xml"
            final_calls = [
                ToolCall(id=c["id"], name=c["name"], arguments=c["arguments"])
                for c in xml_calls
            ]

    tokens_est = eval_count if eval_count > 0 else max(1, len(raw_text) // 4) if raw_text else 0
    if eval_duration_ns > 0 and eval_count > 0:
        tok_per_sec = round(eval_count / (eval_duration_ns / 1_000_000_000), 2)
    else:
        tok_per_sec = round(tokens_est / elapsed_sec, 2) if tokens_est else 0.0

    return ProviderResponse(
        content=clean_text.strip(),
        tool_calls=final_calls,
        tokens_generated=tokens_est,
        elapsed_ms=elapsed_ms,
        tok_per_sec=tok_per_sec,
        used_tool_mode=effective_mode,
        raw_content=raw_text,
    )
