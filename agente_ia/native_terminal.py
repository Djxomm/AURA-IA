"""Terminal interactiva integrada de AURA (PowerShell, CMD y Python) acoplable al escritorio."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .command_exec import validate_command
from .workspace import WorkspaceError


class _HistoryLineEdit(QLineEdit):
    """Línea de comandos con historial navegable con flechas arriba/abajo."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._history: list[str] = []
        self._pos = 0

    def push_history(self, command: str) -> None:
        clean = command.strip()
        if clean and (not self._history or self._history[-1] != clean):
            self._history.append(clean)
        self._pos = len(self._history)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Up and self._history:
            self._pos = max(0, self._pos - 1)
            self.setText(self._history[self._pos])
            event.accept()
            return
        if event.key() == Qt.Key.Key_Down and self._history:
            self._pos = min(len(self._history), self._pos + 1)
            self.setText(self._history[self._pos] if self._pos < len(self._history) else "")
            event.accept()
            return
        super().keyPressEvent(event)


def launch_external_shell(shell: str, workspace_path: str) -> None:
    """Abre una ventana externa real de PowerShell o CMD en la carpeta del proyecto."""
    cwd = Path(workspace_path).resolve()
    if not cwd.is_dir():
        raise WorkspaceError(f"La carpeta del proyecto no existe: {cwd}")
    kind = shell.strip().lower()
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    if kind in ("powershell", "ps", "pwsh"):
        exe = shutil.which("pwsh.exe") or shutil.which("powershell.exe") or "powershell.exe"
        subprocess.Popen([exe, "-NoExit", "-NoProfile"], cwd=str(cwd), creationflags=flags)
    elif kind == "cmd":
        exe = shutil.which("cmd.exe") or "cmd.exe"
        subprocess.Popen([exe, "/K"], cwd=str(cwd), creationflags=flags)
    else:
        raise WorkspaceError(f"Intérprete externo no soportado: {shell}")


