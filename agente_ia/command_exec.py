"""Ejecución controlada de compilación, pruebas y comandos dentro del workspace de AURA."""

from __future__ import annotations

import asyncio
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .workspace import SafeWorkspace, WorkspaceError


VALID_PROJECT_ACTIONS = ("check", "test", "build", "run")
MAX_COMMAND_CHARS = 2000
MAX_OUTPUT_BYTES = 256 * 1024

_DANGEROUS_PATTERNS = (
    re.compile(r"(?i)\b(?:format|diskpart|bcdedit|cipher\s+/w|vssadmin\s+delete)\b"),
    re.compile(r"(?i)\b(?:shutdown|restart-computer|stop-computer|logoff)\b"),
    re.compile(r"(?i)\b(?:reg\s+(?:delete|add|import)|net\s+user|takeown|icacls\s+c:\\windows)\b"),
    re.compile(r"(?i)\brm\s+-[a-z]*r[a-z]*f[a-z]*\s+(?:/|c:\\|c:/|\$env:systemdrive)"),
    re.compile(r"(?i)\b(?:del|erase|rd|rmdir)\s+.*(?:/s|/q).*(?:c:\\windows|c:\\users|c:\\program|c:\\\s*$|c:\\\*)"),
    re.compile(r"(?i)\bremove-item\b.*(?:-recurse|-r).*(?:c:\\windows|c:\\users|c:\\program|c:\\\s*$|c:\\\*)"),
    re.compile(r"(?i)\b(?:mkfs|dd\s+if=|wmic\s+os\s+where)\b"),
)


def validate_command(command: str) -> str:
    """Valida que el comando no esté vacío ni contenga acciones destructivas del sistema."""
    text = str(command or "").strip()
    if not text:
        raise WorkspaceError("El comando está vacío.")
    if len(text) > MAX_COMMAND_CHARS:
        raise WorkspaceError(f"El comando supera el límite de {MAX_COMMAND_CHARS} caracteres.")
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(text):
            raise WorkspaceError(
                "Comando bloqueado por seguridad: afecta al sistema operativo o discos fuera del proyecto."
            )
    from .android_tools import android_command_policy
    if android_command_policy(text) == "blocked":
        raise WorkspaceError(
            "Comando Fastboot bloqueado por seguridad: borra particiones de calibración/IMEI (EFS/modemst/nvram). La modificación de bootloader, vbmeta, boot, recovery y ROMs sí está habilitada con aprobación de 1 clic."
        )
    return text


_APPROVAL_REQUIRED_PATTERNS = (
    re.compile(r"(?i)\b(?:pip|pip3|uv)\s+(?:install|uninstall)\b"),
    re.compile(r"(?i)\b(?:npm|pnpm|yarn)\s+(?:install|i|add|remove|uninstall)\b"),
    re.compile(r"(?i)\b(?:winget|choco|msiexec|scoop)\b"),
    re.compile(r"(?i)\b(?:taskkill|stop-process|kill)\b"),
    re.compile(r"(?i)\b(?:remove-item|rm\s+-|del\s+|erase\s+|rmdir|rd\s+)\b"),
    re.compile(r"(?i)\bgit\s+(?:push|reset\s+--hard|clean\s+-f)\b"),
)


def command_requires_approval(command: str) -> bool:
    """Devuelve True si el comando instala software, borra archivos, cierra procesos, altera remotos o modifica un dispositivo Android."""
    text = str(command or "").strip()
    if any(p.search(text) for p in _APPROVAL_REQUIRED_PATTERNS):
        return True
    from .android_tools import android_command_policy
    return android_command_policy(text) == "requires_approval"


