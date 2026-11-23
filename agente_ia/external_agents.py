"""Detección y lanzador de agentes CLI / Apps externas (Claude Code, Codex CLI, OpenCode,
Qwen Code, Copilot CLI, Cline, Ollama y Terminal) dentro de la carpeta del proyecto AuraX."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExternalAgentSpec:
    id: str
    name: str
    subtitle: str
    executables: tuple[str, ...]
    ollama_launch_name: str = ""
    install_hint: str = ""
    category: str = "Agente CLI"


AGENT_CATALOG: tuple[ExternalAgentSpec, ...] = (
    ExternalAgentSpec(
        id="claude-code",
        name="Claude Code",
        subtitle="Agente de programación, compilación y edición autónoma en terminal",
        executables=("claude", "claude.cmd", "claude.exe", "claude.ps1"),
        ollama_launch_name="claude",
        install_hint="npm i -g @anthropic-ai/claude-code  (o vía Ollama Apps)",
    ),
    ExternalAgentSpec(
        id="codex",
        name="Codex CLI",
        subtitle="Agente CLI estilo Codex para compilar, depurar y aplicar parches",
        executables=("codex", "codex.cmd", "codex.exe", "codex.ps1"),
        ollama_launch_name="codex",
        install_hint="npm i -g @openai/codex  (o vía Ollama Apps)",
    ),
    ExternalAgentSpec(
        id="opencode",
        name="OpenCode",
        subtitle="Agente de código abierto compatible con modelos locales y Ollama",
        executables=("opencode", "opencode.cmd", "opencode.exe", "opencode.ps1"),
        ollama_launch_name="opencode",
        install_hint="npm i -g opencode-ai",
    ),
    ExternalAgentSpec(
        id="qwen-code",
        name="Qwen Code",
        subtitle="CLI especializado en arquitectura, compilación y edición multiarchivo",
        executables=("qwen", "qwen-code", "qwen.cmd", "qwen.ps1"),
        ollama_launch_name="",
        install_hint="npm i -g @qwen-code/qwen-code",
    ),
    ExternalAgentSpec(
        id="copilot",
        name="Copilot CLI",
        subtitle="Asistente CLI para comandos, depuración y flujo de desarrollo",
        executables=("copilot", "copilot.exe", "copilot.cmd"),
        ollama_launch_name="",
        install_hint="winget install GitHub.Copilot",
    ),
    ExternalAgentSpec(
        id="cline",
        name="Cline CLI",
        subtitle="Agente autónomo orientado a tareas y compilaciones en proyecto",
        executables=("cline", "cline.cmd", "cline.ps1"),
        ollama_launch_name="",
        install_hint="npm i -g cline",
    ),
    ExternalAgentSpec(
        id="ollama",
        name="Ollama (Apps / Local)",
        subtitle="Motor local de modelos y lanzador de Apps CLI en tu equipo",
        executables=("ollama", "ollama.exe"),
        ollama_launch_name="",
        install_hint="https://ollama.com/download",
        category="Motor local",
    ),
    ExternalAgentSpec(
        id="powershell",
        name="PowerShell",
        subtitle="Terminal PowerShell abierta directamente en la carpeta del proyecto",
        executables=("pwsh", "powershell", "powershell.exe"),
        ollama_launch_name="",
        install_hint="Incluido en Windows",
        category="Terminal",
    ),
    ExternalAgentSpec(
        id="cmd",
        name="CMD · Terminal",
        subtitle="Símbolo del sistema clásico abierto en la carpeta del proyecto",
        executables=("cmd", "cmd.exe"),
        ollama_launch_name="",
        install_hint="Incluido en Windows",
        category="Terminal",
    ),
)


def _extra_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    home = Path.home()
    candidates = [
        home / "AppData" / "Roaming" / "npm",
        home / "AppData" / "Local" / "Programs" / "Ollama",
        home / "AppData" / "Local" / "GitHubCopilotCLI",
        home / ".local" / "bin",
        home / ".cargo" / "bin",
    ]
    for c in candidates:
        if c.is_dir():
            dirs.append(c)
    return dirs


def find_executable(names: tuple[str, ...]) -> str | None:
    extra = os.pathsep.join(str(d) for d in _extra_search_dirs())
    search_path = os.environ.get("PATH", "")
    if extra:
        search_path = search_path + os.pathsep + extra
    for name in names:
        hit = shutil.which(name, path=search_path)
        if hit:
            return str(Path(hit))
    for d in _extra_search_dirs():
        for name in names:
            cand = d / name
            if cand.is_file():
                return str(cand)
    return None


def ollama_status(timeout: float = 1.2) -> dict[str, Any]:
    exe = find_executable(("ollama", "ollama.exe"))
    models: list[str] = []
    running = False
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                running = True
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                for item in data.get("models") or []:
                    name = str(item.get("name") or "").strip()
                    if name:
                        models.append(name)
    except Exception:
        running = False
    return {"installed": bool(exe), "executable": exe or "", "running": running, "models": models}


def detect_external_agents() -> list[dict[str, Any]]:
    oll = ollama_status()
    rows: list[dict[str, Any]] = []
    for spec in AGENT_CATALOG:
        exe = find_executable(spec.executables)
        via_ollama = bool(oll["installed"] and spec.ollama_launch_name)
        rows.append(
            {
                "id": spec.id,
                "name": spec.name,
                "subtitle": spec.subtitle,
                "category": spec.category,
                "installed": bool(exe),
                "executable": exe or "",
                "can_launch_via_ollama": via_ollama,
                "ollama_launch_name": spec.ollama_launch_name,
                "install_hint": spec.install_hint,
            }
        )
    return rows


def _ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def build_launch_command(
    agent_id: str,
    workspace_path: str | Path,
    prompt: str = "",
    *,
    use_ollama: bool = False,
) -> tuple[list[str], str]:
    """Construye la invocación segura de terminal externa dentro de `workspace_path`."""
    ws = Path(workspace_path).resolve()
    if not ws.is_dir():
        raise ValueError(f"La carpeta del proyecto no existe: {ws}")
    spec = next((s for s in AGENT_CATALOG if s.id == agent_id), None)
    if spec is None:
        raise ValueError(f"Agente externo desconocido: {agent_id}")

    if spec.id == "cmd":
        cmd = ["cmd.exe", "/k", f"cd /d {ws}"]
        return cmd, f"cmd /k cd /d {ws}"

    ps_exe = find_executable(("pwsh", "powershell", "powershell.exe")) or "powershell.exe"
    if spec.id == "powershell":
        script = f"Set-Location -LiteralPath {_ps_quote(str(ws))}"
        return [ps_exe, "-NoExit", "-Command", script], script

    oll = find_executable(("ollama", "ollama.exe"))
    exe = find_executable(spec.executables)

    if use_ollama and spec.ollama_launch_name and oll:
        inner = f"& {_ps_quote(oll)} launch {spec.ollama_launch_name}"
    elif exe:
        clean_prompt = str(prompt or "").strip()
        if clean_prompt and spec.id in {"claude-code", "codex", "opencode", "qwen-code"}:
            inner = f"& {_ps_quote(exe)} {_ps_quote(clean_prompt)}"
        else:
            inner = f"& {_ps_quote(exe)}"
    elif spec.ollama_launch_name and oll:
        inner = f"& {_ps_quote(oll)} launch {spec.ollama_launch_name}"
    else:
        raise ValueError(
            f"{spec.name} no está instalado en este equipo.\nInstálalo con: {spec.install_hint}"
        )

    script = f"Set-Location -LiteralPath {_ps_quote(str(ws))}; {inner}"
    return [ps_exe, "-NoExit", "-Command", script], script


def launch_external_agent(
    agent_id: str,
    workspace_path: str | Path,
    prompt: str = "",
    *,
    use_ollama: bool = False,
) -> dict[str, Any]:
    argv, display = build_launch_command(agent_id, workspace_path, prompt=prompt, use_ollama=use_ollama)
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    proc = subprocess.Popen(argv, cwd=str(Path(workspace_path).resolve()), creationflags=flags)
    return {"ok": True, "agent_id": agent_id, "pid": proc.pid, "command": display}


def open_external_agents_dialog(parent, workspace_path: str | Path, initial_prompt: str = "") -> None:
    """Abre un selector visual estilo Apps (Claude Code, Codex CLI, OpenCode, Qwen Code, Copilot, Ollama...)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QDialog,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )

    dlg = QDialog(parent)
    dlg.setWindowTitle("AURA · Apps y Agentes CLI en el proyecto")
    dlg.resize(760, 560)
    dlg.setStyleSheet(
        "QDialog{background:#0b1626;color:#ecf5ff;}"
        "QWidget#agentCard{background:#12233a;border:1px solid #2b486b;border-radius:12px;}"
        "QWidget#agentCard:hover{border-color:#53c9f5;}"
        "QPushButton{background:#1d4ed8;color:#ffffff;border:none;border-radius:8px;padding:7px 14px;font-weight:600;}"
        "QPushButton:hover{background:#2563eb;}"
        "QPushButton:disabled{background:#1f2e42;color:#7d93ad;}"
        "QLineEdit{background:#0f1d31;color:#f1f5f9;border:1px solid #305075;border-radius:8px;padding:8px;}"
    )
    root_layout = QVBoxLayout(dlg)
    head = QLabel("Apps y Agentes CLI (estilo Codex / Claude Code / Ollama Apps)")
    head.setStyleSheet("font-size:18px;font-weight:700;color:#f8fafc;")
    root_layout.addWidget(head)

    ws_label = QLabel(f"Proyecto activo: {Path(workspace_path).resolve()}")
    ws_label.setWordWrap(True)
    ws_label.setStyleSheet("color:#93c5fd;")
    root_layout.addWidget(ws_label)

    oll = ollama_status()
    oll_chk = QCheckBox(
        f"Lanzar mediante Ollama local (`ollama launch ...`)"
        + (f" · {len(oll['models'])} modelo(s) en Ollama" if oll["running"] else " · Ollama instalado" if oll["installed"] else " · Ollama no detectado")
    )
    oll_chk.setEnabled(bool(oll["installed"]))
    oll_chk.setChecked(False)
    root_layout.addWidget(oll_chk)

    prompt_box = QLineEdit(initial_prompt)
    prompt_box.setPlaceholderText("Instrucción inicial opcional para el agente CLI (ej.: compila el proyecto y corrige errores)…")
    root_layout.addWidget(prompt_box)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
    grid_host = QWidget()
    grid = QGridLayout(grid_host)
    grid.setSpacing(12)

    agents = detect_external_agents()
    for idx, ag in enumerate(agents):
        card = QWidget()
        card.setObjectName("agentCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        top = QHBoxLayout()
        title = QLabel(ag["name"])
        title.setStyleSheet("font-size:14px;font-weight:700;color:#f8fafc;")
        badge_txt = "Instalado" if ag["installed"] else ("Vía Ollama" if ag["can_launch_via_ollama"] else "No instalado")
        badge_bg = "#065f46" if ag["installed"] else ("#1e40af" if ag["can_launch_via_ollama"] else "#334155")
        badge = QLabel(badge_txt)
        badge.setStyleSheet(f"background:{badge_bg};color:#f8fafc;border-radius:10px;padding:2px 9px;font-size:11px;font-weight:600;")
        top.addWidget(title, 1)
        top.addWidget(badge)
        cl.addLayout(top)

        sub = QLabel(ag["subtitle"])
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#cbd5e1;font-size:12px;")
        cl.addWidget(sub)

        if not ag["installed"]:
            hint = QLabel(f"Instalar: {ag['install_hint']}")
            hint.setWordWrap(True)
            hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            hint.setStyleSheet("color:#94a3b8;font-size:11px;font-family:Consolas;")
            cl.addWidget(hint)

        btn = QPushButton("Abrir en proyecto" if (ag["installed"] or ag["can_launch_via_ollama"]) else "No instalado")
        btn.setEnabled(bool(ag["installed"] or ag["can_launch_via_ollama"]))

        def _fire(_checked=False, aid=ag["id"]):
            try:
                res = launch_external_agent(aid, workspace_path, prompt=prompt_box.text().strip(), use_ollama=oll_chk.isChecked())
                if hasattr(parent, "status"):
                    parent.status.setText(f"Agente externo abierto: {aid} (PID {res['pid']})")
                dlg.accept()
            except Exception as exc:
                QMessageBox.warning(dlg, "AURA · Agente externo", str(exc))

        btn.clicked.connect(_fire)
        cl.addWidget(btn)
        grid.addWidget(card, idx // 2, idx % 2)

    scroll.setWidget(grid_host)
    root_layout.addWidget(scroll, 1)

    close_btn = QPushButton("Cerrar")
    close_btn.setStyleSheet("background:#334155;color:#f8fafc;")
    close_btn.clicked.connect(dlg.reject)
    root_layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
    dlg.exec()
