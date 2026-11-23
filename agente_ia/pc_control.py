"""Inspección segura y control de la PC Windows para AURA (con aprobación explícita en acciones activas).
Usa APIs nativas de Windows (ctypes user32, psutil, Pillow ImageGrab, subprocess) sin dependencias frágiles."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

import psutil

from .workspace import SafeWorkspace, WorkspaceError


PC_INSPECT_ACTIONS = ("system_info", "list_processes", "list_windows", "screenshot", "clipboard_get")
PC_CONTROL_ACTIONS = (
    "open_app",
    "open_path",
    "focus_window",
    "mouse_click",
    "type_text",
    "press_hotkey",
    "close_process",
    "clipboard_set",
)

_PROTECTED_PROCESSES = {
    "system",
    "system idle process",
    "registry",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "winlogon.exe",
    "svchost.exe",
    "dwm.exe",
    "explorer.exe",
    "aura-nativa.exe",
}

_BLOCKED_APPS = {
    "format",
    "format.com",
    "diskpart",
    "diskpart.exe",
    "bcdedit",
    "bcdedit.exe",
    "shutdown",
    "shutdown.exe",
    "regedit",
    "reg.exe",
    "cipher.exe",
}

_VK_MAP: dict[str, int] = {
    "ctrl": 0x11,
    "control": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "win": 0x5B,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f11": 0x7A,
    "f12": 0x7B,
}


def _list_visible_windows(limit: int = 40) -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    results: list[dict[str, Any]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        if len(results) >= limit:
            return False
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        results.append({"hwnd": int(hwnd), "pid": int(pid.value), "title": title[:160]})
        return True

    user32.EnumWindows(_cb, 0)
    return results


def pc_inspect(
    workspace: SafeWorkspace,
    action: str,
    *,
    query: str = "",
    output_path: str = "capturas/pantalla.png",
    limit: int = 25,
) -> dict[str, Any]:
    """Inspección de solo lectura de la PC (sistema, procesos, ventanas, captura o portapapeles)."""
    act = str(action or "").strip().lower()
    if act not in PC_INSPECT_ACTIONS:
        raise WorkspaceError(f"Acción pc_inspect inválida '{action}'. Usa: {', '.join(PC_INSPECT_ACTIONS)}.")

    if act == "system_info":
        vm = psutil.virtual_memory()
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "drive": part.mountpoint,
                    "free_gb": round(usage.free / (1024**3), 2),
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_pct": usage.percent,
                })
            except OSError:
                continue
        return {
            "action": "system_info",
            "cpu_percent": psutil.cpu_percent(interval=0.15),
            "physical_cores": psutil.cpu_count(logical=False) or 1,
            "logical_cores": psutil.cpu_count(logical=True) or 1,
            "ram_free_gb": round(vm.available / (1024**3), 2),
            "ram_total_gb": round(vm.total / (1024**3), 2),
            "ram_used_pct": vm.percent,
            "disks": disks,
        }

    if act == "list_processes":
        q = str(query or "").strip().lower()
        cap = max(5, min(60, int(limit or 25)))
        rows = []
        for proc in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                name = str(proc.info.get("name") or "")
                if q and q not in name.lower():
                    continue
                mem = proc.info.get("memory_info")
                mb = round((mem.rss if mem else 0) / (1024**2), 1)
                rows.append({"pid": int(proc.info["pid"]), "name": name, "ram_mb": mb})
            except (psutil.Error, OSError):
                continue
        rows.sort(key=lambda r: r["ram_mb"], reverse=True)
        return {"action": "list_processes", "count": len(rows[:cap]), "processes": rows[:cap]}

    if act == "list_windows":
        q = str(query or "").strip().lower()
        wins = _list_visible_windows(limit=max(10, min(80, int(limit or 40))))
        if q:
            wins = [w for w in wins if q in w["title"].lower()]
        return {"action": "list_windows", "count": len(wins), "windows": wins}

    if act == "screenshot":
        target = workspace.resolve_safe_path(str(output_path or "capturas/pantalla.png").strip(), allow_write=True)
        if target.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise WorkspaceError("La captura de pantalla debe guardarse como .png, .jpg o .webp.")
        target.parent.mkdir(parents=True, exist_ok=True)
        from PIL import ImageGrab

        img = ImageGrab.grab()
        img.save(str(target))
        return {
            "action": "screenshot",
            "path": workspace.to_rel_posix(target),
            "width": img.width,
            "height": img.height,
            "bytes": target.stat().st_size,
        }

    # clipboard_get
    if os.name == "nt":
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return {"action": "clipboard_get", "text": proc.stdout[:3000]}
    return {"action": "clipboard_get", "text": ""}


def describe_pc_action(action: str, args: dict[str, Any]) -> str:
    """Genera una descripción clara para la ventana de aprobación del usuario."""
    act = str(action or "").strip().lower()
    if act not in PC_CONTROL_ACTIONS:
        raise WorkspaceError(f"Acción pc_control inválida '{action}'. Usa: {', '.join(PC_CONTROL_ACTIONS)}.")
    if act == "open_app":
        app = str(args.get("target") or "").strip()
        if not app:
            raise WorkspaceError("Indica el programa en `target` (ej. notepad, calc, explorer, blender).")
        if Path(app).name.lower() in _BLOCKED_APPS or app.lower() in _BLOCKED_APPS:
            raise WorkspaceError(f"Aplicación bloqueada por seguridad del sistema: {app}")
        extra = args.get("arguments") or []
        return f"Abrir aplicación: {app} {' '.join(str(a) for a in extra)}".strip()
    if act == "open_path":
        target = str(args.get("target") or "").strip()
        if not target:
            raise WorkspaceError("Indica la carpeta, archivo o URL en `target`.")
        return f"Abrir ruta/URL en Windows: {target}"
    if act == "focus_window":
        title = str(args.get("target") or "").strip()
        if not title:
            raise WorkspaceError("Indica parte del título de la ventana en `target`.")
        return f"Enfocar ventana que contenga: '{title}'"
    if act == "mouse_click":
        x, y = int(args.get("x", -1)), int(args.get("y", -1))
        if x < 0 or y < 0:
            raise WorkspaceError("Indica coordenadas válidas `x >= 0` y `y >= 0`.")
        btn = str(args.get("button") or "left").lower()
        return f"Clic de ratón ({btn}) en coordenadas ({x}, {y})"
    if act == "type_text":
        txt = str(args.get("text") or "")
        if not txt:
            raise WorkspaceError("Indica el texto a escribir en `text`.")
        return f"Escribir texto en ventana activa ({len(txt)} caracteres): {txt[:80]}"
    if act == "press_hotkey":
        keys = str(args.get("keys") or "").strip()
        if not keys:
            raise WorkspaceError("Indica la combinación de teclas en `keys` (ej. 'ctrl+s', 'alt+tab').")
        return f"Pulsar combinación de teclas: {keys}"
    if act == "close_process":
        target = str(args.get("target") or "").strip()
        if not target:
            raise WorkspaceError("Indica el PID o nombre del proceso en `target`.")
        if target.lower() in _PROTECTED_PROCESSES:
            raise WorkspaceError(f"Proceso crítico del sistema protegido: {target}")
        return f"Cerrar proceso: {target}"
    if act == "clipboard_set":
        txt = str(args.get("text") or "")
        return f"Copiar texto al portapapeles ({len(txt)} caracteres)"
    return f"pc_control({act})"


def _send_unicode_text(text: str) -> None:
    user32 = ctypes.windll.user32
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]

    for ch in text:
        code = ord(ch)
        down = INPUT(type=INPUT_KEYBOARD, union=_INPUTUNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0)))
        up = INPUT(type=INPUT_KEYBOARD, union=_INPUTUNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)))
        arr = (INPUT * 2)(down, up)
        user32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(INPUT))
        time.sleep(0.005)


def _press_hotkey_win(keys: str) -> None:
    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    vks: list[int] = []
    for part in keys.lower().split("+"):
        token = part.strip()
        if not token:
            continue
        if token in _VK_MAP:
            vks.append(_VK_MAP[token])
        elif len(token) == 1 and token.isalnum():
            vks.append(ord(token.upper()))
        else:
            raise WorkspaceError(f"Tecla no reconocida en combinación: '{token}'")
    if not vks:
        raise WorkspaceError("Combinación de teclas vacía.")
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)


def execute_pc_control(workspace: SafeWorkspace, action: str, args: dict[str, Any]) -> dict[str, Any]:
    """Ejecuta una acción activa de control de PC previamente autorizada por el usuario."""
    act = str(action or "").strip().lower()
    describe_pc_action(act, args)

    if act == "open_app":
        app = str(args.get("target") or "").strip()
        extra = [str(a) for a in (args.get("arguments") or [])]
        resolved = shutil.which(app) or app
        proc = subprocess.Popen([resolved, *extra], cwd=str(workspace.root))
        return {"ok": True, "action": act, "target": resolved, "pid": int(proc.pid)}

    if act == "open_path":
        target = str(args.get("target") or "").strip()
        if target.startswith(("http://", "https://")):
            os.startfile(target)  # type: ignore[attr-defined]
            return {"ok": True, "action": act, "target": target}
        p = Path(target)
        if not p.is_absolute():
            p = workspace.resolve_safe_path(target)
        if not p.exists():
            raise WorkspaceError(f"No existe la ruta: {p}")
        os.startfile(str(p))  # type: ignore[attr-defined]
        return {"ok": True, "action": act, "target": str(p)}

    if act == "focus_window":
        if os.name != "nt":
            raise WorkspaceError("focus_window solo está disponible en Windows.")
        q = str(args.get("target") or "").strip().lower()
        wins = _list_visible_windows(limit=80)
        match = next((w for w in wins if q in w["title"].lower()), None)
        if match is None:
            raise WorkspaceError(f"No se encontró ninguna ventana visible que contenga '{q}'.")
        user32 = ctypes.windll.user32
        user32.ShowWindow(match["hwnd"], 9)  # SW_RESTORE
        user32.SetForegroundWindow(match["hwnd"])
        return {"ok": True, "action": act, "window": match}

    if act == "mouse_click":
        if os.name != "nt":
            raise WorkspaceError("mouse_click solo está disponible en Windows.")
        x, y = int(args["x"]), int(args["y"])
        btn = str(args.get("button") or "left").lower()
        clicks = 2 if btn == "double" else 1
        user32 = ctypes.windll.user32
        user32.SetCursorPos(x, y)
        time.sleep(0.03)
        down_flag, up_flag = (0x0008, 0x0010) if btn == "right" else (0x0002, 0x0004)
        for _ in range(clicks):
            user32.mouse_event(down_flag, 0, 0, 0, 0)
            time.sleep(0.02)
            user32.mouse_event(up_flag, 0, 0, 0, 0)
            time.sleep(0.05)
        return {"ok": True, "action": act, "x": x, "y": y, "button": btn}

    if act == "type_text":
        if os.name != "nt":
            raise WorkspaceError("type_text solo está disponible en Windows.")
        txt = str(args.get("text") or "")
        _send_unicode_text(txt)
        return {"ok": True, "action": act, "chars": len(txt)}

    if act == "press_hotkey":
        if os.name != "nt":
            raise WorkspaceError("press_hotkey solo está disponible en Windows.")
        keys = str(args.get("keys") or "")
        _press_hotkey_win(keys)
        return {"ok": True, "action": act, "keys": keys}

    if act == "close_process":
        target = str(args.get("target") or "").strip()
        closed = []
        if target.isdigit():
            p = psutil.Process(int(target))
            if p.name().lower() in _PROTECTED_PROCESSES:
                raise WorkspaceError(f"Proceso crítico protegido: {p.name()}")
            p.terminate()
            closed.append({"pid": p.pid, "name": p.name()})
        else:
            for p in psutil.process_iter(["pid", "name"]):
                if str(p.info.get("name") or "").lower() == target.lower():
                    if target.lower() in _PROTECTED_PROCESSES:
                        raise WorkspaceError(f"Proceso crítico protegido: {target}")
                    p.terminate()
                    closed.append({"pid": int(p.info["pid"]), "name": str(p.info["name"])})
        if not closed:
            raise WorkspaceError(f"No se encontró proceso activo coincidente con '{target}'.")
        return {"ok": True, "action": act, "closed": closed}

    if act == "clipboard_set":
        txt = str(args.get("text") or "")
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
            input=txt,
            text=True,
            timeout=10,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return {"ok": True, "action": act, "chars": len(txt)}

    raise WorkspaceError(f"Acción no soportada: {act}")
