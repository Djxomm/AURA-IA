"""Pruebas reales de QbitX estilo Codex/Claude Code, Apps CLI externas, Globo AURAX y Gestor de Modelos."""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest


def _write_fake_gguf(path: Path, arch: str = "llama", name: str = "AURA - MATEO-Nano (desde 0)") -> None:
    def _str(s: str) -> bytes:
        b = s.encode("utf-8")
        return struct.pack("<Q", len(b)) + b

    kvs = [
        ("general.architecture", 8, _str(arch)),
        ("general.name", 8, _str(name)),
        (f"{arch}.block_count", 4, struct.pack("<I", 8)),
        (f"{arch}.context_length", 4, struct.pack("<I", 4096)),
    ]
    buf = bytearray(b"GGUF")
    buf += struct.pack("<IQQ", 3, 0, len(kvs))
    for k, kind, val in kvs:
        buf += _str(k) + struct.pack("<I", kind) + val
    buf += b"\x00" * 1024
    path.write_bytes(bytes(buf))


def test_external_agents_catalog_and_launch_commands(tmp_path):
    from agente_ia.external_agents import build_launch_command, detect_external_agents

    agents = detect_external_agents()
    ids = {a["id"] for a in agents}
    assert {"claude-code", "codex", "opencode", "qwen-code", "copilot", "ollama", "powershell", "cmd"} <= ids

    argv_ps, disp_ps = build_launch_command("powershell", tmp_path)
    assert "-NoExit" in argv_ps and str(tmp_path.resolve()) in disp_ps

    argv_cmd, disp_cmd = build_launch_command("cmd", tmp_path)
    assert argv_cmd[0].lower().endswith("cmd.exe") and "/k" in argv_cmd

    codex_entry = next(a for a in agents if a["id"] == "codex")
    assert codex_entry["name"].startswith("Codex CLI")
    if codex_entry["installed"]:
        argv_cx, disp_cx = build_launch_command("codex", tmp_path, prompt="compila")
        assert str(tmp_path.resolve()) in disp_cx and "compila" in disp_cx


def test_workspace_compile_action_works_for_any_model_in_active_workspace(tmp_path):
    from agente_ia.command_exec import execute_project_action
    from agente_ia.workspace import SafeWorkspace

    (tmp_path / "app.py").write_text("def suma(a, b):\n    return a + b\n", encoding="utf-8")
    ws = SafeWorkspace(str(tmp_path))
    res = execute_project_action(ws, None, "check", "app.py")
    assert res["ok"] is True and res["exit_code"] == 0


def test_qbitx_multi_toolchain_plans(tmp_path):
    from agente_ia.project_actions import choose_target, plan

    # 1. PyInstaller .spec
    spec_dir = tmp_path / "py_spec"
    spec_dir.mkdir()
    (spec_dir / "MiApp.spec").write_text("# spec", encoding="utf-8")
    tgt = choose_target(spec_dir, "compila")
    assert tgt is not None and tgt.name == "MiApp.spec"
    cmds = plan(tmp_path / "rt", spec_dir, tgt, "build")
    assert cmds and "PyInstaller" in cmds[0].arguments

    # 2. Android Gradle
    and_dir = tmp_path / "android_app"
    and_dir.mkdir()
    (and_dir / "gradlew.bat").write_text("@echo off\n", encoding="utf-8")
    assert choose_target(and_dir, "compila") is None
    cmds_and = plan(tmp_path / "rt", and_dir, None, "build")
    assert cmds_and and cmds_and[0].program.name == "gradlew.bat" and ":app:assembleDebug" in cmds_and[0].arguments

    # 3. Python tests/ sin archivo abierto
    py_dir = tmp_path / "py_tests"
    (py_dir / "tests").mkdir(parents=True)
    assert choose_target(py_dir, "prueba") is None
    cmds_py = plan(tmp_path / "rt", py_dir, None, "test")
    assert cmds_py and "pytest" in cmds_py[0].arguments


