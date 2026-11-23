"""Detección de herramientas Android (SDK, ADB, Fastboot), lectura de dispositivos USB/Wi-Fi
y clasificación de seguridad para mantenimiento de apps Android desde AURA."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


_BLOCKED_FASTBOOT_PATTERNS = (
    # Protege únicamente contra borrado irreversible de calibración de radio/IMEI;
    # la modificación/flasheo de bootloader, vbmeta, boot, recovery y ROMs queda habilitada con aprobación de 1 clic.
    re.compile(r"(?i)\bfastboot\b.*\b(?:erase|format)\s+(?:efs|sec_efs|modemst1|modemst2|nvram|fsg)\b"),
)

_APPROVAL_ANDROID_PATTERNS = (
    re.compile(r"(?i)\badb\b(?:\s+-s\s+\S+)?\s+(?:install|install-multiple|uninstall|reboot|root|unroot|remount|sideload|push|disable-verity|enable-verity)\b"),
    re.compile(r"(?i)\badb\b(?:\s+-s\s+\S+)?\s+shell\s+(?:rm\b|pm\s+(?:clear|uninstall|disable|disable-user|enable|grant|revoke)\b|settings\s+put\b|am\s+force-stop\b|reboot\b|svc\b)"),
    re.compile(r"(?i)\bfastboot\b(?:\s+-s\s+\S+)?\s+(?:flash|erase|format|oem|flashing|reboot|boot|-w|update|set_active|continue|create-logical-partition|delete-logical-partition|resize-logical-partition)\b"),
    re.compile(r"(?i)\bheimdall\b.*\b(?:flash|close-pc-screen)\b"),
)


def is_bootloader_or_flash_command(command: str) -> bool:
    """Detecta comandos de modificación de bootloader, flasheo de particiones o sideload de Custom ROM."""
    text = str(command or "").strip()
    return bool(
        re.search(
            r"(?i)(?:\bfastboot\b.*\b(?:flash|erase|format|oem|flashing|boot|-w|update|set_active|logical-partition)\b|\bheimdall\b.*\bflash\b|\badb\b.*\bsideload\b)",
            text,
        )
    )


def android_command_policy(command: str) -> str:
    """Clasifica un comando Android/ADB/Fastboot en 'blocked', 'requires_approval' o 'safe_auto'."""
    text = str(command or "").strip()
    for pat in _BLOCKED_FASTBOOT_PATTERNS:
        if pat.search(text):
            return "blocked"
    for pat in _APPROVAL_ANDROID_PATTERNS:
        if pat.search(text):
            return "requires_approval"
    return "safe_auto"


def find_android_sdk() -> Path | None:
    """Ubica el directorio raíz del Android SDK si existe en el equipo."""
    candidates: list[Path] = []
    for env_key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        val = os.environ.get(env_key)
        if val:
            candidates.append(Path(val))
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        candidates.append(Path(local_app) / "Android" / "Sdk")
    candidates.extend([Path(r"C:\Android\Sdk"), Path(r"D:\Android\Sdk")])
    for cand in candidates:
        if cand.is_dir():
            return cand.resolve()
    return None


def find_platform_tools(runtime: Path | None = None) -> dict[str, str | None]:
    """Localiza adb y fastboot en el runtime de AURA, el Android SDK local o el PATH del sistema."""
    dirs: list[Path] = []
    if runtime is not None:
        dirs.append(Path(runtime).resolve() / "herramientas" / "platform-tools")
    pkg_runtime = Path(__file__).resolve().parent.parent / "runtime" / "herramientas" / "platform-tools"
    if pkg_runtime not in dirs:
        dirs.append(pkg_runtime)
    sdk = find_android_sdk()
    if sdk is not None:
        dirs.append(sdk / "platform-tools")
    dirs.extend([Path(r"C:\platform-tools"), Path(r"D:\platform-tools")])

    adb_path: str | None = None
    fb_path: str | None = None
    exe_ext = ".exe" if os.name == "nt" else ""
    for d in dirs:
        if not d.is_dir():
            continue
        if adb_path is None and (d / f"adb{exe_ext}").is_file():
            adb_path = str((d / f"adb{exe_ext}").resolve())
        if fb_path is None and (d / f"fastboot{exe_ext}").is_file():
            fb_path = str((d / f"fastboot{exe_ext}").resolve())

    if adb_path is None:
        adb_path = shutil.which("adb")
    if fb_path is None:
        fb_path = shutil.which("fastboot")

    return {
        "sdk_dir": str(sdk) if sdk else None,
        "adb": adb_path,
        "fastboot": fb_path,
        "heimdall": shutil.which("heimdall"),
        "java": shutil.which("java"),
    }


def parse_adb_devices(output: str) -> list[dict[str, Any]]:
    """Parsea la salida de `adb devices -l` distinguiendo USB y Wi-Fi/TCP."""
    devices: list[dict[str, Any]] = []
    for raw in str(output or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        meta: dict[str, str] = {}
        for token in parts[2:]:
            if ":" in token:
                k, v = token.split(":", 1)
                meta[k] = v
        is_wifi = (":" in serial) or ("_adb-tls-connect" in serial) or ("_adb._tcp" in serial)
        devices.append(
            {
                "serial": serial,
                "state": state,
                "transport": "wifi" if is_wifi else "usb",
                "model": meta.get("model", ""),
                "device": meta.get("device", ""),
                "product": meta.get("product", ""),
                "transport_id": meta.get("transport_id", ""),
            }
        )
    return devices


def parse_fastboot_devices(output: str) -> list[dict[str, Any]]:
    """Parsea la salida de `fastboot devices`."""
    devices: list[dict[str, Any]] = []
    for raw in str(output or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "state": parts[1], "transport": "usb"})
    return devices


def inspect_android_devices(runtime: Path | None = None) -> dict[str, Any]:
    """Inspección de solo lectura del entorno Android y dispositivos ADB (USB/Wi-Fi) y Fastboot conectados."""
    tools = find_platform_tools(runtime)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    adb_devices: list[dict[str, Any]] = []
    fastboot_devices: list[dict[str, Any]] = []
    adb_error = ""
    fb_error = ""

    if tools["adb"]:
        try:
            proc = subprocess.run(
                [tools["adb"], "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=flags,
            )
            adb_devices = parse_adb_devices(proc.stdout)
            if proc.returncode != 0 and proc.stderr.strip():
                adb_error = proc.stderr.strip()[:300]
        except Exception as exc:
            adb_error = str(exc)

    if tools["fastboot"]:
        try:
            proc = subprocess.run(
                [tools["fastboot"], "devices"],
                capture_output=True,
                text=True,
                timeout=6,
                creationflags=flags,
            )
            fastboot_devices = parse_fastboot_devices(proc.stdout)
            if proc.returncode != 0 and proc.stderr.strip():
                fb_error = proc.stderr.strip()[:300]
        except Exception as exc:
            fb_error = str(exc)

    return {
        "action": "android_devices",
        "toolchain": tools,
        "adb_count": len(adb_devices),
        "adb_devices": adb_devices,
        "fastboot_count": len(fastboot_devices),
        "fastboot_devices": fastboot_devices,
        "adb_error": adb_error,
        "fastboot_error": fb_error,
    }
