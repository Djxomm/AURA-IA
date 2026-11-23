"""Motor de agente local, registro de aprobaciones diff y reversión de cambios."""

from __future__ import annotations

import asyncio
import json
import tempfile
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from .config import AppSettings
from .providers import LocalLLMClient, ProviderError, ToolCall, ProviderResponse
from .skills import SkillStore
from .storage import Storage
from .tools import EXEC_TOOLS, READ_TOOLS, TOOL_DEFINITIONS, WRITE_TOOLS, build_system_prompt, estimate_tokens
from .workspace import SafeWorkspace, WorkspaceError


EventEmitter = Callable[[str, dict[str, Any]], Awaitable[None] | None]
ApprovalHandler = Callable[["PendingProposal"], Awaitable["ApprovalDecision"]]


@dataclass
class ApprovalDecision:
    """Decisión humana sobre una propuesta de cambio en disco."""

    approved: bool
    feedback: str = ""


@dataclass
class PendingProposal:
    """Propuesta de modificación con diff completo previo a escribir en disco."""

    id: str
    session_id: str
    workspace_path: str
    file_path: str
    action: str
    reason: str
    original_content: str | None
    proposed_content: str | None
    base_hash: str
    unified_diff: str
    hunks: list[dict[str, Any]]
    added_lines: int
    removed_lines: int
    status: str = "pending"
    feedback: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        """Serialización segura para UI y SSE (incluye preview acotado de contenido si aplica)."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "workspace_path": self.workspace_path,
            "file_path": self.file_path,
            "action": self.action,
            "reason": self.reason,
            "unified_diff": self.unified_diff,
            "hunks": self.hunks,
            "added_lines": self.added_lines,
            "removed_lines": self.removed_lines,
            "status": self.status,
            "feedback": self.feedback,
        }


class ApprovalRegistry:
    """Registro en memoria de propuestas esperando confirmación y runs activos."""

    def __init__(self) -> None:
        self._proposals: dict[str, tuple[PendingProposal, asyncio.Future[ApprovalDecision]]] = {}
        self._runs: dict[str, tuple[asyncio.Event, set[str]]] = {}

    @property
    def has_active_runs(self):
        return bool(self._runs)

    def register_run(self, run_id: str) -> asyncio.Event:
        ev = asyncio.Event()
        self._runs[run_id] = (ev, set())
        return ev

    def cleanup_run(self, run_id: str) -> None:
        info = self._runs.pop(run_id, None)
        if not info:
            return
        _, prop_ids = info
        for pid in prop_ids:
            pair = self._proposals.pop(pid, None)
            if pair:
                _, fut = pair
                if not fut.done():
                    fut.set_result(ApprovalDecision(approved=False, feedback="Ejecución finalizada."))

    def cancel_run(self, run_id: str) -> bool:
        info = self._runs.get(run_id)
        if not info:
            return False
        ev, prop_ids = info
        ev.set()
        for pid in list(prop_ids):
            pair = self._proposals.get(pid)
            if pair:
                prop, fut = pair
                if not fut.done():
                    prop.status = "rejected"
                    prop.feedback = "Cancelado por el usuario."
                    fut.set_result(ApprovalDecision(approved=False, feedback="Cancelado por el usuario."))
        return True

    def register_proposal(
        self,
        proposal: PendingProposal,
        *,
        run_id: str | None = None,
    ) -> asyncio.Future[ApprovalDecision]:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[ApprovalDecision] = loop.create_future()
        self._proposals[proposal.id] = (proposal, fut)
        if run_id and run_id in self._runs:
            self._runs[run_id][1].add(proposal.id)
        return fut

    def get_proposal(self, proposal_id: str) -> PendingProposal | None:
        pair = self._proposals.get(proposal_id)
        return pair[0] if pair else None

    def resolve_proposal(self, proposal_id: str, decision: ApprovalDecision) -> PendingProposal:
        pair = self._proposals.get(proposal_id)
        if not pair:
            raise KeyError(f"Propuesta no encontrada o ya expirada: {proposal_id}")
        proposal, fut = pair
        if fut.done():
            return proposal
        proposal.status = "approved" if decision.approved else "rejected"
        proposal.feedback = decision.feedback.strip()
        fut.set_result(decision)
        return proposal


async def _emit(emitter: EventEmitter | None, event: str, data: dict[str, Any]) -> None:
    if not emitter:
        return
    res = emitter(event, data)
    if asyncio.iscoroutine(res):
        await res


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    kept = text[:max_chars]
    omitted = len(text) - max_chars
    return f"{kept}\n... [+{omitted} caracteres omitidos para ahorrar contexto]"


def _normalize_action(tool_name: str) -> str:
    return {
        "create_file": "create",
        "edit_file": "edit",
        "write_file": "write",
        "delete_file": "delete",
    }[tool_name]


class AgentEngine:
    """Orquestador del ciclo de razonamiento, herramientas y confirmación humana."""

    def __init__(
        self,
        storage: Storage,
        llm_client: LocalLLMClient,
        approval_registry: ApprovalRegistry,
        skills_store: SkillStore | None = None,
    ) -> None:
        if skills_store is not None:
            self.skills_store = skills_store
        elif storage.db_path == ":memory:":
            self.skills_store = SkillStore(Path(tempfile.mkdtemp(prefix="codigolocal_skills_")))
        else:
            self.skills_store = SkillStore(Path(storage.db_path).parent / "skills")
        self.storage = storage
        self.llm_client = llm_client
        self.approval_registry = approval_registry

    def _build_attached_context(
        self,
        workspace: SafeWorkspace,
        attached_files: list[str],
        settings: AppSettings,
    ) -> str:
        if not attached_files:
            return ""
        chunks: list[str] = []
        for rel in attached_files[:4]:
            try:
                info = workspace.read_file(
                    rel,
                    start_line=1,
                    end_line=settings.max_read_lines,
                )
                body = _truncate_text(info["numbered_excerpt"], settings.max_tool_output_chars)
                chunks.append(
                    f"[Archivo adjunto: {info['path']} (líneas {info['start_line']}-{info['end_line']} de {info['total_lines']})]\n{body}"
                )
            except WorkspaceError as exc:
                chunks.append(f"[No se pudo adjuntar {rel}: {exc}]")
        return "\n\n".join(chunks)

    def _execute_read_tool(
        self,
        workspace: SafeWorkspace,
        tc: ToolCall,
        settings: AppSettings,
    ) -> tuple[bool, str, str]:
        args = tc.arguments
        try:
            if tc.name == "inspect_binary":
                from .binary_inspection import inspect_binary
                result = inspect_binary(workspace, str(args.get("path", "")))
                return True, _truncate_text(json.dumps(result, ensure_ascii=False), settings.max_tool_output_chars), "Inspección binaria sin ejecutar el archivo"
            if tc.name == "inspect_artifact":
                from .artifact_inspect import inspect_artifact
                result = inspect_artifact(
                    workspace,
                    str(args.get("path") or ""),
                    mode=str(args.get("mode") or "summary"),
                    max_items=int(args.get("max_items") or 30),
                )
                return True, _truncate_text(json.dumps(result, ensure_ascii=False), settings.max_tool_output_chars), f"Inspeccionó {result['path']}"
            if tc.name == "read_skill":
                from .skills import read_chunk_for_context
                chunk = read_chunk_for_context(settings.num_ctx)
                result = self.skills_store.read(
                    str(args.get("id", "")),
                    int(args.get("offset", 0)),
                    file=str(args.get("file") or "SKILL.md"),
                    query=str(args.get("query") or ""),
                    chunk_chars=chunk,
                )
                return True, _truncate_text(json.dumps(result, ensure_ascii=False), max(settings.max_tool_output_chars, chunk + 600)), "Leyó habilidad: " + result["name"]
            if tc.name == "list_files":
                res = workspace.list_files(
                    path=str(args.get("path") or "."),
                    max_depth=min(5, max(1, int(args.get("max_depth") or 3))),
                    max_entries=160 if settings.compact_prompt else 250,
                )
                output = _truncate_text(res["text"], settings.max_tool_output_chars)
                summary = f"Listó {len(res['entries'])} elementos en {res['base']}"
                return True, output, summary

            if tc.name == "read_file":
                path = str(args.get("path") or "")
                start = max(1, int(args.get("start_line") or 1))
                requested_end = args.get("end_line")
                max_span = settings.max_read_lines
                end = int(requested_end) if requested_end is not None else (start + max_span - 1)
                if end - start + 1 > max_span:
                    end = start + max_span - 1
                res = workspace.read_file(path, start_line=start, end_line=end)
                header = (
                    f"Archivo: {res['path']} (líneas {res['start_line']}-{res['end_line']} "
                    f"de {res['total_lines']})"
                )
                body = _truncate_text(res["numbered_excerpt"], settings.max_tool_output_chars)
                footer = (
                    f"\n(Continúa desde línea {res['end_line'] + 1})"
                    if res["truncated"]
                    else ""
                )
                return True, f"{header}\n{body}{footer}", f"Leyó {res['path']} ({res['start_line']}-{res['end_line']})"

            if tc.name == "search_in_files":
                query = str(args.get("query") or "")
                matches = workspace.search_in_files(
                    query=query,
                    path=str(args.get("path") or "."),
                    file_pattern=str(args.get("file_pattern") or "*"),
                    use_regex=bool(args.get("use_regex", False)),
                    max_results=30 if settings.compact_prompt else 50,
                )
                if not matches:
                    return True, f"Sin coincidencias para '{query}'.", f"Buscó '{query}' (0 resultados)"
                lines = [f"{m['file']}:{m['line']}: {m['text']}" for m in matches]
                output = _truncate_text("\n".join(lines), settings.max_tool_output_chars)
                return True, output, f"Buscó '{query}' ({len(matches)} coincidencias)"

            if tc.name == "get_file_info":
                info = workspace.get_file_info(str(args.get("path") or ""))
                return True, json.dumps(info, ensure_ascii=False), f"Info de {info['path']}"

            if tc.name == "web_search":
                from .web_research import web_search
                result = web_search(str(args.get("query") or ""), max_results=int(args.get("max_results") or 5))
                return True, _truncate_text(json.dumps(result, ensure_ascii=False), max(settings.max_tool_output_chars, 3200)), f"Buscó en web '{result['query'][:40]}' ({result['count']} resultados)"

            if tc.name == "fetch_url":
                from .web_research import fetch_url
                result = fetch_url(str(args.get("url") or ""), max_chars=int(args.get("max_chars") or 4000))
                return True, _truncate_text(json.dumps(result, ensure_ascii=False), max(settings.max_tool_output_chars, 4200)), f"Leyó documentación web: {result['url'][:60]}"

            if tc.name == "pc_inspect":
                from .pc_control import pc_inspect
                result = pc_inspect(
                    workspace,
                    str(args.get("action") or ""),
                    query=str(args.get("query") or ""),
                    output_path=str(args.get("output_path") or "capturas/pantalla.png"),
                    limit=int(args.get("limit") or 25),
                )
                return True, _truncate_text(json.dumps(result, ensure_ascii=False), max(settings.max_tool_output_chars, 3200)), f"Inspeccionó PC ({result['action']})"

            return False, f"Herramienta desconocida: {tc.name}", f"Herramienta inválida {tc.name}"
        except (WorkspaceError, ValueError, TypeError, OSError, KeyError) as exc:
            return False, f"Error en {tc.name}: {exc}", f"Error en {tc.name}: {exc}"

    def _prepare_proposal(
        self,
        *,
        session_id: str,
        workspace: SafeWorkspace,
        tc: ToolCall,
    ) -> PendingProposal:
        args = tc.arguments
        path = str(args.get("path") or "").strip()
        reason = str(args.get("reason") or "Modificación propuesta por el agente.").strip()
        action = _normalize_action(tc.name)

        if tc.name == "create_file":
            orig, prop, base_hash, diff = workspace.prepare_create(path, str(args.get("content") or ""))
        elif tc.name == "edit_file":
            orig, prop, base_hash, diff = workspace.prepare_edit(
                path,
                str(args.get("old_text") or ""),
                str(args.get("new_text") or ""),
            )
        elif tc.name == "write_file":
            orig, prop, base_hash, diff = workspace.prepare_write(path, str(args.get("content") or ""))
        elif tc.name == "delete_file":
            orig, prop, base_hash, diff = workspace.prepare_delete(path)
        else:
            raise WorkspaceError(f"Acción de escritura no soportada: {tc.name}")

        from .code_preservation import validate_agent_change
        try:validate_agent_change(path,orig,prop,whole_file=tc.name=='write_file')
        except ValueError as error:raise WorkspaceError(str(error)) from error
        rel_path = workspace.to_rel_posix(workspace.resolve_safe_path(path, allow_write=True))
        return PendingProposal(
            id=f"prop_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            workspace_path=str(workspace.root),
            file_path=rel_path,
            action=action,
            reason=reason,
            original_content=orig,
            proposed_content=prop,
            base_hash=base_hash,
            unified_diff=diff["unified_diff"],
            hunks=diff["hunks"],
            added_lines=diff["added"],
            removed_lines=diff["removed"],
        )

    async def run_turn(self, **kwargs):
        from .task_coordinator import TaskCoordinator
        if not hasattr(self, 'coordinator'):
            path = ':memory:' if self.storage.db_path == ':memory:' else str(Path(self.storage.db_path).with_name('qbitx-tasks.sqlite'))
            self.coordinator = TaskCoordinator(path)
        session = kwargs['session_id']
        project = str(Path(kwargs['settings'].workspace_path).resolve())
        state = self.coordinator.begin(session, project, kwargs['user_message'])
        emitter = kwargs.get('emit')
        async def progress(event, payload):
            if event in ('proposal_resolved', 'tool_result', 'error'):
                self.coordinator.event(session, project, state, event, payload)
            await _emit(emitter, event, payload)
        await _emit(emitter, 'task_progress', {'message': 'QbitX · Recuperando objetivo y revisando el proyecto', 'state': state})
        kwargs['emit'] = progress
        kwargs['_task_context'] = self.coordinator.context(state)
        kwargs['_task_state'] = state
        try:
            result = await self._run_turn(**kwargs)
            state['status'] = 'review_pending' if state['files'] and result.get('status') == 'done' else result.get('status', 'incomplete')
            state['last_result'] = str(result.get('content') or result.get('error') or '')[:1400]
            self.coordinator.save(session, project, state)
            label={'review_pending':'Archivos guardados; revisión pendiente','done':'Turno terminado','incomplete':'Avance guardado; puedes continuar','error':'Requiere atención','cancelled':'Detenido por el usuario'}.get(state['status'],'Avance guardado')
            await _emit(emitter, 'task_progress', {'message': 'QbitX · '+label, 'state': state})
            return result
        except BaseException:
            state['status'] = 'interrupted'
            self.coordinator.save(session, project, state)
            raise

    async def _run_turn(
        self,
        *,
        session_id: str,
        user_message: str,
        settings: AppSettings,
        attached_files: list[str] | None = None,
        emit: EventEmitter | None = None,
        approval_handler: ApprovalHandler | None = None,
        cancel_event: asyncio.Event | None = None,
        run_id: str | None = None,
        reference_context: str = "",
        _task_context: str = "",
        _task_state: dict | None = None,
    ) -> dict[str, Any]:
        """Ejecuta un turno completo del agente con streaming, herramientas y aprobación de diffs."""
        try:
            workspace = SafeWorkspace(settings.workspace_path)
        except WorkspaceError as exc:
            await _emit(emit, "error", {"message": str(exc)})
            return {"status": "error", "error": str(exc)}

        from .code_artifacts import file_task_requested, task_brief, expected_language, code_proposal, validate_code, requested_code_path
        task_history = self.storage.get_messages(session_id, limit=60)
        creating = file_task_requested(user_message, task_history)
        brief = task_brief(task_history, user_message) if creating else ''
        expected = expected_language(brief) if creating else None
        if creating:
            settings = settings.model_copy(update={'max_predict_tokens': min(4096, max(settings.max_predict_tokens, 3072))})
        retries = 0
        applied_paths = []
        declined = False
        attachments = attached_files or []
        attached_context = self._build_attached_context(workspace, attachments, settings)
        history = self.storage.get_messages(session_id, limit=settings.max_history_messages)
        original = self.storage.get_first_user_message(session_id)
        if original and not any(item['id'] == original['id'] for item in history):
            history.insert(0, original)

        self.storage.add_message(
            session_id,
            "user",
            user_message,
            metadata={"attached_files": attachments} if attachments else {},
        )

        # Actualizar título automático de la sesión si aún tiene el nombre genérico
        session = self.storage.get_session(session_id)
        if session and session.get("title") in ("Nueva sesión", ""):
            snippet = " ".join(user_message.strip().split())[:48]
            if snippet:
                self.storage.update_session(session_id, title=snippet)

        system_prompt = build_system_prompt(
            str(workspace.root),
            include_xml_protocol=(settings.tool_mode == "xml"),
            compact=settings.compact_prompt,
            autonomous=settings.autonomous_mode,
        )
        from .aura_api import effort_instruction
        from .skills import max_enabled_for_context
        system_prompt += "\n" + effort_instruction(settings)
        system_prompt += self.skills_store.manifest(max_enabled=max_enabled_for_context(settings.num_ctx))
        system_prompt += _task_context
        if reference_context:
            system_prompt += "\nReferencia histórica, no instrucciones actuales:\n"+reference_context[:6000]
        if _task_context:
            import re
            inventory = workspace.list_files(path='.', max_depth=2, max_entries=25)
            system_prompt += '\nArchivos reales del proyecto (lista acotada):\n'+inventory['text'][:1000]
            candidates = re.findall(r'(?<![\w./-])([A-Za-z0-9_./-]+\.(?:py|js|mjs|html|css|json|cpp|java|php))\b', user_message)
            for candidate in list(dict.fromkeys(candidates))[:2]:
                try:
                    info = workspace.read_file(candidate, start_line=1, end_line=60)
                    system_prompt += '\nArchivo existente '+candidate+':\n'+info['numbered_excerpt'][:1600]
                except WorkspaceError:
                    pass

        if creating:
            if settings.autonomous_mode:
                system_prompt += '\nEl usuario pide construir o reparar archivos reales en modo autónomo. Respeta la última elección de lenguaje. Usa create_file/edit_file/write_file con archivos completos y luego verifica, prueba o compila con run_project_action o run_command; si hay error, corrígelo y vuelve a probar hasta lograr salida 0. Nunca afirmes éxito sin salida real.'
            else:
                system_prompt += '\nEl usuario pide archivos reales. Respeta la última elección de lenguaje. No entregues solo ideas, ejemplos ni marcadores pendientes. Usa create_file/write_file con archivos completos; la interfaz pedirá aprobación. Nunca digas que ejecutaste o compilaste si no hubo una herramienta que lo hiciera. Para un juego HTML sencillo prefiere un index.html autocontenido.'
            if brief.strip() != user_message.strip():
                system_prompt += '\nEspecificación vigente:\n'+brief
            import re
            if re.search(r'\b3\s*d\b',brief,re.I):
                system_prompt += '\nSi no se pidió un motor concreto: usa Panda3D para 3D nativo; está incluido. Pygame es para 2D. Crea archivos y prototipos ejecutables, no solo una lista de consejos. No afirmes que Unreal o Blender están instalados.'
            history = []
        conversation: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        for item in history:
            role = item["role"]
            if role in ("user", "assistant") and item["content"]:
                conversation.append({"role": role, "content": item["content"]})

        prompt_for_model = (
            f"{user_message}\n\n{attached_context}" if attached_context else user_message
        )
        conversation.append({"role": "user", "content": prompt_for_model})

        system_without_checkpoint = system_prompt.replace(_task_context, "") if _task_context else system_prompt
        total_tokens = 0
        total_elapsed_ms = 0
        last_tok_per_sec = 0.0
        last_mode = settings.tool_mode
        tool_traces: list[dict[str, Any]] = []
        executed_actions: list[dict[str, Any]] = []
        final_content = ""
        effective_max_steps = max(settings.max_steps, 16) if settings.autonomous_mode else settings.max_steps

        for step in range(1, effective_max_steps + 1):
            if creating and declined:
                message = 'No apliqué cambios: rechazaste la propuesta.'
                self.storage.add_message(session_id, 'assistant', message, metadata={'tools':tool_traces})
                await _emit(emit, 'done', {'content':message,'steps':step-1})
                return {'status':'done','content':message,'steps':step-1}
            promoted = False
            if cancel_event and cancel_event.is_set():
                await _emit(emit, "error", {"message": "Generación cancelada por el usuario."})
                return {"status": "cancelled", "content": final_content}

            from .task_coordinator import bounded_conversation, TaskCoordinator
            if _task_state is not None:
                conversation[0]["content"] = system_without_checkpoint + TaskCoordinator.context(_task_state)
            conversation = bounded_conversation(conversation, max(1000, settings.num_ctx - 800))
            est_tokens = estimate_tokens(conversation)
            await _emit(
                emit,
                "context_stats",
                {
                    "estimated_tokens": est_tokens,
                    "num_ctx": settings.num_ctx,
                    "step": step,
                    "max_steps": settings.max_steps,
                },
            )

            async def _on_tok(delta: str) -> None:
                if cancel_event and cancel_event.is_set():
                    raise asyncio.CancelledError()
                await _emit(emit, "token", {"text": delta, "step": step})

            try:
                from .game_starter import racing_starter
                starter = racing_starter(brief, workspace, getattr(self.llm_client, 'runtime', None)) if creating and step == 1 else None
                if starter:
                    promoted = True
                    response = ProviderResponse(content='Prototipo Panda3D de carreras a partir de una plantilla local; revisa el archivo antes de guardarlo.', tool_calls=[ToolCall('starter_'+uuid.uuid4().hex[:8], 'create_file', starter)])
                else:
                    response = await self.llm_client.stream_chat(
                        settings=settings,
                        messages=conversation,
                        tools=TOOL_DEFINITIONS,
                        on_token=_on_tok,
                    )
            except asyncio.CancelledError:
                await _emit(emit, "error", {"message": "Generación cancelada por el usuario."})
                return {"status": "cancelled", "content": final_content}
            except ProviderError as exc:
                await _emit(emit, "error", {"message": str(exc)})
                return {"status": "error", "error": str(exc)}
            except Exception as exc:
                msg = f"Error inesperado del motor local: {exc}"
                await _emit(emit, "error", {"message": msg})
                return {"status": "error", "error": msg}

            total_tokens += response.tokens_generated
            total_elapsed_ms += response.elapsed_ms
            if response.tok_per_sec:
                last_tok_per_sec = response.tok_per_sec
            last_mode = response.used_tool_mode

            if creating and not response.tool_calls and not applied_paths and not declined:
                try:
                    name, arguments = code_proposal(response.content, expected, workspace, getattr(self.llm_client, 'runtime', None), requested_code_path(brief, expected))
                    promoted = True
                    response.tool_calls = [ToolCall(id='artifact_'+uuid.uuid4().hex[:10], name=name, arguments=arguments)]
                    await _emit(emit, 'stream_clean', {'content':'Preparando el archivo completo para tu revisión.', 'step':step})
                except (ValueError, SyntaxError, OSError, subprocess.TimeoutExpired) as error:
                    if retries < 2 and step < effective_max_steps:
                        retries += 1
                        await _emit(emit, 'stream_clean', {'content':'La respuesta no produjo un archivo completo. Reintentando la creación ('+str(retries)+'/2).', 'step':step})
                        conversation = [conversation[0], {'role':'user','content':brief+'\nCORRECCIÓN: '+str(error)+'\nEntrega UN archivo completo en '+str(expected or 'el lenguaje solicitado')+'. Usa create_file con JSON válido, o un único bloque de código completo. Sin explicaciones, sin puntos suspensivos y sin repetir fragmentos anteriores.'}]
                        continue
                    message = 'No creé archivos: el modelo no produjo código completo y válido para esta petición. '+str(error)+' Puedes dividir la tarea o elegir un modelo más capaz. No se ejecutó ni compiló ningún juego.'
                    self.storage.add_message(session_id, 'assistant', message, metadata={'status':'incomplete','tools':tool_traces})
                    await _emit(emit, 'done', {'content':message,'status':'incomplete','steps':step})
                    return {'status':'incomplete','content':message,'steps':step}
            if not response.tool_calls:
                final_content = response.content or "(Sin respuesta de texto del modelo)"
                if creating and applied_paths and not executed_actions:
                    final_content = 'Archivos guardados con tu aprobación: '+', '.join(dict.fromkeys(applied_paths))+'. La revisión estática no sustituye probar el proyecto. No se ejecutó ni compiló automáticamente; usa Verificar, Ejecutar o Compilar en AURAX.'
                elif creating and declined:
                    final_content = 'No apliqué cambios: rechazaste la propuesta.' 
                self.storage.add_message(
                    session_id,
                    "assistant",
                    final_content,
                    metadata={
                        "tokens_generated": total_tokens,
                        "elapsed_ms": total_elapsed_ms,
                        "tok_per_sec": last_tok_per_sec,
                        "tool_mode": last_mode,
                        "tools": tool_traces,
                    },
                )
                await _emit(
                    emit,
                    "done",
                    {
                        "content": final_content,
                        "tokens_generated": total_tokens,
                        "elapsed_ms": total_elapsed_ms,
                        "tok_per_sec": last_tok_per_sec,
                        "used_tool_mode": last_mode,
                        "steps": step,
                    },
                )
                return {
                    "status": "done",
                    "content": final_content,
                    "tokens_generated": total_tokens,
                    "elapsed_ms": total_elapsed_ms,
                    "tok_per_sec": last_tok_per_sec,
                    "steps": step,
                }

            # Si el modelo emitió bloques XML/fenced sin texto útil, limpiamos el buffer temporal en UI
            if response.used_tool_mode == "xml" and ("<tool_call>" in response.raw_content or "```tool_call" in response.raw_content):
                await _emit(emit, "stream_clean", {"content": response.content, "step": step})

            assistant_tool_calls_payload = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in response.tool_calls
            ]
            conversation.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": assistant_tool_calls_payload,
                }
            )

            for tc in response.tool_calls:
                if cancel_event and cancel_event.is_set():
                    await _emit(emit, "error", {"message": "Ejecución cancelada por el usuario."})
                    return {"status": "cancelled", "content": final_content}

                if tc.name in READ_TOOLS:
                    await _emit(
                        emit,
                        "tool_start",
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments},
                    )
                    if tc.name in ("web_search", "fetch_url", "pc_inspect"):
                        ok, tool_output, summary = await asyncio.to_thread(self._execute_read_tool, workspace, tc, settings)
                    else:
                        ok, tool_output, summary = self._execute_read_tool(workspace, tc, settings)
                    tool_traces.append({"name": tc.name, "ok": ok, "summary": summary})
                    await _emit(
                        emit,
                        "tool_result",
                        {"id": tc.id, "name": tc.name, "ok": ok, "summary": summary},
                    )
                    conversation.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.name,
                            "content": tool_output,
                        }
                    )
                    continue

                if tc.name in WRITE_TOOLS:
                    await _emit(
                        emit,
                        "tool_start",
                        {"id": tc.id, "name": tc.name, "arguments": {"path": tc.arguments.get("path")}},
                    )
                    try:
                        proposal = self._prepare_proposal(
                            session_id=session_id,
                            workspace=workspace,
                            tc=tc,
                        )
                        if proposal.proposed_content is not None and proposal.action in ('create','write','edit'):
                            try:
                                validate_code(proposal.file_path, proposal.proposed_content, expected if creating else None, getattr(self.llm_client, 'runtime', None))
                            except (ValueError, SyntaxError, OSError, subprocess.TimeoutExpired) as error:
                                raise WorkspaceError(str(error)) from error
                    except WorkspaceError as exc:
                        err_text = f"No se pudo preparar el cambio en {tc.name}: {exc}"
                        tool_traces.append({"name": tc.name, "ok": False, "summary": err_text})
                        await _emit(
                            emit,
                            "tool_result",
                            {"id": tc.id, "name": tc.name, "ok": False, "summary": err_text},
                        )
                        conversation.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "name": tc.name,
                                "content": err_text,
                            }
                        )
                        continue

                    # Registrar en DB como pendiente y esperar confirmación humana
                    self.storage.add_change_record(
                        change_id=proposal.id,
                        session_id=session_id,
                        workspace_path=proposal.workspace_path,
                        file_path=proposal.file_path,
                        action=proposal.action,
                        reason=proposal.reason,
                        before_content=proposal.original_content,
                        after_content=proposal.proposed_content,
                        unified_diff=proposal.unified_diff,
                        added_lines=proposal.added_lines,
                        removed_lines=proposal.removed_lines,
                        status="pending",
                    )
                    await _emit(emit, "proposal", proposal.to_public_dict())

                    if settings.autonomous_mode and tc.name != "delete_file":
                        decision = ApprovalDecision(
                            approved=True,
                            feedback="Aplicado automáticamente en modo constructor.",
                        )
                    elif approval_handler is not None:
                        decision = await approval_handler(proposal)
                    else:
                        fut = self.approval_registry.register_proposal(proposal, run_id=run_id)
                        decision = await fut

                    if decision.approved:
                        try:
                            workspace.apply_change(
                                proposal.file_path,
                                proposal.action,
                                proposal.proposed_content,
                                proposal.base_hash,
                            )
                            proposal.status = "applied"
                            applied_paths.append(proposal.file_path)
                            self.storage.resolve_change_record(
                                proposal.id,
                                status="applied",
                                feedback=decision.feedback,
                            )
                            msg_to_llm = (
                                f"Cambio aprobado y aplicado correctamente en '{proposal.file_path}' "
                                f"(+{proposal.added_lines}/-{proposal.removed_lines})."
                            )
                            summary = f"Aplicado en {proposal.file_path}"
                            ok_flag = True
                        except WorkspaceError as exc:
                            proposal.status = "error"
                            proposal.feedback = str(exc)
                            self.storage.resolve_change_record(
                                proposal.id,
                                status="error",
                                feedback=str(exc),
                            )
                            msg_to_llm = f"Error al aplicar cambio en '{proposal.file_path}': {exc}"
                            summary = msg_to_llm
                            ok_flag = False
                    else:
                        proposal.status = "rejected"
                        declined = not bool(decision.feedback.strip())
                        proposal.feedback = decision.feedback
                        self.storage.resolve_change_record(
                            proposal.id,
                            status="rejected",
                            feedback=decision.feedback,
                        )
                        fb_note = f" Comentario del usuario: {decision.feedback}" if decision.feedback else ""
                        msg_to_llm = (
                            f"El usuario RECHAZÓ el cambio propuesto en '{proposal.file_path}'.{fb_note} "
                            "No se modificó el archivo. Propón una alternativa o pregunta qué prefiere."
                        )
                        summary = f"Rechazado: {proposal.file_path}"
                        ok_flag = False

                    tool_traces.append({"name": tc.name, "ok": ok_flag, "summary": summary})
                    await _emit(
                        emit,
                        "proposal_resolved",
                        {
                            "id": proposal.id,
                            "file_path": proposal.file_path,
                            "action": proposal.action,
                            "status": proposal.status,
                            "feedback": proposal.feedback,
                        },
                    )
                    await _emit(
                        emit,
                        "tool_result",
                        {"id": tc.id, "name": tc.name, "ok": ok_flag, "summary": summary},
                    )
                    conversation.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.name,
                            "content": msg_to_llm,
                        }
                    )
                    continue

                if tc.name in EXEC_TOOLS:
                    from .command_exec import (
                        command_requires_approval,
                        execute_project_action,
                        execute_workspace_command,
                        validate_command,
                    )
                    from .image_studio import edit_image as studio_edit_image
                    from .image_studio import generate_image as studio_generate_image
                    from .pc_control import describe_pc_action, execute_pc_control

                    args = tc.arguments
                    reason = str(args.get("reason") or "Verificación, prueba, compilación, imagen o acción de PC solicitada por el agente.").strip()
                    runtime_dir = getattr(self.llm_client, "runtime", None)
                    await _emit(
                        emit,
                        "tool_start",
                        {"id": tc.id, "name": tc.name, "arguments": args},
                    )
                    proposal_action = "exec"
                    requires_user_approval = not settings.autonomous_mode
                    pc_act = ""
                    try:
                        if tc.name == "run_command":
                            cmd_preview = validate_command(str(args.get("command") or ""))
                            action_label = "command"
                            target_label = "."
                            timeout_sec = int(args.get("timeout") or 120)
                            requires_user_approval = (not settings.autonomous_mode) or command_requires_approval(cmd_preview)
                        elif tc.name == "pc_control":
                            pc_act = str(args.get("action") or "").strip().lower()
                            cmd_preview = describe_pc_action(pc_act, args)
                            action_label = f"pc:{pc_act}"
                            target_label = str(args.get("target") or pc_act)
                            timeout_sec = 60
                            proposal_action = "pc_control"
                            requires_user_approval = True
                        elif tc.name == "generate_image":
                            out_p = str(args.get("output_path") or "").strip()
                            workspace.resolve_safe_path(out_p, allow_write=True)
                            cmd_preview = f"generate_image({out_p}, prompt={str(args.get('prompt') or '')[:80]})"
                            action_label = "generate_image"
                            target_label = out_p
                            timeout_sec = 300
                        elif tc.name == "edit_image":
                            in_p = str(args.get("input_path") or "").strip()
                            out_p = str(args.get("output_path") or "").strip()
                            workspace.resolve_safe_path(in_p)
                            workspace.resolve_safe_path(out_p, allow_write=True)
                            cmd_preview = f"edit_image({in_p} -> {out_p})"
                            action_label = "edit_image"
                            target_label = out_p
                            timeout_sec = 300
                        else:
                            act_name = str(args.get("action") or "").strip().lower()
                            target_arg = str(args.get("path") or "").strip() or None
                            if target_arg and target_arg != ".":
                                workspace.resolve_safe_path(target_arg)
                            cmd_preview = f"run_project_action({act_name}" + (f", {target_arg}" if target_arg else "") + ")"
                            action_label = act_name
                            target_label = target_arg or "."
                            timeout_sec = 300
                    except (WorkspaceError, ValueError, TypeError) as exc:
                        err_text = f"No se pudo ejecutar {tc.name}: {exc}"
                        tool_traces.append({"name": tc.name, "ok": False, "summary": err_text})
                        await _emit(emit, "tool_result", {"id": tc.id, "name": tc.name, "ok": False, "summary": err_text})
                        conversation.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": err_text})
                        continue

                    if not requires_user_approval:
                        decision = ApprovalDecision(approved=True, feedback="Ejecutado en modo constructor autónomo.")
                    else:
                        approval_reason = reason
                        if settings.autonomous_mode and tc.name == "pc_control":
                            approval_reason = f"{reason} (Acción directa sobre la PC: requiere tu aprobación de 1 clic.)"
                        elif settings.autonomous_mode and tc.name == "run_command":
                            from .android_tools import is_bootloader_or_flash_command
                            if is_bootloader_or_flash_command(cmd_preview):
                                approval_reason = f"{reason} (Modificación de bootloader/particiones o Custom ROM: verifica modelo exacto, respaldo EFS, ranura activa y batería antes de aceptar.)"
                            else:
                                approval_reason = f"{reason} (Comando sensible: instala software, borra archivos, cierra procesos o altera remotos.)"
                        exec_proposal = PendingProposal(
                            id=f"exec_{uuid.uuid4().hex[:12]}",
                            session_id=session_id,
                            workspace_path=str(workspace.root),
                            file_path=target_label,
                            action=proposal_action,
                            reason=approval_reason,
                            original_content=None,
                            proposed_content=cmd_preview,
                            base_hash="",
                            unified_diff=(f"PC > {cmd_preview}" if proposal_action == "pc_control" else f"$ {cmd_preview}"),
                            hunks=[],
                            added_lines=0,
                            removed_lines=0,
                        )
                        await _emit(emit, "proposal", exec_proposal.to_public_dict())
                        if approval_handler is not None:
                            decision = await approval_handler(exec_proposal)
                        else:
                            fut = self.approval_registry.register_proposal(exec_proposal, run_id=run_id)
                            decision = await fut

                    if not decision.approved:
                        fb_note = f" Comentario: {decision.feedback}" if decision.feedback else ""
                        msg_to_llm = f"El usuario rechazó ejecutar '{cmd_preview}'.{fb_note}"
                        summary = f"Ejecución rechazada: {cmd_preview[:60]}"
                        tool_traces.append({"name": tc.name, "ok": False, "summary": summary})
                        await _emit(emit, "tool_result", {"id": tc.id, "name": tc.name, "ok": False, "summary": summary})
                        conversation.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": msg_to_llm})
                        continue

                    loop = asyncio.get_running_loop()

                    def _on_line(line: str) -> None:
                        if emit is None:
                            return
                        try:
                            asyncio.run_coroutine_threadsafe(_emit(emit, "command_output", {"line": line}), loop)
                        except RuntimeError:
                            pass

                    def _is_cancelled() -> bool:
                        return bool(cancel_event and cancel_event.is_set())

                    try:
                        if tc.name == "run_command":
                            exec_res = await asyncio.to_thread(
                                execute_workspace_command,
                                workspace,
                                runtime_dir,
                                cmd_preview,
                                timeout=timeout_sec,
                                cancel_check=_is_cancelled,
                                on_output=_on_line,
                            )
                        elif tc.name == "pc_control":
                            pc_res = await asyncio.to_thread(
                                execute_pc_control,
                                workspace,
                                pc_act,
                                args,
                            )
                            exec_res = {
                                "ok": bool(pc_res.get("ok", True)),
                                "exit_code": 0,
                                "target": target_label,
                                "artifact": None,
                                "output": json.dumps(pc_res, ensure_ascii=False),
                            }
                        elif tc.name == "generate_image":
                            img_res = await asyncio.to_thread(
                                studio_generate_image,
                                workspace,
                                runtime_dir,
                                str(args.get("prompt") or ""),
                                str(args.get("output_path") or ""),
                                negative_prompt=str(args.get("negative_prompt") or "blurry, lowres, watermark, deformed"),
                                width=int(args.get("width") or 512),
                                height=int(args.get("height") or 512),
                                steps=int(args.get("steps") or 4),
                                cfg_scale=float(args.get("cfg_scale") if args.get("cfg_scale") is not None else 1.0),
                                seed=int(args.get("seed") if args.get("seed") is not None else -1),
                                threads=max(1, int(settings.num_thread or 4)),
                                cancel_check=_is_cancelled,
                            )
                            exec_res = {
                                "ok": True,
                                "exit_code": 0,
                                "target": img_res["path"],
                                "artifact": img_res["path"],
                                "output": json.dumps(img_res, ensure_ascii=False),
                            }
                        elif tc.name == "edit_image":
                            img_res = await asyncio.to_thread(
                                studio_edit_image,
                                workspace,
                                runtime_dir,
                                str(args.get("input_path") or ""),
                                str(args.get("output_path") or ""),
                                prompt=str(args.get("prompt") or ""),
                                negative_prompt=str(args.get("negative_prompt") or "blurry, lowres, watermark, deformed"),
                                strength=float(args.get("strength") if args.get("strength") is not None else 0.55),
                                steps=int(args.get("steps") or 4),
                                cfg_scale=float(args.get("cfg_scale") if args.get("cfg_scale") is not None else 1.0),
                                operations=args.get("operations") if isinstance(args.get("operations"), list) else None,
                                threads=max(1, int(settings.num_thread or 4)),
                                cancel_check=_is_cancelled,
                            )
                            exec_res = {
                                "ok": True,
                                "exit_code": 0,
                                "target": img_res["path"],
                                "artifact": img_res["path"],
                                "output": json.dumps(img_res, ensure_ascii=False),
                            }
                        else:
                            exec_res = await asyncio.to_thread(
                                execute_project_action,
                                workspace,
                                runtime_dir,
                                action_label,
                                None if target_label == "." else target_label,
                                cancel_check=_is_cancelled,
                                on_output=_on_line,
                            )
                    except (WorkspaceError, ValueError, TypeError, OSError) as exc:
                        err_text = f"Error al ejecutar {tc.name}: {exc}"
                        tool_traces.append({"name": tc.name, "ok": False, "summary": err_text})
                        await _emit(emit, "tool_result", {"id": tc.id, "name": tc.name, "ok": False, "summary": err_text})
                        conversation.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": err_text})
                        continue

                    ok_flag = bool(exec_res.get("ok"))
                    exit_code = int(exec_res.get("exit_code", 1))
                    artifact = exec_res.get("artifact")
                    raw_out = str(exec_res.get("output") or "")
                    bounded_out = _truncate_text(raw_out, max(settings.max_tool_output_chars, 3200))
                    executed_actions.append({"name": tc.name, "action": action_label, "exit_code": exit_code, "artifact": artifact})
                    if hasattr(self, "coordinator"):
                        self.coordinator.execution(session_id, str(workspace.root), action_label, str(exec_res.get("target") or target_label), exit_code)
                    summary = f"{tc.name} ({action_label}): salida {exit_code}" + (f" · {artifact}" if artifact else "")
                    msg_to_llm = (
                        f"Resultado real de {tc.name} ({action_label}): código de salida {exit_code}.\n"
                        + (f"Artefacto generado: {artifact}\n" if artifact else "")
                        + (f"Salida:\n{bounded_out}" if bounded_out else "(Sin salida en consola)")
                    )
                    tool_traces.append({"name": tc.name, "ok": ok_flag, "summary": summary})
                    await _emit(emit, "tool_result", {"id": tc.id, "name": tc.name, "ok": ok_flag, "summary": summary})
                    conversation.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": msg_to_llm})
                    continue

                # Herramienta desconocida
                err_unknown = f"Herramienta no reconocida: '{tc.name}'."
                await _emit(
                    emit,
                    "tool_result",
                    {"id": tc.id, "name": tc.name, "ok": False, "summary": err_unknown},
                )
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": err_unknown,
                    }
                )

            if promoted and applied_paths and not settings.autonomous_mode:
                message = 'Archivo guardado con tu aprobación: '+', '.join(dict.fromkeys(applied_paths))+'. Abierto en AURAX. Usa Verificar y Ejecutar para probarlo; no se ejecutó ni compiló automáticamente.'
                self.storage.add_message(session_id, 'assistant', message, metadata={'tools':tool_traces})
                await _emit(emit, 'done', {'content':message,'steps':step})
                return {'status':'done','content':message,'steps':step}

        # Se alcanzó max_steps sin respuesta final limpia
        fallback_msg = (
            f"Se alcanzó el límite de {effective_max_steps} pasos en este turno para cuidar el contexto "
            "del modelo local. Puedes pedir que continúe en el siguiente mensaje."
        )
        result_status = 'incomplete' if creating else 'done'
        if creating:
            fallback_msg = ('Se guardaron estos archivos: '+', '.join(dict.fromkeys(applied_paths))+'. El proyecto sigue incompleto; falta verificarlo.' if applied_paths else 'No se creó el proyecto: el modelo agotó los pasos sin guardar archivos completos. Prueba una tarea más pequeña o un modelo más capaz.')
        self.storage.add_message(
            session_id,
            "assistant",
            fallback_msg,
            metadata={
                "tokens_generated": total_tokens,
                "elapsed_ms": total_elapsed_ms,
                "tok_per_sec": last_tok_per_sec,
                "tools": tool_traces,
            },
        )
        await _emit(
            emit,
            "done",
            {
                "content": fallback_msg,
                "tokens_generated": total_tokens,
                "elapsed_ms": total_elapsed_ms,
                "tok_per_sec": last_tok_per_sec,
                "used_tool_mode": last_mode,
                "steps": effective_max_steps,
            },
        )
        return {"status": result_status, "content": fallback_msg, "steps": effective_max_steps}

    def revert_change(self, change_id: str) -> dict[str, Any]:
        """Revierte un cambio aplicado en disco al estado previo registrado."""
        record = self.storage.get_change(change_id)
        if not record:
            raise WorkspaceError(f"Cambio no encontrado: {change_id}")
        if record["status"] != "applied":
            raise WorkspaceError(
                f"Solo se pueden revertir cambios en estado 'applied' (estado actual: {record['status']})."
            )
        workspace = SafeWorkspace(record["workspace_path"])
        workspace.revert_change(record["file_path"], record["before_content"])
        updated = self.storage.mark_change_reverted(change_id)
        return updated or record