class AuraTerminalPanel(QWidget):
    """Panel acoplable de terminal propia de AURA con salida en vivo, PowerShell, CMD y Python."""

    send_to_chat_requested = Signal(str)

    def __init__(self, owner, runtime: Path) -> None:
        super().__init__(owner)
        self.owner = owner
        self.runtime = Path(runtime).resolve()
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)
        self._last_command = ""
        self._last_chunks: list[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Terminal · AURA")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        header.addWidget(title, 1)

        self.shell_box = QComboBox(self)
        self.shell_box.addItem("PowerShell", "powershell")
        self.shell_box.addItem("CMD", "cmd")
        self.shell_box.addItem("Python", "python")
        self.shell_box.setToolTip("Intérprete para ejecutar comandos o código dentro del proyecto.")
        header.addWidget(self.shell_box)

        btn_ps = QPushButton("PowerShell externo", self)
        btn_ps.setToolTip("Abrir una ventana independiente de PowerShell en la carpeta del proyecto.")
        btn_ps.clicked.connect(lambda: self.open_external("powershell"))
        header.addWidget(btn_ps)

        btn_cmd = QPushButton("CMD externo", self)
        btn_cmd.setToolTip("Abrir una ventana independiente de Símbolo del sistema (CMD) en el proyecto.")
        btn_cmd.clicked.connect(lambda: self.open_external("cmd"))
        header.addWidget(btn_cmd)
        root.addLayout(header)

        self.cwd_label = QLabel(self._workspace_path(), self)
        self.cwd_label.setWordWrap(True)
        self.cwd_label.setStyleSheet("color:#93abc8;font-size:11px;")
        root.addWidget(self.cwd_label)

        self.console = QPlainTextEdit(self)
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(3000)
        self.console.setFont(QFont("Consolas", 10))
        self.console.setStyleSheet(
            "background:#07111e;color:#e6f1ff;border:1px solid #243b57;border-radius:8px;"
            "font-family:Consolas;font-size:12px;padding:6px;"
        )
        self.console.setPlaceholderText(
            "Terminal integrada de AURA lista. Escribe un comando PowerShell, CMD o código Python abajo y pulsa Enter…"
        )
        root.addWidget(self.console, 1)

        cmd_row = QHBoxLayout()
        self.command_input = _HistoryLineEdit(self)
        self.command_input.setPlaceholderText("Ej: python -m pytest -q  ·  git status  ·  dir  ·  blender --version")
        self.command_input.returnPressed.connect(self.run_current)
        cmd_row.addWidget(self.command_input, 1)

        self.run_btn = QPushButton("Ejecutar", self)
        self.run_btn.clicked.connect(self.run_current)
        cmd_row.addWidget(self.run_btn)

        self.stop_btn = QPushButton("Detener", self)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_process)
        cmd_row.addWidget(self.stop_btn)
        root.addLayout(cmd_row)

        foot = QHBoxLayout()
        btn_clear = QPushButton("Limpiar", self)
        btn_clear.clicked.connect(self.console.clear)
        foot.addWidget(btn_clear)

        btn_send = QPushButton("Enviar salida a AURA para reparar", self)
        btn_send.setToolTip("Envía la última salida o error de la terminal al chat de AURA.")
        btn_send.clicked.connect(self._emit_send_to_chat)
        foot.addWidget(btn_send)
        foot.addStretch(1)
        root.addLayout(foot)

    def _workspace_path(self) -> str:
        return str(Path(self.owner.store.get_settings().workspace_path).resolve())

    def refresh_workspace(self) -> None:
        self.cwd_label.setText(self._workspace_path())

    def _build_process_env(self) -> QProcessEnvironment:
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        prefixes: list[str] = []
        for rel in (
            "herramientas/python",
            "herramientas/python/Scripts",
            "herramientas/node",
            "herramientas/php",
            "herramientas/jdk/bin",
            "herramientas/w64devkit/bin",
            "herramientas/inno",
        ):
            cand = self.runtime / rel
            if cand.is_dir():
                prefixes.append(str(cand))
        for blender_root in (Path(r"C:\Program Files\Blender Foundation"), Path(r"C:\Program Files (x86)\Blender Foundation")):
            if blender_root.is_dir():
                for cand in sorted(blender_root.glob("Blender*"), reverse=True):
                    if (cand / "blender.exe").is_file():
                        prefixes.append(str(cand))
                        break
        if prefixes:
            env.insert("PATH", os.pathsep.join(prefixes) + os.pathsep + env.value("PATH"))
        return env

    def _resolve_python(self) -> str:
        bundled = self.runtime / "herramientas/python/python.exe"
        if bundled.is_file():
            return str(bundled)
        if not getattr(sys, "frozen", False) and Path(sys.executable).is_file():
            return str(Path(sys.executable).resolve())
        return shutil.which("python") or "python"

    def run_current(self) -> None:
        cmd = self.command_input.text().strip()
        if not cmd:
            return
        shell = str(self.shell_box.currentData() or "powershell")
        self.command_input.clear()
        self.execute(cmd, shell=shell)

    def execute(self, command: str, *, shell: str | None = None) -> bool:
        """Ejecuta un comando dentro de la terminal integrada con streaming en vivo."""
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.console.appendPlainText("[AURA] Ya hay un proceso en ejecución. Pulsa Detener primero.")
            return False
        try:
            clean = validate_command(command)
        except WorkspaceError as exc:
            self.console.appendPlainText(f"[Bloqueado] {exc}")
            return False

        chosen = (shell or str(self.shell_box.currentData() or "powershell")).lower()
        idx = self.shell_box.findData(chosen)
        if idx >= 0:
            self.shell_box.setCurrentIndex(idx)

        cwd = self._workspace_path()
        self.refresh_workspace()
        self.command_input.push_history(clean)
        self._last_command = clean
        self._last_chunks = []

        if chosen == "cmd":
            program = shutil.which("cmd.exe") or "cmd.exe"
            args = ["/C", clean]
            prefix = "CMD>"
        elif chosen == "python":
            program = self._resolve_python()
            args = ["-c", clean]
            prefix = "PY>"
        else:
            program = shutil.which("powershell.exe") or shutil.which("powershell") or "powershell.exe"
            args = ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", clean]
            prefix = "PS>"

        self.console.appendPlainText(f"\n[{cwd}] {prefix} {clean}")
        self.process.setProcessEnvironment(self._build_process_env())
        self.process.setWorkingDirectory(cwd)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.process.start(program, args)
        return True

    def stop_process(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            pid = self.process.processId()
            if os.name == "nt" and pid:
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=4,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except Exception:
                    self.process.kill()
            else:
                self.process.kill()
            self.console.appendPlainText("[AURA] Proceso detenido por el usuario.")

    def open_external(self, shell: str) -> None:
        try:
            launch_external_shell(shell, self._workspace_path())
            self.console.appendPlainText(f"[AURA] Ventana externa de {shell.upper()} abierta en {self._workspace_path()}.")
        except Exception as exc:
            QMessageBox.warning(self, "Terminal · AURA", str(exc))

    def _on_output(self) -> None:
        raw = bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
        if raw:
            self._last_chunks.append(raw)
            if len(self._last_chunks) > 200:
                self._last_chunks = self._last_chunks[-200:]
            self.console.appendPlainText(raw.rstrip("\r\n"))

    def _on_finished(self, code: int, _status) -> None:
        self._on_output()
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.console.appendPlainText(f"[Código de salida: {code}]")

    def _on_error(self, _error) -> None:
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.console.appendPlainText(f"[Error de proceso] {self.process.errorString()}")

    def _emit_send_to_chat(self) -> None:
        tail = "".join(self._last_chunks)[-2400:].strip() or self.console.toPlainText()[-2400:].strip()
        if not tail:
            return
        cmd_hdr = f"Comando ejecutado: `{self._last_command}`\n" if self._last_command else ""
        msg = f"Analiza esta salida real de la terminal de AURA y corrige cualquier error:\n{cmd_hdr}```text\n{tail}\n```"
        self.send_to_chat_requested.emit(msg)
