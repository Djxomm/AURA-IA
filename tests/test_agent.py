"""Pruebas de integración del motor de agente, confirmación de diffs y reversión."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from agente_ia.agent import AgentEngine, ApprovalDecision, ApprovalRegistry, PendingProposal
from agente_ia.config import AppSettings
from agente_ia.providers import LocalLLMClient
from agente_ia.storage import Storage


def test_agent_read_propose_approve_and_revert(tmp_path: Path) -> None:
    target = tmp_path / "calc.py"
    target.write_text("def sumar(a, b):\n    return a - b\n", encoding="utf-8")

    step = 0

    async def mock_ollama(request: httpx.Request) -> httpx.Response:
        nonlocal step
        step += 1
        if step == 1:
            msg = {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "c1", "function": {"name": "read_file", "arguments": {"path": "calc.py"}}}],
                },
                "done": True,
                "eval_count": 10,
                "eval_duration": 200_000_000,
            }
        elif step == 2:
            msg = {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "c2",
                            "function": {
                                "name": "edit_file",
                                "arguments": {
                                    "path": "calc.py",
                                    "old_text": "return a - b",
                                    "new_text": "return a + b",
                                    "reason": "Corregir signo en sumar()",
                                },
                            },
                        }
                    ],
                },
                "done": True,
                "eval_count": 15,
                "eval_duration": 300_000_000,
            }
        else:
            msg = {
                "message": {"role": "assistant", "content": "Se corrigió la función `sumar`."},
                "done": True,
                "eval_count": 12,
                "eval_duration": 200_000_000,
            }
        return httpx.Response(200, text=json.dumps(msg) + "\n")

    async def run() -> None:
        storage = Storage(":memory:")
        client = LocalLLMClient(transport=httpx.MockTransport(mock_ollama))
        registry = ApprovalRegistry()
        engine = AgentEngine(storage, client, registry)
        settings = AppSettings(workspace_path=str(tmp_path), provider="ollama", model="qwen2.5-coder:1.5b")
        session = storage.create_session(
            title="Test",
            workspace_path=str(tmp_path),
            provider="ollama",
            model="qwen2.5-coder:1.5b",
        )

        events: list[tuple[str, dict[str, Any]]] = []
        disk_while_pending: list[str] = []

        async def emit(name: str, data: dict[str, Any]) -> None:
            events.append((name, data))

        async def approve(proposal: PendingProposal) -> ApprovalDecision:
            # Mientras espera aprobación, el disco aún no se ha modificado
            disk_while_pending.append(target.read_text(encoding="utf-8"))
            assert proposal.added_lines == 1
            assert proposal.removed_lines == 1
            return ApprovalDecision(approved=True)

        result = await engine.run_turn(
            session_id=session["id"],
            user_message="Corrige sumar en calc.py",
            settings=settings,
            emit=emit,
            approval_handler=approve,
        )
        assert result["status"] == "done"
        assert disk_while_pending == ["def sumar(a, b):\n    return a - b\n"]
        assert "return a + b" in target.read_text(encoding="utf-8")

        changes = storage.list_changes(session["id"])
        assert len(changes) == 1
        assert changes[0]["status"] == "applied"

        reverted = engine.revert_change(changes[0]["id"])
        assert reverted["status"] == "reverted"
        assert target.read_text(encoding="utf-8") == "def sumar(a, b):\n    return a - b\n"

    asyncio.run(run())


def test_agent_reject_with_feedback_then_retry_and_cancel(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("X = 1\n", encoding="utf-8")

    observed_feedback: list[str] = []
    call_idx = 0

    async def mock_ollama(request: httpx.Request) -> httpx.Response:
        nonlocal call_idx
        call_idx += 1
        body = json.loads(request.content.decode("utf-8"))
        if call_idx == 1:
            msg = {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "e1",
                            "function": {
                                "name": "edit_file",
                                "arguments": {
                                    "path": "app.py",
                                    "old_text": "X = 1",
                                    "new_text": "X = 2",
                                    "reason": "Subir X a 2",
                                },
                            },
                        }
                    ],
                },
                "done": True,
            }
        elif call_idx == 2:
            # Verificar que el feedback de rechazo llegó al LLM
            last_tool = [m for m in body["messages"] if m.get("role") == "tool"][-1]["content"]
            observed_feedback.append(last_tool)
            msg = {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "e2",
                            "function": {
                                "name": "edit_file",
                                "arguments": {
                                    "path": "app.py",
                                    "old_text": "X = 1",
                                    "new_text": "X = 10",
                                    "reason": "Cambiar X a 10 según feedback",
                                },
                            },
                        }
                    ],
                },
                "done": True,
            }
        else:
            msg = {"message": {"role": "assistant", "content": "Actualizado a 10."}, "done": True}
        return httpx.Response(200, text=json.dumps(msg) + "\n")

    async def run() -> None:
        storage = Storage(":memory:")
        client = LocalLLMClient(transport=httpx.MockTransport(mock_ollama))
        registry = ApprovalRegistry()
        engine = AgentEngine(storage, client, registry)
        settings = AppSettings(workspace_path=str(tmp_path), provider="ollama", model="qwen2.5-coder:0.5b")
        session = storage.create_session(
            title="Reject test",
            workspace_path=str(tmp_path),
            provider="ollama",
            model="qwen2.5-coder:0.5b",
        )

        decisions = iter(
            [
                ApprovalDecision(approved=False, feedback="Pon X = 10 en lugar de 2"),
                ApprovalDecision(approved=True),
            ]
        )

        async def handler(_: PendingProposal) -> ApprovalDecision:
            return next(decisions)

        res = await engine.run_turn(
            session_id=session["id"],
            user_message="Cambia X",
            settings=settings,
            approval_handler=handler,
        )
        assert res["status"] == "done"
        assert "Pon X = 10 en lugar de 2" in observed_feedback[0]
        assert target.read_text(encoding="utf-8") == "X = 10\n"

        # Cancelación limpia antes de comenzar
        ev = asyncio.Event()
        ev.set()
        res_cancel = await engine.run_turn(
            session_id=session["id"],
            user_message="Otro",
            settings=settings,
            cancel_event=ev,
        )
        assert res_cancel["status"] == "cancelled"

    asyncio.run(run())
