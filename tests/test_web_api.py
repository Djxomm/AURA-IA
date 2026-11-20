"""Pruebas de API REST y streaming SSE concurrente con aprobación humana."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from agente_ia.providers import LocalLLMClient
from agente_ia.storage import Storage
from agente_ia.web_server import create_app


def _make_mock_app(tmp_path: Path):
    step = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal step
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:0.5b", "size": 417333248}]})
        if request.url.path == "/v1/models":
            return httpx.Response(503)
        if request.url.path == "/api/chat":
            step += 1
            if step == 1:
                payload = {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "w1",
                                "function": {
                                    "name": "edit_file",
                                    "arguments": {
                                        "path": "demo.py",
                                        "old_text": "VALOR = 1",
                                        "new_text": "VALOR = 99",
                                        "reason": "Actualizar constante VALOR",
                                    },
                                },
                            }
                        ],
                    },
                    "done": True,
                    "eval_count": 14,
                    "eval_duration": 500_000_000,
                }
            else:
                payload = {
                    "message": {"role": "assistant", "content": "Listo, VALOR quedó en 99."},
                    "done": True,
                    "eval_count": 10,
                    "eval_duration": 250_000_000,
                }
            return httpx.Response(200, text=json.dumps(payload) + "\n")
        return httpx.Response(404)

    storage = Storage(tmp_path / "test.db")
    cur = storage.get_settings()
    storage.save_settings(cur.model_copy(update={"workspace_path": str(tmp_path), "provider":"ollama"}))
    client = LocalLLMClient(transport=httpx.MockTransport(handler))
    return create_app(storage=storage, llm_client=client)


def test_rest_endpoints_settings_profiles_and_workspace(tmp_path: Path) -> None:
    (tmp_path / "demo.py").write_text("VALOR = 1\n", encoding="utf-8")
    app = _make_mock_app(tmp_path)
    tc = TestClient(app)

    r_health = tc.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    r_prov = tc.get("/api/providers/status")
    assert r_prov.status_code == 200
    pdata = r_prov.json()
    assert pdata["any_online"] is True
    assert "llamacpp" in pdata["providers"]
    assert "legacy_i5_1gb" in pdata["hardware_profiles"]

    # Cambiar perfil de hardware y confirmar que aplica defaults + override
    r_put = tc.put(
        "/api/settings",
        json={"hardware_profile": "balanced_cpu", "apply_profile": True, "num_gpu": 0},
    )
    assert r_put.status_code == 200
    sdata = r_put.json()
    assert sdata["hardware_profile"] == "balanced_cpu"
    assert sdata["num_ctx"] == 4096
    assert sdata["num_gpu"] == 0

    r_tree = tc.get("/api/workspace/tree")
    assert r_tree.status_code == 200
    assert "demo.py" in r_tree.json()["entries"]

    r_file = tc.get("/api/workspace/file", params={"path": "demo.py"})
    assert r_file.status_code == 200
    assert r_file.json()["content"] == (tmp_path / "demo.py").read_bytes().decode("utf-8")

    # Sesiones CRUD
    r_sess = tc.post("/api/sessions", json={"title": "Prueba API"})
    assert r_sess.status_code == 200
    sid = r_sess.json()["session"]["id"]
    assert any(s["id"] == sid for s in tc.get("/api/sessions").json()["sessions"])
    assert tc.delete(f"/api/sessions/{sid}").status_code == 200


def test_sse_stream_with_concurrent_approval_and_revert(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    target.write_text("VALOR = 1\n", encoding="utf-8")
    app = _make_mock_app(tmp_path)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            sess_resp = await client.post("/api/sessions", json={"title": "SSE Test"})
            session_id = sess_resp.json()["session"]["id"]

            seen_events: list[dict] = []
            proposal_id: str | None = None

            async def approve_pending():
                nonlocal proposal_id
                for _ in range(200):
                    await asyncio.sleep(0.01)
                    pending = app.state.storage.list_changes(session_id=session_id)
                    if pending:
                        proposal_id = pending[0]["id"]
                        assert target.read_text(encoding="utf-8") == "VALOR = 1\n"
                        result = await client.post(f"/api/proposals/{proposal_id}/resolve", json={"approved": True})
                        assert result.status_code == 200
                        return
                raise AssertionError("No apareció propuesta pendiente")

            approval = asyncio.create_task(approve_pending())
            response = await asyncio.wait_for(client.post("/api/chat/stream", json={"session_id": session_id, "message": "Cambia VALOR a 99"}), 10)
            await approval
            assert response.status_code == 200
            seen_events = [json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith("data:")]
            assert proposal_id is not None
            types = [e["type"] for e in seen_events]
            assert "proposal" in types
            assert "proposal_resolved" in types
            assert "done" in types
            assert target.read_text(encoding="utf-8") == "VALOR = 99\n"

            # Revertir vía API y validar archivo restaurado
            rev_resp = await client.post(f"/api/changes/{proposal_id}/revert")
            assert rev_resp.status_code == 200
            assert target.read_text(encoding="utf-8") == "VALOR = 1\n"

    asyncio.run(run())
