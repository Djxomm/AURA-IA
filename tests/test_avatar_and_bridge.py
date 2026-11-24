"""Pruebas unitarias para los avatares 3D animados (Lumen/Angel/Mateo/Zamara V8.2)
y el puente local OpenAI-compatible para Codex CLI y OpenCode con modelos AURA IA."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


def _qt_app():
    return QApplication.instance() or QApplication([])


def test_avatar_persona_resolution_and_3d_rendering():
    _qt_app()
    from agente_ia.avatar_3d import AvatarStageWidget, render_avatar_pixmap, resolve_avatar_persona

    assert resolve_avatar_persona("AURA-Lumen-2.0IB_V2-Q4_K_M.gguf") == "lumen"
    assert resolve_avatar_persona("AURA-ANGEL-5.6-Q4_K_M.gguf") == "angel"
    assert resolve_avatar_persona("AURA-MATEO-Pro-Q4_K_M.gguf") == "mateo"
    assert resolve_avatar_persona("AURA-Zamara-V8.2-E4B-Q4_K_M.gguf") == "zamara"
    assert resolve_avatar_persona("qwen2.5-coder-3b-instruct-q4_k_m.gguf") == "aura"

    for persona in ("lumen", "angel", "mateo", "zamara", "aura"):
        for state in ("idle", "thinking", "working", "speaking", "listening", "error"):
            pix = render_avatar_pixmap(persona, state, 1.25, 128, 140)
            assert not pix.isNull()
            assert pix.hasAlphaChannel()

    stage = AvatarStageWidget(compact=True)
    assert stage.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    stage.set_model("AURA-Zamara-V8.2-E4B-Q4_K_M.gguf", "AURA - Zamara V8.2")
    assert stage.persona == "zamara"
    stage.set_state("thinking")
    assert stage.state == "thinking"
    stage.close()
    stage.deleteLater()

    from agente_ia.avatar_3d import TransparentStartupSplash

    splash = TransparentStartupSplash(None, Path("agente_ia/static/assets"), "AURA-ANGEL-5.6-Q4_K_M.gguf")
    assert splash.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert splash.persona == "angel"
    snap = splash.grab()
    assert not snap.isNull()
    splash.release()


def test_codex_and_opencode_aura_local_bridge(tmp_path, monkeypatch):
    from agente_ia.external_agents import build_launch_command
    from agente_ia.local_openai_bridge import sync_codex_aura_profile, sync_opencode_aura_config

    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text('[user]\ntheme = "dark"\n', encoding="utf-8")

    cfg = sync_codex_aura_profile("http://127.0.0.1:11439/v1", "AURA-ANGEL-5.6-Q4_K_M", codex_home=codex_home)
    txt = cfg.read_text(encoding="utf-8")
    assert 'theme = "dark"' in txt
    assert "[model_providers.aura]" in txt
    assert 'base_url = "http://127.0.0.1:11439/v1"' in txt
    assert "[profiles.aura]" in txt
    assert 'model = "AURA-ANGEL-5.6-Q4_K_M"' in txt

    oc_cfg = sync_opencode_aura_config(tmp_path, "http://127.0.0.1:11439/v1", "AURA-MATEO-Pro", "AURA - MATEO Pro")
    oc_data = json.loads(oc_cfg.read_text(encoding="utf-8"))
    assert oc_data["model"] == "aura/AURA-MATEO-Pro"
    assert oc_data["provider"]["aura"]["options"]["baseURL"] == "http://127.0.0.1:11439/v1"

    fake_codex = tmp_path / "codex.exe"
    fake_codex.write_text("", encoding="utf-8")
    monkeypatch.setattr("agente_ia.external_agents.find_executable", lambda names: str(fake_codex) if "codex" in names else "powershell.exe")
    monkeypatch.setattr("agente_ia.local_openai_bridge.Path.home", classmethod(lambda cls: tmp_path))

    argv, display = build_launch_command(
        "codex",
        tmp_path,
        prompt="corrige el bug",
        aura_endpoint={"base_url": "http://127.0.0.1:11439/v1", "model_id": "AURA-ANGEL-5.6", "model_label": "AURA - ANGEL 5.6"},
    )
    assert "-p aura" in display
    assert "AURA_LOCAL_API_KEY" in display
    assert "corrige el bug" in display