def _build_env(runtime: Path | None) -> dict[str, str]:
    env = os.environ.copy()
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1", "FORCE_COLOR": "0"})
    env.pop("PYTHONPATH", None)
    env.pop("NODE_OPTIONS", None)
    prefixes: list[str] = []
    if runtime is not None:
        rt = Path(runtime).resolve()
        for rel in (
            "herramientas/python",
            "herramientas/python/Scripts",
            "herramientas/node",
            "herramientas/w64devkit/bin",
            "herramientas/inno",
            "herramientas/platform-tools",
        ):
            cand = rt / rel
            if cand.is_dir():
                prefixes.append(str(cand))
    if not prefixes and not getattr(sys, "frozen", False):
        py_dir = Path(sys.executable).resolve().parent
        if py_dir.is_dir():
            prefixes.append(str(py_dir))
    pkg_pt = Path(__file__).resolve().parent.parent / "runtime" / "herramientas" / "platform-tools"
    if pkg_pt.is_dir() and str(pkg_pt) not in prefixes:
        prefixes.append(str(pkg_pt))
    from .android_tools import find_android_sdk
    android_sdk = find_android_sdk()
    if android_sdk is not None:
        env.setdefault("ANDROID_HOME", str(android_sdk))
        env.setdefault("ANDROID_SDK_ROOT", str(android_sdk))
        sdk_pt = android_sdk / "platform-tools"
        if sdk_pt.is_dir() and str(sdk_pt) not in prefixes:
            prefixes.append(str(sdk_pt))
    for blender_root in (Path(r"C:\Program Files\Blender Foundation"), Path(r"C:\Program Files (x86)\Blender Foundation")):
        if blender_root.is_dir():
            for cand in sorted(blender_root.glob("Blender*"), reverse=True):
                if (cand / "blender.exe").is_file():
                    prefixes.append(str(cand))
                    break
    from .diagram_studio import find_kicad_cli
    kicad_info = find_kicad_cli(runtime)
    if kicad_info.get("bin_dir") and kicad_info["bin_dir"] not in prefixes:
        prefixes.append(str(kicad_info["bin_dir"]))
    if prefixes:
        env["PATH"] = os.pathsep.join(prefixes) + os.pathsep + env.get("PATH", "")
    return env


