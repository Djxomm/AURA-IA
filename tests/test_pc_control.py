"""Pruebas de inspección/control de PC Windows y aprobación inteligente por riesgo en modo autónomo."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from agente_ia.agent import AgentEngine, ApprovalDecision, ApprovalRegistry
from agente_ia.command_exec import command_requires_approval
from agente_ia.config import AppSettings
from agente_ia.pc_control import describe_pc_action, pc_inspect
from agente_ia.providers import LocalLLMClient
from agente_ia.skills import SkillStore
from agente_ia.slash_palette import build_slash_catalog, resolve_slash_command
from agente_ia.storage import Storage
from agente_ia.workspace import SafeWorkspace, WorkspaceError


def test_pc_inspect_reads_real_system_processes_and_windows(tmp_path: Path):
    ws = SafeWorkspace(str(tmp_path))
    info = pc_inspect(ws, "system_info")
    assert info["action"] == "system_info"
    assert info["physical_cores"] >= 1
    assert info["ram_total_gb"] > 0

    procs = pc_inspect(ws, "list_processes", limit=10)
    assert procs["action"] == "list_processes"
    assert procs["count"] >= 1

    wins = pc_inspect(ws, "list_windows", limit=15)
    assert wins["action"] == "list_windows"
    assert isinstance(wins["windows"], list)

    with pytest.raises(WorkspaceError):
        pc_inspect(ws, "accion_invalida")


def test_pc_control_blocks_dangerous_apps_and_protected_processes():
    for bad_app in ("format", "diskpart.exe", "shutdown", "regedit"):
        with pytest.raises(WorkspaceError):
            describe_pc_action("open_app", {"target": bad_app})

    for critical in ("explorer.exe", "lsass.exe", "csrss.exe", "aura-nativa.exe"):
        with pytest.raises(WorkspaceError):
            describe_pc_action("close_process", {"target": critical})

    with pytest.raises(WorkspaceError):
        describe_pc_action("mouse_click", {"x": -5, "y": 10})

    desc = describe_pc_action("open_app", {"target": "notepad"})
    assert "notepad" in desc.lower()


def test_command_requires_approval_separates_safe_from_risky():
    assert command_requires_approval("python -m pytest -q") is False
    assert command_requires_approval("python -m py_compile app.py") is False
    assert command_requires_approval("git status") is False

    for risky in (
        "pip install requests",
        "npm install vite",
        "winget install BlenderFoundation.Blender",
        "taskkill /IM notepad.exe /F",
        "Remove-Item -Recurse temp",
        "git push origin main",
    ):
        assert command_requires_approval(risky) is True, f"Debió requerir aprobación: {risky}"


def test_pc_slash_command_works_with_and_without_skill(tmp_path: Path):
    # Sin skill instalada todavía usa el fallback integrado con auto_autonomous
    res_plain = resolve_slash_command("/pc revisa cuanta RAM queda", None)
    assert res_plain["type"] == "prompt"
    assert res_plain.get("auto_autonomous") is True
    assert "pc_inspect" in res_plain["prompt"]

    # Con skill control-pc instalada la activa automáticamente
    store = SkillStore(tmp_path / "skills")
    bundle = tmp_path / "bundle"
    (bundle / "control-pc").mkdir(parents=True)
    (bundle / "control-pc" / "SKILL.md").write_text(
        "---\nname: control-pc\ndescription: Control seguro de PC\n---\n\n# Control PC\n",
        encoding="utf-8",
    )
    sid = store.install_bundled(bundle, "control-pc")
    cmds = {e.command for e in build_slash_catalog(store)}
    assert "/pc" in cmds
    res_skill = resolve_slash_command("/pc abre la calculadora", store)
    assert res_skill["type"] == "invoke_skill"
    assert res_skill["skill_id"] == sid
    assert res_skill.get("auto_autonomous") is True


def test_autonomous_smart_approval_runs_safe_auto_and_prompts_only_risky_or_pc(tmp_path: Path):
    """En modo autónomo:
    - pc_inspect, edit_file y run_command seguro corren sin molestar al usuario (0 prompts).
    - run_command sensible (pip install) y pc_control (open_app) SIEMPRE piden aprobación de 1 clic.
    """
    (tmp_path / "app.py").write_text("VALOR = 1\n", encoding="utf-8")

    replies = [
        '<tool_call>{"name": "pc_inspect", "arguments": {"action": "system_info"}}</tool_call>',
        '<tool_call>{"name": "edit_file", "arguments": {"path": "app.py", "old_text": "VALOR = 1", "new_text": "VALOR = 2", "reason": "Actualizar valor"}}</tool_call>',
        '<tool_call>{"name": "run_command", "arguments": {"command": "python -c \\"print(\'AUTO_OK\')\\"", "reason": "Verificar"}}</tool_call>',
        '<tool_call>{"name": "run_command", "arguments": {"command": "pip install paquete-inexistente-prueba", "reason": "Instalar dependencia"}}</tool_call>',
        '<tool_call>{"name": "pc_control", "arguments": {"action": "open_app", "target": "notepad", "reason": "Abrir Bloc de notas"}}</tool_call>',
        "Inspeccioné la PC, actualicé app.py, verifiqué la ejecución automática y respeté tus rechazos en pip install y Bloc de notas.",
    ]
    idx = 0
    seen_tools: list[str] = []
    prompts: list[tuple[str, str]] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal idx
        body = json.loads(request.content.decode("utf-8"))
        for m in body.get("messages", []):
            txt = str(m.get("content") or "")
            if txt and txt not in seen_tools:
                seen_tools.append(txt)
        reply = replies[min(idx, len(replies) - 1)]
        idx += 1
        return httpx.Response(200, text=json.dumps({"message": {"role": "assistant", "content": reply}, "done": True}) + "\n")

    async def scenario() -> None:
        store = Storage(":memory:")
        engine = AgentEngine(store, LocalLLMClient(transport=httpx.MockTransport(respond)), ApprovalRegistry())
        session = store.create_session(title="PC Auto", workspace_path=str(tmp_path), provider="ollama", model="test")

        async def handle_approval(proposal):
            prompts.append((proposal.action, proposal.proposed_content or ""))
            # Rechazamos para verificar que se bloquea sin ejecutar pip ni abrir notepad real
            return ApprovalDecision(approved=False, feedback="No autorizado en prueba")

        settings = AppSettings(
            workspace_path=str(tmp_path),
            provider="ollama",
            model="test",
            tool_mode="xml",
            autonomous_mode=True,
        )
        res = await engine.run_turn(
            session_id=session["id"],
            user_message="Revisa la PC, edita app.py, prueba y abre notepad",
            settings=settings,
            approval_handler=handle_approval,
        )
        assert res["status"] == "done"
        # Edit y run_command seguro corrieron automáticamente
        assert "VALOR = 2" in (tmp_path / "app.py").read_text(encoding="utf-8")
        assert any("AUTO_OK" in t for t in seen_tools)
        assert any("ram_total_gb" in t for t in seen_tools)
        # SOLO se pidió aprobación en pip install (exec) y en pc_control (open_app)
        assert len(prompts) == 2
        assert prompts[0][0] == "exec" and "pip install" in prompts[0][1]
        assert prompts[1][0] == "pc_control" and "notepad" in prompts[1][1].lower()

    asyncio.run(scenario())
