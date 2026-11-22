"""Pruebas del modo constructor y reparador autónomo (run_project_action, run_command y auto-reparación)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from agente_ia.agent import AgentEngine, ApprovalDecision, ApprovalRegistry
from agente_ia.command_exec import validate_command
from agente_ia.config import AppSettings
from agente_ia.project_actions import requested_actions
from agente_ia.providers import LocalLLMClient
from agente_ia.storage import Storage
from agente_ia.tools import EXEC_TOOLS, build_system_prompt, parse_xml_tool_calls
from agente_ia.workspace import WorkspaceError


def test_parse_xml_and_bare_json_exec_tools():
    xml = '<tool_call>{"name": "run_project_action", "arguments": {"action": "test", "path": "app.py"}}</tool_call>'
    _, calls = parse_xml_tool_calls(xml)
    assert len(calls) == 1 and calls[0]["name"] == "run_project_action"

    bare = '{"name": "run_command", "arguments": {"command": "python -m py_compile app.py"}}'
    _, calls2 = parse_xml_tool_calls(bare)
    assert len(calls2) == 1 and calls2[0]["name"] == "run_command"
    assert "run_project_action" in EXEC_TOOLS and "run_command" in EXEC_TOOLS


def test_validate_command_blocks_destructive_os_actions():
    assert validate_command("python -m pytest -q") == "python -m pytest -q"
    for bad in ("", "format C:", "diskpart", "shutdown /s /t 0", "rm -rf /", "del /s /q C:\\Windows\\*"):
        with pytest.raises(WorkspaceError):
            validate_command(bad)


def test_requested_actions_routes_compound_repair_and_compile_to_agent():
    assert requested_actions("compila y ejecuta main.py") == ["build", "run"]
    assert requested_actions("prueba main.py") == ["test"]
    assert requested_actions("compila y corrige los errores de main.py") == []
    assert requested_actions("repara app.py y compila") == []
    assert requested_actions("prueba tests y arregla lo que falle") == []


def test_autonomous_prompt_instructs_builder_repairer_role(tmp_path: Path):
    prompt = build_system_prompt(str(tmp_path), include_xml_protocol=True, autonomous=True)
    assert "constructora y reparadora" in prompt.lower()
    assert "run_project_action" in prompt
    assert "run_command" in prompt


def test_autonomous_builder_edits_runs_test_repairs_and_verifies_in_one_turn(tmp_path: Path):
    """Simula un ciclo real completo en 1 sola orden: leer -> correr prueba fallida -> editar -> re-probar OK."""
    (tmp_path / "calc.py").write_text("def sumar(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "test_calc.py").write_text(
        "from calc import sumar\n\ndef test_sumar():\n    assert sumar(2, 3) == 5\n",
        encoding="utf-8",
    )

    scripted_replies = [
        '<tool_call>{"name": "run_project_action", "arguments": {"action": "test", "reason": "Ejecutar pruebas iniciales"}}</tool_call>',
        '<tool_call>{"name": "edit_file", "arguments": {"path": "calc.py", "old_text": "return a - b", "new_text": "return a + b", "reason": "Corregir suma"}}</tool_call>',
        '<tool_call>{"name": "run_project_action", "arguments": {"action": "test", "reason": "Verificar reparación"}}</tool_call>',
        '<tool_call>{"name": "run_command", "arguments": {"command": "python -m py_compile calc.py", "reason": "Comprobar compilación"}}</tool_call>',
        "Reparé `calc.py` (`a - b` -> `a + b`), volví a ejecutar las pruebas y salieron con código 0.",
    ]
    step_idx = 0
    seen_tool_outputs: list[str] = []
    approval_prompts = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal step_idx
        body = json.loads(request.content.decode("utf-8"))
        for m in body.get("messages", []):
            txt = str(m.get("content") or "")
            if "Resultado real de " in txt and txt not in seen_tool_outputs:
                seen_tool_outputs.append(txt)
        reply = scripted_replies[min(step_idx, len(scripted_replies) - 1)]
        step_idx += 1
        return httpx.Response(200, text=json.dumps({"message": {"role": "assistant", "content": reply}, "done": True}) + "\n")

    async def scenario() -> None:
        nonlocal approval_prompts
        store = Storage(":memory:")
        client = LocalLLMClient(transport=httpx.MockTransport(respond))
        engine = AgentEngine(store, client, ApprovalRegistry())
        session = store.create_session(title="Auto", workspace_path=str(tmp_path), provider="ollama", model="test")

        async def should_not_prompt(proposal):
            nonlocal approval_prompts
            approval_prompts += 1
            return ApprovalDecision(approved=False)

        events: list[tuple[str, dict]] = []

        async def emit(kind: str, payload: dict) -> None:
            events.append((kind, payload))

        settings = AppSettings(
            workspace_path=str(tmp_path),
            provider="ollama",
            model="test",
            tool_mode="xml",
            autonomous_mode=True,
        )
        result = await engine.run_turn(
            session_id=session["id"],
            user_message="Repara calc.py, corre las pruebas y verifica la compilación",
            settings=settings,
            emit=emit,
            approval_handler=should_not_prompt,
        )
        assert result["status"] == "done"
        assert approval_prompts == 0, "En modo autónomo no debe bloquear pidiendo confirmación por editar o probar"
        assert "return a + b" in (tmp_path / "calc.py").read_text(encoding="utf-8")
        # Primera ejecución falló (salida 1), segunda ejecución pasó (salida 0)
        assert any("código de salida 1" in out for out in seen_tool_outputs)
        assert any("código de salida 0" in out for out in seen_tool_outputs)
        # Historial completo registrado para deshacer con 1 clic
        changes = store.list_changes(session["id"])
        assert len(changes) == 1 and changes[0]["status"] == "applied"
        engine.revert_change(changes[0]["id"])
        assert "return a - b" in (tmp_path / "calc.py").read_text(encoding="utf-8")

    asyncio.run(scenario())


def test_delete_file_still_requires_confirmation_even_in_autonomous_mode(tmp_path: Path):
    (tmp_path / "dato.txt").write_text("importante", encoding="utf-8")
    replies = [
        '<tool_call>{"name": "delete_file", "arguments": {"path": "dato.txt", "reason": "Limpiar"}}</tool_call>',
        "Cancelado porque lo rechazaste.",
    ]
    idx = 0
    prompted = 0

    async def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal idx
        r = replies[min(idx, len(replies) - 1)]
        idx += 1
        return httpx.Response(200, text=json.dumps({"message": {"role": "assistant", "content": r}, "done": True}) + "\n")

    async def scenario() -> None:
        nonlocal prompted
        store = Storage(":memory:")
        engine = AgentEngine(store, LocalLLMClient(transport=httpx.MockTransport(respond)), ApprovalRegistry())
        session = store.create_session(title="Del", workspace_path=str(tmp_path), provider="ollama", model="test")

        async def reject_delete(proposal):
            nonlocal prompted
            prompted += 1
            assert proposal.action == "delete"
            return ApprovalDecision(approved=False, feedback="No borres archivos")

        settings = AppSettings(workspace_path=str(tmp_path), provider="ollama", model="test", tool_mode="xml", autonomous_mode=True)
        await engine.run_turn(session_id=session["id"], user_message="Borra dato.txt", settings=settings, approval_handler=reject_delete)
        assert prompted == 1
        assert (tmp_path / "dato.txt").is_file()

    asyncio.run(scenario())


def test_manual_mode_asks_approval_for_run_command(tmp_path: Path):
    replies = [
        '<tool_call>{"name": "run_command", "arguments": {"command": "python -c \\"print(42)\\"", "reason": "Probar"}}</tool_call>',
        "Listo.",
    ]
    idx = 0
    asked = []

    async def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal idx
        r = replies[min(idx, len(replies) - 1)]
        idx += 1
        return httpx.Response(200, text=json.dumps({"message": {"role": "assistant", "content": r}, "done": True}) + "\n")

    async def scenario() -> None:
        store = Storage(":memory:")
        engine = AgentEngine(store, LocalLLMClient(transport=httpx.MockTransport(respond)), ApprovalRegistry())
        session = store.create_session(title="Manual", workspace_path=str(tmp_path), provider="ollama", model="test")

        async def approve_exec(proposal):
            asked.append(proposal.action)
            return ApprovalDecision(approved=True)

        settings = AppSettings(workspace_path=str(tmp_path), provider="ollama", model="test", tool_mode="xml", autonomous_mode=False)
        res = await engine.run_turn(session_id=session["id"], user_message="Ejecuta prueba", settings=settings, approval_handler=approve_exec)
        assert res["status"] == "done"
        assert asked == ["exec"]

    asyncio.run(scenario())
