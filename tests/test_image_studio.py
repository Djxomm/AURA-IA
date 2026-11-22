"""Pruebas del estudio offline de generación y edición de imágenes (Pillow + stable-diffusion.cpp)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from agente_ia.agent import AgentEngine, ApprovalRegistry
from agente_ia.config import AppSettings
from agente_ia.image_studio import edit_image
from agente_ia.providers import LocalLLMClient
from agente_ia.storage import Storage
from agente_ia.tools import EXEC_TOOLS, parse_xml_tool_calls
from agente_ia.workspace import SafeWorkspace, WorkspaceError


def test_parse_generate_and_edit_image_tool_calls():
    assert "generate_image" in EXEC_TOOLS and "edit_image" in EXEC_TOOLS
    _, c1 = parse_xml_tool_calls(
        '<tool_call>{"name": "generate_image", "arguments": {"prompt": "photorealistic espresso cup", "output_path": "img/cafe.png"}}</tool_call>'
    )
    assert len(c1) == 1 and c1[0]["name"] == "generate_image"
    _, c2 = parse_xml_tool_calls(
        '{"name": "edit_image", "arguments": {"input_path": "img/cafe.png", "output_path": "img/cafe_edit.png", "operations": [{"op": "contrast", "factor": 1.2}]}}'
    )
    assert len(c2) == 1 and c2[0]["name"] == "edit_image"


def test_edit_image_pillow_pipeline_and_workspace_boundary(tmp_path: Path):
    ws = SafeWorkspace(str(tmp_path))
    src = tmp_path / "base.png"
    Image.new("RGB", (320, 240), color=(30, 80, 140)).save(str(src))

    res = edit_image(
        ws,
        None,
        "base.png",
        "salidas/editada.webp",
        operations=[
            {"op": "resize", "width": 256, "height": 192},
            {"op": "contrast", "factor": 1.25},
            {"op": "brightness", "factor": 1.1},
            {"op": "border", "width": 4, "color": "#38bdf8"},
            {"op": "text", "text": "AURA", "x": 12, "y": 12, "color": "#ffffff", "bg": "#0f172a"},
        ],
    )
    assert res["ok"] is True
    assert res["path"] == "salidas/editada.webp"
    assert res["width"] == 264 and res["height"] == 200
    assert (tmp_path / "salidas/editada.webp").is_file()

    with pytest.raises(WorkspaceError):
        edit_image(ws, None, "base.png", "../fuera.png", operations=[{"op": "grayscale"}])


def test_autonomous_agent_executes_edit_image_tool(tmp_path: Path):
    Image.new("RGB", (128, 128), color=(20, 40, 80)).save(str(tmp_path / "foto.png"))
    replies = [
        '<tool_call>{"name": "edit_image", "arguments": {"input_path": "foto.png", "output_path": "foto_bn.png", "operations": [{"op": "grayscale"}, {"op": "autocontrast"}], "reason": "Convertir a blanco y negro con alto contraste"}}</tool_call>',
        "Edité `foto.png` y guardé el resultado en `foto_bn.png`.",
    ]
    idx = 0

    async def respond(_req: httpx.Request) -> httpx.Response:
        nonlocal idx
        r = replies[min(idx, len(replies) - 1)]
        idx += 1
        return httpx.Response(200, text=json.dumps({"message": {"role": "assistant", "content": r}, "done": True}) + "\n")

    async def scenario() -> None:
        store = Storage(":memory:")
        engine = AgentEngine(store, LocalLLMClient(transport=httpx.MockTransport(respond)), ApprovalRegistry())
        session = store.create_session(title="Img", workspace_path=str(tmp_path), provider="ollama", model="test")
        settings = AppSettings(workspace_path=str(tmp_path), provider="ollama", model="test", tool_mode="xml", autonomous_mode=True)
        res = await engine.run_turn(session_id=session["id"], user_message="Pasa foto.png a blanco y negro", settings=settings)
        assert res["status"] == "done"
        assert (tmp_path / "foto_bn.png").is_file()

    asyncio.run(scenario())
