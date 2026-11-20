"""Terminal initiated only by an explicit user confirmation in the UI, más API de skills."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .skills import MAX_ENABLED_SKILLS
from .workspace import SafeWorkspace


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4000)
    confirmed: Literal[True]


async def execute_command(command: str, cwd: str, timeout: float = 120) -> dict[str, Any]:
    if os.name == "nt":
        args = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command]
        kwargs: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW}
    else:
        args = ["/bin/sh", "-c", command]
        kwargs = {}
    base = (
        Path(sys.executable).parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent / "offline"
    )
    env = dict(os.environ)
    env["PATH"] = str(base / "herramientas/python") + os.pathsep + env.get("PATH", "")
    env["PYTHONUTF8"] = "1"
    child = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        **kwargs,
    )
    chunks = bytearray()
    truncated = False

    async def drain() -> int:
        nonlocal truncated
        assert child.stdout is not None
        while block := await child.stdout.read(4096):
            space = max(0, 64000 - len(chunks))
            chunks.extend(block[:space])
            truncated |= len(block) > space
        return await child.wait()

    timed_out = False
    try:
        code = await asyncio.wait_for(drain(), timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        if os.name == "nt":
            await asyncio.to_thread(
                subprocess.run,
                ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        elif child.returncode is None:
            child.kill()
        await child.wait()
        if isinstance(exc, asyncio.CancelledError):
            raise
        code, timed_out = child.returncode, True
    return {
        "exit_code": code,
        "output": chunks.decode("utf-8", errors="replace"),
        "truncated": truncated,
        "timed_out": timed_out,
        "workspace": cwd,
    }


def register_desktop_routes(app: Any, db: Any) -> None:
    @app.middleware("http")
    async def local_origin(request: Request, call_next: Any) -> Any:
        origin = request.headers.get("origin", "")
        if origin and origin not in (
            f"http://127.0.0.1:{request.url.port}",
            f"http://localhost:{request.url.port}",
        ):
            return JSONResponse({"detail": "Origen externo no autorizado."}, status_code=403)
        if request.url.hostname not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse({"detail": "Acceso solo local."}, status_code=403)
        return await call_next(request)

    @app.post("/api/terminal/run")
    async def terminal_run(payload: CommandRequest) -> dict[str, Any]:
        if not payload.command.strip():
            raise HTTPException(400, "Escribe un comando.")
        workspace = SafeWorkspace(db.get_settings().workspace_path)
        return await execute_command(payload.command, str(workspace.root))


class SkillImportRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=524288)
    folder_path: str | None = Field(default=None, max_length=1024)
    name: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=160)


class SkillEnableRequest(BaseModel):
    enabled: bool


def register_skill_routes(app: Any) -> None:
    store = app.state.engine.skills_store
    bundled_dir = getattr(app.state, "bundled_skills_dir", None)

    def fail(exc: Exception, status: int = 400) -> None:
        raise HTTPException(status, str(exc)) from exc

    @app.get("/api/skills")
    async def skills_list() -> dict[str, Any]:
        skills = store.catalog()
        return {
            "skills": skills,
            "enabled_count": sum(1 for s in skills if s.get("enabled")),
            "max_enabled": MAX_ENABLED_SKILLS,
            "bundled": store.list_bundled(bundled_dir),
        }

    @app.post("/api/skills")
    async def skills_import(payload: SkillImportRequest) -> dict[str, Any]:
        try:
            if payload.folder_path and payload.folder_path.strip():
                sid = store.import_directory(
                    payload.folder_path.strip(),
                    name=payload.name,
                    description=payload.description,
                )
            elif payload.content is not None:
                sid = store.add(
                    payload.content,
                    payload.name,
                    description=payload.description,
                )
            else:
                raise HTTPException(422, "Debes enviar 'content' o 'folder_path'.")
            return {"ok": True, "id": sid, "skill": store.get(sid)}
        except (ValueError, OSError) as exc:
            fail(exc)

    @app.post("/api/skills/bundled/{slug}")
    async def skills_install_bundled(slug: str) -> dict[str, Any]:
        try:
            sid = store.install_bundled(bundled_dir, slug)
            return {"ok": True, "id": sid, "skill": store.get(sid)}
        except (ValueError, OSError) as exc:
            fail(exc)

    @app.put("/api/skills/{skill_id}")
    async def skills_enable(skill_id: str, payload: SkillEnableRequest) -> dict[str, Any]:
        try:
            updated = store.enable(skill_id, payload.enabled)
            return {"ok": True, "skill": updated}
        except (ValueError, OSError) as exc:
            fail(exc)

    @app.get("/api/skills/{skill_id}/read")
    async def skills_read(
        skill_id: str,
        file: str = Query("SKILL.md"),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        try:
            return store.read(skill_id, offset=offset, file=file, allow_disabled=True)
        except (ValueError, OSError) as exc:
            fail(exc)

    @app.delete("/api/skills/{skill_id}")
    async def skills_delete(skill_id: str) -> dict[str, Any]:
        try:
            store.delete(skill_id)
            return {"ok": True, "deleted": True, "id": skill_id}
        except (ValueError, OSError) as exc:
            fail(exc)
