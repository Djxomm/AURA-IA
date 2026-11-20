"""Servidor Web FastAPI con streaming SSE, API REST y archivos estáticos."""

from __future__ import annotations

import asyncio
import json
import os
import string
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import APP_NAME, __version__
from .agent import AgentEngine, ApprovalDecision, ApprovalRegistry
from .config import (
    HARDWARE_PROFILES,
    RECOMMENDED_MODELS,
    AppSettings,
    apply_hardware_profile,
    detect_local_hardware,
)
from .providers import LocalLLMClient
from .storage import Storage
from .workspace import SafeWorkspace, WorkspaceError, build_diff


STATIC_DIR = Path(__file__).resolve().parent / "static"
HEARTBEAT_SECONDS = 15.0


class SessionCreateRequest(BaseModel):
    title: str = "Nueva sesión"
    workspace_path: str | None = None


class WorkspaceSelectRequest(BaseModel):
    path: str
    session_id: str | None = None


class WorkspaceInspectRequest(BaseModel):
    path: str = Field(..., min_length=1)
    mode: str = "summary"
    max_items: int = Field(default=40, ge=1, le=200)


class ChatStreamRequest(BaseModel):
    mode: Literal["chat", "code"] = "code"
    session_id: str | None = None
    message: str = Field(..., min_length=1, max_length=24000)
    attached_files: list[str] = Field(default_factory=list)


class ProposalResolveRequest(BaseModel):
    approved: bool
    feedback: str = ""


def _list_windows_drives() -> list[str]:
    if os.name != "nt":
        return ["/"]
    drives: list[str] = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.exists(root):
            drives.append(root)
    return drives


def _setup_guides() -> dict[str, Any]:
    return {
        "legacy_i5_1gb": {
            "title": "Intel i5 1ra Gen + NVIDIA 1 GB (Sin AVX/AVX2)",
            "summary": (
                "Los procesadores Intel Core i5 de 1ra generación no tienen instrucciones AVX/AVX2. "
                "KoboldCpp con --noavx2 --noavx o llama-server (build SSE4.2) corren sin errores "
                "y permiten repartir capas en tu GPU NVIDIA de 1 GB."
            ),
            "commands": [
                {
                    "label": "KoboldCpp (recomendado sin AVX)",
                    "cmd": "koboldcpp.exe --model qwen2.5-coder-1.5b-instruct-q4_k_m.gguf --noavx2 --noavx --contextsize 2048 --threads 2 --gpulayers 8 --port 8080",
                },
                {
                    "label": "llama-server (llama.cpp CPU/GPU)",
                    "cmd": "llama-server.exe -m qwen2.5-coder-0.5b-instruct-q4_k_m.gguf -c 2048 -b 128 -t 2 -ngl 99 --port 8080",
                },
                {
                    "label": "Script asistente incluido",
                    "cmd": "iniciar_motor_legacy_i5.bat",
                },
            ],
        },
        "ollama": {
            "title": "Ollama (Windows)",
            "summary": "Motor automático con gestión de modelos GGUF mediante comandos simples.",
            "commands": [
                {"label": "1. Instalar Ollama", "cmd": "winget install Ollama.Ollama"},
                {"label": "2. Modelo ultra-ligero (cabe en 1 GB VRAM)", "cmd": "ollama pull qwen2.5-coder:0.5b"},
                {"label": "3. Modelo equilibrado (híbrido 1 GB + RAM)", "cmd": "ollama pull qwen2.5-coder:1.5b"},
            ],
        },
        "lmstudio": {
            "title": "LM Studio (Solo CPUs con AVX2)",
            "summary": "Requiere procesador con AVX2; en i5 1ra Gen usa KoboldCpp o llama-server.",
            "commands": [
                {"label": "Puerto API local por defecto", "cmd": "http://127.0.0.1:1234/v1"},
            ],
        },
    }


