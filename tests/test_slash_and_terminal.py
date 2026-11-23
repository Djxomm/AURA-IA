"""Pruebas de la paleta de comandos `/`, menciones `@`, habilidades (/rea, /impeccable, /blender) y terminal integrada."""

from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow

from agente_ia.config import AppSettings
from agente_ia.native_terminal import AuraTerminalPanel
from agente_ia.skills import SkillStore
from agente_ia.slash_palette import (
    SlashPopup,
    build_slash_catalog,
    filter_slash_entries,
    list_workspace_mentions,
    resolve_slash_command,
)


def _seed_skill(store: SkillStore, folder: Path, name: str, desc: str) -> str:
    sk_dir = folder / name
    sk_dir.mkdir(parents=True, exist_ok=True)
    (sk_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\nInstrucciones de prueba.\n",
        encoding="utf-8",
    )
    return store.install_bundled(folder, name)


def test_slash_catalog_includes_dynamic_skills_and_aliases(tmp_path: Path):
    store = SkillStore(tmp_path / "skills")
    bundle = tmp_path / "bundle"
    rea_id = _seed_skill(store, bundle, "reverse-engineer-anything", "Ingeniería inversa avanzada")
    imp_id = _seed_skill(store, bundle, "impeccable", "Diseño y pulido UI profesional")
    bld_id = _seed_skill(store, bundle, "blender-3d", "Animación y render 3D en Blender 5")

    catalog = build_slash_catalog(store)
    cmds = {e.command for e in catalog}
    assert {"/rea", "/reverse-engineer-anything", "/impeccable", "/impecable", "/blender", "/blender-3d", "/terminal", "/powershell", "/cmd", "/imagen", "/web"} <= cmds

    r_rea = resolve_slash_command("/rea analiza app.exe", store)
    assert r_rea["type"] == "invoke_skill" and r_rea["skill_id"] == rea_id and "app.exe" in r_rea["prompt"]

    r_imp = resolve_slash_command("/impecable mejora el contraste de login.html", store)
    assert r_imp["type"] == "invoke_skill" and r_imp["skill_id"] == imp_id

    r_bld = resolve_slash_command("/blender crea una cámara orbital", store)
    assert r_bld["type"] == "invoke_skill" and r_bld["skill_id"] == bld_id

    assert resolve_slash_command("/terminal dir", store) == {"type": "open_terminal", "shell": "powershell", "command": "dir"}
    assert resolve_slash_command("/powershell Get-Date", store) == {"type": "open_terminal", "shell": "powershell", "command": "Get-Date"}
    assert resolve_slash_command("/powershell externo", store) == {"type": "external_shell", "shell": "powershell"}
    assert resolve_slash_command("/cmd echo hola", store) == {"type": "open_terminal", "shell": "cmd", "command": "echo hola"}
    assert resolve_slash_command("/cmd externo", store) == {"type": "external_shell", "shell": "cmd"}
    assert resolve_slash_command("hola sin barra", store) is None

    filtered = filter_slash_entries(catalog, "/pow")
    assert filtered and filtered[0].command == "/powershell"


def test_workspace_at_mentions_and_slash_popup_selection(tmp_path: Path):
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "panel.py").write_text("# ui\n", encoding="utf-8")

    mentions = list_workspace_mentions(str(tmp_path), "pan")
    assert len(mentions) == 1 and mentions[0].command == "@ui/panel.py"

    app = QApplication.instance() or QApplication([])
    popup = SlashPopup()
    chosen = []
    popup.entry_chosen.connect(chosen.append)
    popup.set_entries(mentions)
    assert popup.accept_current() is True
    assert len(chosen) == 1 and chosen[0].payload["path"] == "ui/panel.py"
    popup.close()
    popup.deleteLater()
    app.processEvents()


def test_integrated_terminal_runs_cmd_powershell_and_python_and_blocks_destructive(tmp_path: Path):
    app = QApplication.instance() or QApplication([])

    class DummyStore:
        def __init__(self, ws: Path) -> None:
            self._s = AppSettings(workspace_path=str(ws))

        def get_settings(self) -> AppSettings:
            return self._s

    owner = QMainWindow()
    owner.store = DummyStore(tmp_path)
    panel = AuraTerminalPanel(owner, tmp_path)

    # Bloquea comandos destructivos del SO
    assert panel.execute("format C:", shell="cmd") is False
    assert "Bloqueado" in panel.console.toPlainText()

    # Ejecuta código Python real dentro de la terminal integrada
    assert panel.execute("print('TERMINAL_AURA_OK_777')", shell="python") is True
    for _ in range(150):
        app.processEvents()
        if "TERMINAL_AURA_OK_777" in panel.console.toPlainText() and panel.run_btn.isEnabled():
            break
        QTest.qWait(30)
    assert "TERMINAL_AURA_OK_777" in panel.console.toPlainText()
    assert "Código de salida: 0" in panel.console.toPlainText()

    # Ejecuta CMD real dentro de la terminal integrada
    assert panel.execute("echo CMD_AURA_OK", shell="cmd") is True
    for _ in range(150):
        app.processEvents()
        if "CMD_AURA_OK" in panel.console.toPlainText() and panel.run_btn.isEnabled():
            break
        QTest.qWait(30)
    assert "CMD_AURA_OK" in panel.console.toPlainText()

    # Botón "Enviar salida a AURA para reparar" emite el texto al chat
    sent = []
    panel.send_to_chat_requested.connect(sent.append)
    panel._emit_send_to_chat()
    assert sent and "CMD_AURA_OK" in sent[0]

    panel.close()
    panel.deleteLater()
    owner.close()
    owner.deleteLater()
    app.processEvents()