def _kill_process_tree(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except OSError:
            pass


def _run_subprocess_sync(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
    cancel_check: Callable[[], bool] | None = None,
    on_output: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    proc = subprocess.Popen(
        args,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    ch: queue.Queue[str | None] = queue.Queue(maxsize=256)
    lines: list[str] = []
    truncated = False

    def _reader() -> None:
        nonlocal truncated
        total = 0
        try:
            assert proc.stdout is not None
            while raw := proc.stdout.readline(4096):
                total += len(raw)
                if total > MAX_OUTPUT_BYTES:
                    truncated = True
                    _kill_process_tree(proc)
                    break
                text = raw.decode("utf-8", "replace")
                while True:
                    try:
                        ch.put(text, timeout=0.2)
                        break
                    except queue.Full:
                        if cancel_check and cancel_check():
                            return
        finally:
            try:
                ch.put(None, timeout=0.5)
            except queue.Full:
                pass

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    start = time.monotonic()
    timed_out = False
    cancelled = False

    try:
        while True:
            if cancel_check and cancel_check():
                cancelled = True
                _kill_process_tree(proc)
            elif time.monotonic() - start > timeout:
                timed_out = True
                _kill_process_tree(proc)
            try:
                item = ch.get(timeout=0.1)
            except queue.Empty:
                if not thread.is_alive():
                    break
                continue
            if item is None:
                break
            lines.append(item)
            if len(lines) > 400:
                lines = lines[-400:]
            if on_output is not None:
                on_output(item.rstrip("\r\n"))
    finally:
        if proc.poll() is None:
            _kill_process_tree(proc)
        exit_code = proc.wait()
        if proc.stdout is not None:
            proc.stdout.close()

    output = "".join(lines).strip()
    if truncated:
        output += "\n... [salida truncada al límite de 256 KiB]"
    return {
        "ok": exit_code == 0 and not timed_out and not cancelled,
        "exit_code": exit_code,
        "output": output,
        "seconds": round(time.monotonic() - start, 2),
        "timed_out": timed_out,
        "cancelled": cancelled,
    }


def _find_python(runtime: Path | None) -> Path:
    if runtime is not None:
        bundled = Path(runtime).resolve() / "herramientas/python/python.exe"
        if bundled.is_file():
            return bundled
    if not getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if exe.is_file():
            return exe
    found = shutil.which("python") or shutil.which("python3")
    if found:
        return Path(found)
    raise WorkspaceError("No se encontró un intérprete de Python disponible.")


def execute_workspace_command(
    workspace: SafeWorkspace,
    runtime: Path | None,
    command: str,
    *,
    timeout: int = 120,
    cancel_check: Callable[[], bool] | None = None,
    on_output: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Ejecuta un comando de desarrollo dentro de la carpeta del proyecto."""
    clean_cmd = validate_command(command)
    bounded_timeout = min(300, max(5, int(timeout or 120)))
    env = _build_env(runtime)
    if os.name == "nt":
        shell = shutil.which("powershell.exe") or shutil.which("powershell") or "powershell.exe"
        args = [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", clean_cmd]
    else:
        args = ["/bin/sh", "-c", clean_cmd]
    if on_output is not None:
        on_output(f"> {clean_cmd}")
    res = _run_subprocess_sync(
        args,
        cwd=workspace.root,
        env=env,
        timeout=bounded_timeout,
        cancel_check=cancel_check,
        on_output=on_output,
    )
    res["command"] = clean_cmd
    return res


def execute_project_action(
    workspace: SafeWorkspace,
    runtime: Path | None,
    action: str,
    path: str | None = None,
    *,
    cancel_check: Callable[[], bool] | None = None,
    on_output: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Ejecuta check, test, build o run sobre el proyecto actual y devuelve salida real."""
    act = str(action or "").strip().lower()
    if act not in VALID_PROJECT_ACTIONS:
        raise WorkspaceError(
            f"Acción inválida '{action}'. Usa una de: {', '.join(VALID_PROJECT_ACTIONS)}."
        )

    rel_target: str | None = None
    target_path: Path | None = None
    if path and str(path).strip() and str(path).strip() != ".":
        target_path = workspace.resolve_safe_path(str(path).strip())
        if not target_path.is_file():
            raise WorkspaceError(f"No existe el archivo objetivo: {path}")
        rel_target = workspace.to_rel_posix(target_path)

    # Si existe el runtime empaquetado con herramientas incluidas, usar ProjectRunner oficial
    rt_path = Path(runtime).resolve() if runtime is not None else None
    if rt_path is not None and (rt_path / "herramientas/python/python.exe").is_file():
        from .project_actions import ProjectRunner

        runner = ProjectRunner(rt_path)
        stop_flag = threading.Event()

        def _watch_cancel() -> None:
            while not stop_flag.is_set():
                if cancel_check and cancel_check():
                    runner.stop()
                    return
                stop_flag.wait(0.15)

        watcher = threading.Thread(target=_watch_cancel, daemon=True)
        watcher.start()
        try:
            verb = {"check": "verifica", "test": "prueba", "build": "compila", "run": "ejecuta"}[act]
            req = f"{verb} {rel_target}" if rel_target else verb
            result = runner.run(
                workspace.root,
                req,
                [act],
                preferred=rel_target,
                on_output=on_output or (lambda _line: None),
            )
        except ValueError as exc:
            raise WorkspaceError(str(exc)) from exc
        finally:
            stop_flag.set()

        cmds = result.get("commands") or []
        exit_code = cmds[-1]["exit_code"] if cmds else (0 if result.get("status") == "done" else 1)
        artifact = next((c.get("artifact") for c in reversed(cmds) if c.get("artifact")), None)
        return {
            "ok": result.get("status") == "done",
            "exit_code": exit_code,
            "action": act,
            "target": result.get("target") or rel_target or ".",
            "artifact": artifact,
            "output": result.get("content", ""),
            "commands": cmds,
        }

    # Respaldo directo en entorno de desarrollo / pruebas sin carpeta runtime/herramientas
    env = _build_env(rt_path)
    if target_path is None:
        for candidate in ("main.py", "app.py", "index.js"):
            p = workspace.root / candidate
            if p.is_file():
                target_path = p
                rel_target = candidate
                break
        if target_path is None:
            py_files = sorted(workspace.root.glob("*.py"))
            if len(py_files) == 1:
                target_path = py_files[0]
                rel_target = py_files[0].name

    # Caso especial: test con pytest sin archivo objetivo específico
    has_tests = (workspace.root / "tests").is_dir() or bool(list(workspace.root.glob("test_*.py")))
    if act == "test" and (has_tests or target_path is None):
        py = _find_python(rt_path)
        if not has_tests:
            raise WorkspaceError("No se encontraron pruebas ni archivo objetivo para probar.")
        cmd_args = [str(py), "-m", "pytest", "-q"]
        if on_output:
            on_output("> " + subprocess.list2cmdline(cmd_args))
        res = _run_subprocess_sync(cmd_args, cwd=workspace.root, env=env, timeout=240, cancel_check=cancel_check, on_output=on_output)
        return {
            **res,
            "action": act,
            "target": rel_target or "tests",
            "artifact": None,
            "commands": [{"action": act, "exit_code": res["exit_code"], "seconds": res["seconds"]}],
        }

    if target_path is None:
        raise WorkspaceError("Indica el archivo objetivo en `path` (por ejemplo `main.py`).")

    suffix = target_path.suffix.lower()
    if suffix == ".py":
        py = _find_python(rt_path)
        if act == "check":
            cmd_args = [str(py), "-m", "py_compile", str(target_path)]
            timeout = 90
            artifact = None
        elif act == "test":
            cmd_args = [str(py), str(target_path)]
            timeout = 120
            artifact = None
        elif act == "run":
            cmd_args = [str(py), str(target_path)]
            timeout = 120
            artifact = None
        else:  # build
            cmd_args = [str(py), "-m", "PyInstaller", "--noconfirm", "--onefile", "--name", target_path.stem, str(target_path)]
            timeout = 300
            artifact = str(workspace.root / "dist" / f"{target_path.stem}.exe")
        if on_output:
            on_output("> " + subprocess.list2cmdline(cmd_args))
        res = _run_subprocess_sync(cmd_args, cwd=workspace.root, env=env, timeout=timeout, cancel_check=cancel_check, on_output=on_output)
        if act == "build" and res["ok"] and artifact and not Path(artifact).is_file():
            res["ok"] = False
            res["exit_code"] = 1
            res["output"] = (res["output"] + "\nNo se encontró el ejecutable esperado en dist/.").strip()
        return {
            **res,
            "action": act,
            "target": rel_target or target_path.name,
            "artifact": artifact if (act == "build" and res["ok"]) else None,
            "commands": [{"action": act, "exit_code": res["exit_code"], "seconds": res["seconds"], "artifact": artifact}],
        }

    if suffix in {".js", ".mjs", ".cjs"}:
        node = shutil.which("node")
        if not node:
            raise WorkspaceError("No se encontró Node.js para verificar o ejecutar este archivo.")
        cmd_args = [node, "--check", str(target_path)] if act == "check" else [node, str(target_path)]
        if on_output:
            on_output("> " + subprocess.list2cmdline(cmd_args))
        res = _run_subprocess_sync(cmd_args, cwd=workspace.root, env=env, timeout=120, cancel_check=cancel_check, on_output=on_output)
        return {
            **res,
            "action": act,
            "target": rel_target or target_path.name,
            "artifact": None,
            "commands": [{"action": act, "exit_code": res["exit_code"], "seconds": res["seconds"]}],
        }

    raise WorkspaceError(f"Acción '{act}' no disponible para archivos '{suffix}' sin herramientas empaquetadas.")