def create_app(
    storage: Storage | None = None,
    llm_client: LocalLLMClient | None = None,
    bundled_skills_dir: Path | None = None,
    model_manager: Any = None,
) -> FastAPI:
    """Construye la aplicación FastAPI con estado encapsulado para ejecución o pruebas."""
    db = storage or Storage()
    client = llm_client or LocalLLMClient()
    registry = ApprovalRegistry()
    engine = AgentEngine(storage=db, llm_client=client, approval_registry=registry)
    default_bundled = Path(__file__).resolve().parent.parent / "offline" / "skills"

    app = FastAPI(title=APP_NAME, version=__version__)
    app.state.storage = db
    app.state.llm_client = client
    app.state.registry = registry
    app.state.engine = engine
    app.state.model_manager = model_manager
    from .aura_api import register_aura_routes
    register_aura_routes(app, db)
    app.state.skills_store = engine.skills_store
    app.state.bundled_skills_dir = Path(bundled_skills_dir) if bundled_skills_dir else default_bundled
    from .desktop_api import register_desktop_routes, register_skill_routes
    register_desktop_routes(app, db)
    register_skill_routes(app)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def index_page() -> FileResponse:
        index_file = STATIC_DIR / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="Interfaz estática no encontrada.")
        return FileResponse(str(index_file))

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "app": APP_NAME, "version": __version__}

    @app.get("/api/providers/status")
    async def providers_status() -> dict[str, Any]:
        settings = db.get_settings()
        statuses = await client.detect_providers(
            settings.ollama_url,
            settings.llamacpp_url,
            settings.lmstudio_url,
        )
        providers_payload = {
            pid: {
                "id": st.id,
                "name": st.name,
                "url": st.url,
                "online": st.online,
                "models": st.models,
                "error": st.error,
            }
            for pid, st in statuses.items()
        }
        any_online = any(st.online for st in statuses.values())
        return {
            "any_online": any_online,
            "active_provider": settings.provider,
            "active_model": settings.model,
            "providers": providers_payload,
            "hardware": detect_local_hardware(),
            "hardware_profiles": HARDWARE_PROFILES,
            "recommended_models": RECOMMENDED_MODELS,
            "setup_guides": _setup_guides(),
        }

    @app.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        return db.get_settings().model_dump()

    @app.put("/api/settings")
    async def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
        current = db.get_settings()
        data = dict(payload)

        if "workspace_path" in data and data["workspace_path"]:
            candidate = Path(str(data["workspace_path"])).expanduser().resolve()
            if not candidate.exists() or not candidate.is_dir():
                raise HTTPException(
                    status_code=400,
                    detail=f"La carpeta seleccionada no existe: {data['workspace_path']}",
                )
            data["workspace_path"] = str(candidate)

        requested_profile = data.get("hardware_profile")
        apply_profile_flag = bool(data.pop("apply_profile", False))
        if requested_profile and requested_profile in HARDWARE_PROFILES:
            if apply_profile_flag or requested_profile != current.hardware_profile:
                keep_model = "model" in data and bool(data["model"])
                current = apply_hardware_profile(current, requested_profile, keep_model=keep_model)

        merged = current.model_dump()
        merged.update({k: v for k, v in data.items() if k in merged})
        try:
            updated = AppSettings.model_validate(merged)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Configuración inválida: {exc}") from exc

        db.save_settings(updated)
        return updated.model_dump()

    # ---------------- Workspace ----------------

    @app.get("/api/workspace/tree")
    async def workspace_tree(
        path: str = Query("."),
        depth: int = Query(3, ge=1, le=5),
    ) -> dict[str, Any]:
        settings = db.get_settings()
        try:
            ws = SafeWorkspace(settings.workspace_path)
            return ws.list_files(path=path, max_depth=depth, max_entries=300)
        except WorkspaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/workspace/file")
    async def workspace_file(
        path: str = Query(..., min_length=1),
        start_line: int = Query(1, ge=1),
        end_line: int = Query(1200, ge=1, le=5000),
    ) -> dict[str, Any]:
        settings = db.get_settings()
        try:
            ws = SafeWorkspace(settings.workspace_path)
            return ws.read_file(path, start_line=start_line, end_line=end_line)
        except WorkspaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/workspace/browse")
    async def workspace_browse(dir: str | None = Query(None)) -> dict[str, Any]:
        settings = db.get_settings()
        target_str = dir or settings.workspace_path
        target = Path(target_str).expanduser().resolve()
        if not target.exists() or not target.is_dir():
            target = Path(settings.workspace_path).expanduser().resolve()
        subdirs: list[dict[str, str]] = []
        try:
            for item in sorted(target.iterdir(), key=lambda p: p.name.lower()):
                if item.is_dir() and not item.name.startswith("$"):
                    subdirs.append({"name": item.name, "path": str(item)})
        except OSError as exc:
            raise HTTPException(status_code=403, detail=f"Sin permisos para leer {target}: {exc}") from exc

        parent = str(target.parent) if target.parent != target else None
        return {
            "current": str(target),
            "parent": parent,
            "drives": _list_windows_drives(),
            "directories": subdirs[:200],
        }

    @app.post("/api/workspace/select")
    async def workspace_select(req: WorkspaceSelectRequest) -> dict[str, Any]:
        try:
            ws = SafeWorkspace(req.path)
        except WorkspaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        settings = db.get_settings().model_copy(update={"workspace_path": str(ws.root)})
        db.save_settings(settings)
        if req.session_id:
            db.update_session(req.session_id, workspace_path=str(ws.root))
        return {
            "workspace_path": str(ws.root),
            "tree": ws.list_files(max_depth=3, max_entries=300),
        }

    @app.post("/api/workspace/inspect")
    async def workspace_inspect(req: WorkspaceInspectRequest) -> dict[str, Any]:
        from .binary_inspection import inspect_binary

        settings = db.get_settings()
        try:
            ws = SafeWorkspace(settings.workspace_path)
            return inspect_binary(ws, req.path)
        except WorkspaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ---------------- Sesiones ----------------

    @app.get("/api/sessions")
    async def list_sessions() -> dict[str, Any]:
        return {"sessions": db.list_sessions()}

    @app.post("/api/sessions")
    async def create_session(req: SessionCreateRequest | None = None) -> dict[str, Any]:
        settings = db.get_settings()
        ws_path = req.workspace_path if (req and req.workspace_path) else settings.workspace_path
        title = req.title if req else "Nueva sesión"
        session = db.create_session(
            title=title,
            workspace_path=ws_path,
            provider=settings.provider,
            model=settings.model,
        )
        return {"session": session}

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        session = db.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Sesión no encontrada.")
        messages = db.get_messages(session_id)
        changes = db.list_changes(session_id=session_id)
        return {"session": session, "messages": messages, "changes": changes}

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str) -> dict[str, Any]:
        deleted = db.delete_session(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Sesión no encontrada.")
        return {"deleted": True, "session_id": session_id}

    # ---------------- Chat SSE y Propuestas ----------------

    @app.post("/api/chat/stream")
    async def chat_stream(req: ChatStreamRequest) -> StreamingResponse:
        if registry.has_active_runs:
            raise HTTPException(409, "Ya hay una respuesta en curso. Espera o pulsa Detener.")
        if model_manager is not None and model_manager.status()["phase"] != "ready":
            raise HTTPException(409, "El modelo se está preparando. Consulta el estado en la pantalla de inicio o en Modelos.")
        settings = db.get_settings()
        session = db.get_session(req.session_id) if req.session_id else None
        if not session:
            session = db.create_session(
                title="Nueva sesión",
                workspace_path=settings.workspace_path,
                provider=settings.provider,
                model=settings.model,
                session_id=req.session_id,
            )
        session_id = session["id"]
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        cancel_event = registry.register_run(run_id)
        queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

        async def emit(event_name: str, data: dict[str, Any]) -> None:
            await queue.put((event_name, data))

        async def run_agent_task() -> None:
            try:
                await emit(
                    "run_started",
                    {
                        "run_id": run_id,
                        "session_id": session_id,
                        "provider": settings.provider,
                        "model": settings.model,
                        "hardware_profile": settings.hardware_profile,
                    },
                )
                if req.mode == "chat":
                    from .aura_api import conversation_turn
                    await conversation_turn(db, client, session_id, req.message, settings, emit)
                    return
                await engine.run_turn(
                    session_id=session_id,
                    user_message=req.message,
                    settings=settings,
                    attached_files=req.attached_files,
                    emit=emit,
                    cancel_event=cancel_event,
                    run_id=run_id,
                )
            except asyncio.CancelledError:
                db.add_message(session_id,"assistant","Respuesta detenida por el usuario.",metadata={"status":"cancelled"})
                raise
            except Exception as exc:
                error_message=f"No se pudo completar la respuesta: {exc}"
                db.add_message(session_id,"assistant",error_message,metadata={"status":"error"})
                await emit("error", {"message": error_message})
            finally:
                registry.cleanup_run(run_id)
                await queue.put(None)

        task = asyncio.create_task(run_agent_task())

        async def sse_generator():
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                    except asyncio.TimeoutError:
                        # Mantener vivo el canal durante prefill lento en CPU i5 o espera humana
                        yield ": keepalive\n\n"
                        continue
                    if item is None:
                        break
                    event_name, payload = item
                    data_obj = {"type": event_name, **payload}
                    encoded = json.dumps(data_obj, ensure_ascii=False)
                    yield f"event: {event_name}\ndata: {encoded}\n\n"
            finally:
                if not task.done():
                    registry.cancel_run(run_id)
                    task.cancel()
                    try:
                        await task
                    except BaseException:
                        pass

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/proposals/{proposal_id}/resolve")
    async def resolve_proposal(proposal_id: str, req: ProposalResolveRequest) -> dict[str, Any]:
        try:
            proposal = registry.resolve_proposal(
                proposal_id,
                ApprovalDecision(approved=req.approved, feedback=req.feedback),
            )
            return {
                "ok": True,
                "proposal_id": proposal.id,
                "approved": req.approved,
                "status": proposal.status,
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(run_id: str) -> dict[str, Any]:
        cancelled = registry.cancel_run(run_id)
        return {"ok": cancelled, "run_id": run_id}

    @app.get("/api/sessions/{session_id}/changes")
    async def list_session_changes(session_id: str) -> dict[str, Any]:
        changes = db.list_changes(session_id=session_id)
        enriched: list[dict[str, Any]] = []
        for ch in changes:
            item = dict(ch)
            diff_data = build_diff(
                item["file_path"],
                item.get("before_content"),
                item.get("after_content"),
            )
            item["hunks"] = diff_data["hunks"]
            enriched.append(item)
        return {"changes": enriched}

    @app.post("/api/changes/{change_id}/revert")
    async def revert_change(change_id: str) -> dict[str, Any]:
        try:
            updated = engine.revert_change(change_id)
            return {"ok": True, "change": updated}
        except WorkspaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.exception_handler(Exception)
    async def unhandled_exc_handler(_, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": f"Error interno: {exc}"})

    return app
