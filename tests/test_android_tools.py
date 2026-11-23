"""Pruebas de herramientas Android (ADB USB/Wi-Fi, Fastboot, detección SDK, política de seguridad y /android)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from agente_ia.agent import AgentEngine, ApprovalDecision, ApprovalRegistry
from agente_ia.android_tools import (
    android_command_policy,
    inspect_android_devices,
    parse_adb_devices,
    parse_fastboot_devices,
)
from agente_ia.command_exec import command_requires_approval, validate_command
from agente_ia.config import AppSettings
from agente_ia.pc_control import pc_inspect
from agente_ia.providers import LocalLLMClient
from agente_ia.skills import SkillStore
from agente_ia.slash_palette import build_slash_catalog, resolve_slash_command
from agente_ia.storage import Storage
from agente_ia.workspace import SafeWorkspace, WorkspaceError


def test_parse_adb_and_fastboot_devices_distinguishes_usb_and_wifi():
    adb_out = (
        "List of devices attached\n"
        "R58M91ABCDE            device product:beyond1 model:SM_G973F device:beyond1 transport_id:1\n"
        "192.168.1.45:37123     device product:oriole model:Pixel_6 device:oriole transport_id:2\n"
        "adb-ABC123-xyz._adb-tls-connect._tcp  device model:Moto_G84 transport_id:3\n"
        "ZY22449988             unauthorized transport_id:4\n"
    )
    devs = parse_adb_devices(adb_out)
    assert len(devs) == 4
    assert devs[0]["transport"] == "usb" and devs[0]["state"] == "device" and devs[0]["model"] == "SM_G973F"
    assert devs[1]["transport"] == "wifi" and devs[1]["serial"] == "192.168.1.45:37123"
    assert devs[2]["transport"] == "wifi" and devs[2]["model"] == "Moto_G84"
    assert devs[3]["transport"] == "usb" and devs[3]["state"] == "unauthorized"

    fb_out = "R58M91ABCDE\tfastboot\n"
    fb_devs = parse_fastboot_devices(fb_out)
    assert fb_devs == [{"serial": "R58M91ABCDE", "state": "fastboot", "transport": "usb"}]


def test_android_security_policy_blocks_brick_prompts_mutations_allows_safe_diagnostics():
    # Diagnósticos y compilación debug corren automáticos en modo autónomo
    for safe in (
        "adb devices -l",
        "adb -s 192.168.1.45:5555 logcat -d -b crash",
        "adb shell getprop ro.build.version.release",
        "adb shell dumpsys meminfo com.ejemplo.app",
        "adb pair 192.168.1.45:37891 123456",
        "adb connect 192.168.1.45:41235",
        "adb reverse tcp:8000 tcp:8000",
        "fastboot devices",
        "fastboot getvar all",
        "heimdall detect",
        "heimdall print-pit --no-reboot",
        ".\\gradlew.bat :app:assembleDebug",
    ):
        assert android_command_policy(safe) == "safe_auto", f"Debió ser safe_auto: {safe}"
        assert command_requires_approval(safe) is False
        assert validate_command(safe) == safe

    # Mutaciones de dispositivo, modificación de bootloader y flasheo de Custom ROM (Galaxy/Fastboot/Heimdall/Sideload)
    # están HABILITADAS con aprobación obligatoria de 1 clic
    for risky in (
        "adb install -r app-debug.apk",
        "adb -s 192.168.1.45:5555 uninstall com.ejemplo.app",
        "adb shell pm clear com.ejemplo.app",
        "adb reboot bootloader",
        "adb sideload custom-rom-galaxy.zip",
        "fastboot flash bootloader bl.img",
        "fastboot flash aboot aboot.img",
        "fastboot flash vbmeta --disable-verity --disable-verification vbmeta.img",
        "fastboot flash boot boot.img",
        "fastboot flashing unlock",
        "fastboot oem unlock",
        "fastboot reboot",
        "fastboot -w",
        "heimdall flash --RECOVERY twrp.img --VBMETA vbmeta.img --no-reboot",
    ):
        assert android_command_policy(risky) == "requires_approval", f"Debió requerir aprobación (y estar habilitado): {risky}"
        assert command_requires_approval(risky) is True
        assert validate_command(risky) == risky

    # Únicamente el borrado de calibración IMEI/EFS permanece bloqueado para proteger el teléfono
    for brick in (
        "fastboot erase efs",
        "fastboot erase sec_efs",
        "fastboot erase modemst1",
        "fastboot format nvram",
    ):
        assert android_command_policy(brick) == "blocked", f"Debió bloquearse: {brick}"
        with pytest.raises(WorkspaceError):
            validate_command(brick)


def test_pc_inspect_android_devices_and_slash_android(tmp_path: Path):
    ws = SafeWorkspace(str(tmp_path))
    info = pc_inspect(ws, "android_devices")
    assert info["action"] == "android_devices"
    assert isinstance(info["adb_devices"], list)
    assert isinstance(info["fastboot_devices"], list)
    assert "toolchain" in info

    # /android funciona con fallback y con skill android-adb-dev
    r1 = resolve_slash_command("/android conecta mi celular por wifi y revisa logcat", None)
    assert r1["type"] == "prompt" and r1.get("auto_autonomous") is True

    store = SkillStore(tmp_path / "skills")
    bundle = tmp_path / "bundle"
    (bundle / "android-adb-dev").mkdir(parents=True)
    (bundle / "android-adb-dev" / "SKILL.md").write_text(
        "---\nname: android-adb-dev\ndescription: Android Compose ADB Fastboot\n---\n\n# Android\n",
        encoding="utf-8",
    )
    sid = store.install_bundled(bundle, "android-adb-dev")
    cmds = {e.command for e in build_slash_catalog(store)}
    assert {"/android", "/android-adb-dev"} <= cmds
    r2 = resolve_slash_command("/adb revisa crash de mi app", store)
    assert r2["type"] == "invoke_skill" and r2["skill_id"] == sid and r2.get("auto_autonomous") is True


def test_autonomous_agent_runs_android_inspect_auto_and_prompts_on_adb_install_and_fastboot(tmp_path: Path):
    replies = [
        '<tool_call>{"name": "pc_inspect", "arguments": {"action": "android_devices"}}</tool_call>',
        '<tool_call>{"name": "run_command", "arguments": {"command": "adb install -r app-debug.apk", "reason": "Instalar APK en dispositivo"}}</tool_call>',
        '<tool_call>{"name": "run_command", "arguments": {"command": "fastboot reboot", "reason": "Reiniciar bootloader"}}</tool_call>',
        "Inspeccioné los dispositivos Android y pedí aprobación para adb install y fastboot reboot.",
    ]
    idx = 0
    prompts: list[str] = []

    async def respond(_req: httpx.Request) -> httpx.Response:
        nonlocal idx
        r = replies[min(idx, len(replies) - 1)]
        idx += 1
        return httpx.Response(200, text=json.dumps({"message": {"role": "assistant", "content": r}, "done": True}) + "\n")

    async def scenario() -> None:
        store = Storage(":memory:")
        engine = AgentEngine(store, LocalLLMClient(transport=httpx.MockTransport(respond)), ApprovalRegistry())
        session = store.create_session(title="Android", workspace_path=str(tmp_path), provider="ollama", model="test")

        async def handle(proposal):
            prompts.append(proposal.proposed_content or "")
            return ApprovalDecision(approved=False, feedback="Prueba segura sin tocar teléfono")

        settings = AppSettings(workspace_path=str(tmp_path), provider="ollama", model="test", tool_mode="xml", autonomous_mode=True)
        res = await engine.run_turn(session_id=session["id"], user_message="Depura Android", settings=settings, approval_handler=handle)
        assert res["status"] == "done"
        assert len(prompts) == 2
        assert "adb install" in prompts[0]
        assert "fastboot reboot" in prompts[1]

    asyncio.run(scenario())