def test_task_coordinator_captures_real_error_for_codex_repair(tmp_path):
    from agente_ia.task_coordinator import TaskCoordinator

    coord = TaskCoordinator(tmp_path / "qbitx.db")
    state = coord.begin("s1", str(tmp_path), "compila main.py")
    coord.execution("s1", str(tmp_path), "build", "main.py", 1, output="SyntaxError: expected ':' on line 14")
    resumed = coord.begin("s1", str(tmp_path), "continúa")
    ctx = TaskCoordinator.context(resumed)
    assert "last_build_error" in ctx and "SyntaxError" in ctx


def test_model_manager_discovers_direct_gguf_and_supports_llama(tmp_path):
    from agente_ia.model_library import curate_proven_models, discover, model_info
    from agente_ia.native_models import profile

    nano = tmp_path / "AURA-MATEO-Nano-desde0-Q8_0.gguf"
    custom = tmp_path / "mi-modelo-personalizado.gguf"
    r1 = tmp_path / "AURA-ANGEL-5.6-R1-Q4_K_M.gguf"
    final_angel = tmp_path / "AURA-ANGEL-5.6-Q4_K_M.gguf"
    _write_fake_gguf(nano, "llama", "AURA - MATEO-Nano (desde 0)")
    _write_fake_gguf(custom, "llama", "Custom Local")
    _write_fake_gguf(r1, "qwen2", "AURA - ANGEL 5.6")
    _write_fake_gguf(final_angel, "qwen2", "AURA - ANGEL 5.6")

    found = discover([tmp_path])
    assert nano.resolve() in found and custom.resolve() in found

    arch_profile, info = profile(nano)
    assert arch_profile == "llama" and info["general.name"] == "AURA - MATEO-Nano (desde 0)"
    assert model_info(nano)["llama.block_count"] == 8

    curated = curate_proven_models(found, explicit_models=[custom])
    assert final_angel.resolve() in curated
    assert nano.resolve() in curated
    assert custom.resolve() in curated
    assert r1.resolve() not in curated


def test_slash_commands_for_external_agents_and_training():
    from agente_ia.slash_palette import resolve_slash_command

    assert resolve_slash_command("/agentes")["type"] == "open_external_agents"
    res_codex = resolve_slash_command("/codex compila el proyecto")
    assert res_codex == {"type": "launch_external_agent", "agent_id": "codex", "prompt": "compila el proyecto"}
    res_claude = resolve_slash_command("/claude-code arregla el build")
    assert res_claude == {"type": "launch_external_agent", "agent_id": "claude-code", "prompt": "arregla el build"}
    res_train = resolve_slash_command("/entrenar modelo desde cero")
    assert res_train["type"] == "prompt" and "LLaMA Pro" in res_train["prompt"]


def test_aurax_floating_instruction_bubble_sends_exact_user_words():
    from PySide6.QtWidgets import QApplication
    from agente_ia.floating_companion import FloatingCompanion

    app = QApplication.instance() or QApplication([])
    captured = []

    class FakeOwner:
        prefs = {"animations": False}
        aurax = None

        def save_pref(self, k, v):
            self.prefs[k] = v

        def send_from_aurax_bubble(self, text, **kwargs):
            captured.append((text, kwargs))

        def showNormal(self): ...
        def raise_(self): ...
        def activateWindow(self): ...
        def open_aurax(self): ...
        def toggle_dictation(self): ...
        def speak(self): ...

    comp = FloatingCompanion(FakeOwner())
    comp.bubble.editor.setPlainText("compila el proyecto y arregla el botón guardar")
    comp.bubble.submit()
    assert len(captured) == 1
    assert captured[0][0] == "compila el proyecto y arregla el botón guardar"
    assert captured[0][1]["autonomous"] is True
    comp.close()
    app.processEvents()
