"""Interfaz interactiva en terminal (CLI) con confirmación de diffs coloreados."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import APP_NAME, __version__
from .agent import AgentEngine, ApprovalDecision, ApprovalRegistry, PendingProposal
from .config import (
    HARDWARE_PROFILES,
    RECOMMENDED_MODELS,
    AppSettings,
    apply_hardware_profile,
    detect_local_hardware,
)
from .providers import LocalLLMClient
from .storage import Storage
from .workspace import SafeWorkspace, WorkspaceError


def _make_console() -> Console:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    return Console(force_terminal=None, soft_wrap=True)


def _render_colored_diff(proposal: PendingProposal) -> Text:
    txt = Text()
    if not proposal.hunks:
        txt.append("(sin cambios textuales)", style="dim")
        return txt
    for row in proposal.hunks:
        rtype = row["type"]
        if rtype == "hunk":
            txt.append(f"{row['text']}\n", style="bold cyan")
        elif rtype == "add":
            txt.append(f"+ {row['text']}\n", style="green")
        elif rtype == "del":
            txt.append(f"- {row['text']}\n", style="red")
        else:
            txt.append(f"  {row['text']}\n", style="dim")
    return txt


def _print_help(console: Console) -> None:
    table = Table(title="Comandos disponibles", show_header=True, header_style="bold blue")
    table.add_column("Comando", style="cyan", no_wrap=True)
    table.add_column("Descripción")
    rows = [
        ("/ayuda", "Muestra esta lista de comandos."),
        ("/estado", "Comprueba motores locales (Ollama, llama.cpp/KoboldCpp, LM Studio) y hardware."),
        ("/perfil <nombre>", "Cambia perfil: legacy_i5_1gb | balanced_cpu | gpu_standard."),
        ("/gpu <capas>", "Ajusta capas en GPU (ej. /gpu 0 solo CPU, /gpu 8 para 1 GB VRAM)."),
        ("/hilos <n>", "Ajusta hilos de CPU (ej. /hilos 2 en i5 1ra Gen)."),
        ("/proveedor <id>", "Cambia motor: ollama | llamacpp | lmstudio."),
        ("/modelo <nombre>", "Cambia el modelo local activo."),
        ("/carpeta <ruta>", "Cambia el workspace activo."),
        ("/archivos [subcarpeta]", "Lista archivos dentro del workspace."),
        ("/historial", "Muestra cambios propuestos/aplicados en la sesión."),
        ("/revertir [id]", "Revierte el último cambio aplicado o el ID indicado."),
        ("/limpiar", "Inicia una nueva sesión limpia."),
        ("/salir", "Sale de la CLI."),
    ]
    for cmd, desc in rows:
        table.add_row(cmd, desc)
    console.print(table)


async def run_doctor(storage: Storage | None = None) -> int:
    """Ejecuta diagnóstico de hardware y motores locales sin iniciar chat."""
    console = _make_console()
    db = storage or Storage()
    settings = db.get_settings()
    client = LocalLLMClient()

    hw = detect_local_hardware()
    statuses = await client.detect_providers(
        settings.ollama_url,
        settings.llamacpp_url,
        settings.lmstudio_url,
    )

    simd = hw["simd"]
    avx_label = "No (CPU legacy compatible sin AVX)" if simd["avx"] is False else ("Sí" if simd["avx"] else "No determinado")
    sse_label = "Sí" if simd["sse42"] else ("No" if simd["sse42"] is False else "No determinado")

    hw_table = Table(title=f"{APP_NAME} v{__version__} — Diagnóstico de entorno local")
    hw_table.add_column("Componente", style="cyan")
    hw_table.add_column("Valor detectado")
    hw_table.add_row("Sistema", str(hw["os"]))
    hw_table.add_row("Núcleos lógicos", str(hw["logical_cores"]))
    hw_table.add_row("RAM total", f"{hw['ram_gb']} GB" if hw["ram_gb"] else "Desconocida")
    hw_table.add_row("SSE4.2 / AVX", f"SSE4.2: {sse_label} | AVX: {avx_label}")
    hw_table.add_row("Perfil activo", f"{settings.hardware_profile} (ctx={settings.num_ctx}, batch={settings.num_batch}, gpu={settings.num_gpu}, threads={settings.num_thread})")
    hw_table.add_row("Workspace activo", settings.workspace_path)
    console.print(hw_table)

    prov_table = Table(title="Motores de IA Locales")
    prov_table.add_column("Motor", style="cyan")
    prov_table.add_column("URL")
    prov_table.add_column("Estado")
    prov_table.add_column("Modelos")
    for st in statuses.values():
        estado = "[green]Conectado[/green]" if st.online else "[yellow]Apagado[/yellow]"
        models_txt = ", ".join(m["id"] for m in st.models[:5]) if st.models else ("(sin modelos)" if st.online else "-")
        prov_table.add_row(st.name, st.url, estado, models_txt)
    console.print(prov_table)

    rec_table = Table(title="Modelos recomendados para Intel i5 1ra Gen + NVIDIA 1 GB VRAM")
    rec_table.add_column("Modelo", style="cyan")
    rec_table.add_column("Tamaño")
    rec_table.add_column("Ajuste 1 GB VRAM")
    rec_table.add_column("Comando / Archivo")
    for m in RECOMMENDED_MODELS:
        rec_table.add_row(m["id"], f"{m['size_mb']} MB", m["vram_fit"], m["ollama_cmd"])
    console.print(rec_table)

    console.print(
        Panel(
            "Consejo para Intel i5 1ra Gen (sin AVX) + NVIDIA 1 GB:\n"
            "• Con KoboldCpp: koboldcpp.exe --model qwen2.5-coder-1.5b-instruct-q4_k_m.gguf --noavx2 --noavx --contextsize 2048 --threads 2 --gpulayers 8 --port 8080\n"
            "• Con llama.cpp: llama-server.exe -m qwen2.5-coder-0.5b-instruct-q4_k_m.gguf -c 2048 -b 128 -t 2 -ngl 99 --port 8080\n"
            "• Con Ollama: ollama pull qwen2.5-coder:0.5b  (o qwen2.5-coder:1.5b)",
            title="Guía rápida local",
            border_style="blue",
        )
    )
    return 0


class CLIRunner:
    """Sesión interactiva o de un solo prompt en terminal."""

    def __init__(
        self,
        *,
        workspace: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        profile: str | None = None,
        storage: Storage | None = None,
        llm_client: LocalLLMClient | None = None,
    ) -> None:
        self.console = _make_console()
        self.storage = storage or Storage()
        self.client = llm_client or LocalLLMClient()
        self.registry = ApprovalRegistry()
        self.engine = AgentEngine(self.storage, self.client, self.registry)

        settings = self.storage.get_settings()
        if profile and profile in HARDWARE_PROFILES:
            settings = apply_hardware_profile(settings, profile, keep_model=bool(model))  # type: ignore[arg-type]
        if workspace:
            ws = SafeWorkspace(workspace)
            settings = settings.model_copy(update={"workspace_path": str(ws.root)})
        if provider in ("ollama", "llamacpp", "lmstudio"):
            settings = settings.model_copy(update={"provider": provider})  # type: ignore[arg-type]
        if model:
            settings = settings.model_copy(update={"model": model})
        self.settings: AppSettings = self.storage.save_settings(settings)

        self.session = self.storage.create_session(
            title="Sesión CLI",
            workspace_path=self.settings.workspace_path,
            provider=self.settings.provider,
            model=self.settings.model,
        )

    async def print_status_banner(self) -> None:
        statuses = await self.client.detect_providers(
            self.settings.ollama_url,
            self.settings.llamacpp_url,
            self.settings.lmstudio_url,
        )
        active = statuses.get(self.settings.provider)
        any_online = any(s.online for s in statuses.values())
        prof = HARDWARE_PROFILES.get(self.settings.hardware_profile, {})
        conn_txt = (
            f"[green]Conectado[/green] ({active.name})"
            if active and active.online
            else "[yellow]Desconectado[/yellow]"
        )
        self.console.print(
            Panel(
                f"[bold]{APP_NAME} v{__version__}[/bold] — CLI de codificación local\n"
                f"Workspace: [cyan]{self.settings.workspace_path}[/cyan]\n"
                f"Motor: [bold]{self.settings.provider}[/bold] ({conn_txt}) · Modelo: [bold]{self.settings.model}[/bold]\n"
                f"Perfil: {prof.get('short_label', self.settings.hardware_profile)} · "
                f"ctx={self.settings.num_ctx} · num_gpu={self.settings.num_gpu} · hilos={self.settings.num_thread}\n"
                f"Escribe [cyan]/ayuda[/cyan] para ver comandos o [cyan]/salir[/cyan] para terminar.",
                border_style="blue",
            )
        )
        if not any_online:
            self.console.print(
                "[yellow]Aviso:[/yellow] No hay ningún motor local activo ahora mismo. "
                "Puedes iniciar Ollama, KoboldCpp (--noavx2 --noavx --port 8080) o llama-server y comprobar con [cyan]/estado[/cyan]."
            )

    async def handle_approval(self, proposal: PendingProposal) -> ApprovalDecision:
        self.console.print(
            Panel(
                _render_colored_diff(proposal),
                title=f"Propuesta [{proposal.action.upper()}] {proposal.file_path} (+{proposal.added_lines}/-{proposal.removed_lines})",
                subtitle=proposal.reason,
                border_style="yellow",
            )
        )
        while True:
            choice = self.console.input(
                "[bold][a] Aprobar  [r] Rechazar  [c] Rechazar con comentario  [v] Ver contenido completo:[/bold] "
            ).strip().lower()
            if choice in ("a", "aprobar", "s", "si", "sí"):
                return ApprovalDecision(approved=True)
            if choice in ("r", "rechazar", "n", "no"):
                return ApprovalDecision(approved=False, feedback="")
            if choice in ("c", "comentario"):
                fb = self.console.input("Comentario para el agente: ").strip()
                return ApprovalDecision(approved=False, feedback=fb)
            if choice in ("v", "ver"):
                content = proposal.proposed_content if proposal.proposed_content is not None else "(archivo eliminado)"
                self.console.print(Panel(content, title=f"Contenido completo propuesto: {proposal.file_path}", border_style="cyan"))
                continue
            self.console.print("Opción no reconocida. Usa a, r, c o v.")

    async def execute_prompt(self, user_prompt: str) -> None:
        streamed: list[str] = []
        stream_started = False

        async def emit(event: str, data: dict[str, Any]) -> None:
            nonlocal stream_started
            if event == "token":
                if not stream_started:
                    stream_started = True
                    self.console.print("\n[bold blue]CódigoLocal:[/bold blue] ", end="")
                chunk = data.get("text", "")
                streamed.append(chunk)
                self.console.print(chunk, end="", markup=False, highlight=False)
            elif event == "stream_clean":
                if stream_started:
                    self.console.print("")
                    stream_started = False
            elif event == "tool_start":
                if stream_started:
                    self.console.print("")
                    stream_started = False
                self.console.print(f"[dim]-> Ejecutando {data.get('name')}...[/dim]")
            elif event == "tool_result":
                tag = "[green]OK[/green]" if data.get("ok") else "[red]ERROR[/red]"
                self.console.print(f"   {tag} {data.get('summary')}")
            elif event == "proposal_resolved":
                st = data.get("status")
                color = "green" if st == "applied" else "yellow"
                self.console.print(f"[{color}]Cambio {st}: {data.get('file_path')}[/{color}]")
            elif event == "done":
                if stream_started:
                    self.console.print("")
                elif data.get("content"):
                    self.console.print(Markdown(data["content"]))
                self.console.print(
                    f"[dim]{data.get('tokens_generated', 0)} tok · {data.get('tok_per_sec', 0)} tok/s · modo {data.get('used_tool_mode')}[/dim]\n"
                )
            elif event == "error":
                if stream_started:
                    self.console.print("")
                self.console.print(f"[red]Error:[/red] {data.get('message')}\n")

        await self.engine.run_turn(
            session_id=self.session["id"],
            user_message=user_prompt,
            settings=self.settings,
            emit=emit,
            approval_handler=self.handle_approval,
        )

    async def handle_slash(self, raw: str) -> bool:
        """Procesa comando slash. Devuelve False si el usuario pidió salir."""
        parts = raw.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/salir", "/exit", "/quit"):
            return False
        if cmd in ("/ayuda", "/help"):
            _print_help(self.console)
            return True
        if cmd == "/estado":
            await run_doctor(storage=self.storage)
            return True
        if cmd == "/perfil":
            if arg not in HARDWARE_PROFILES:
                self.console.print(f"Perfiles disponibles: {', '.join(HARDWARE_PROFILES)}")
                return True
            self.settings = self.storage.save_settings(apply_hardware_profile(self.settings, arg))  # type: ignore[arg-type]
            self.console.print(f"Perfil actualizado a [cyan]{arg}[/cyan] (ctx={self.settings.num_ctx}, gpu={self.settings.num_gpu}, threads={self.settings.num_thread}).")
            return True
        if cmd == "/gpu":
            try:
                layers = max(0, int(arg))
            except ValueError:
                self.console.print("Uso: /gpu <número de capas> (ej. /gpu 0 o /gpu 8)")
                return True
            self.settings = self.storage.save_settings(self.settings.model_copy(update={"num_gpu": layers}))
            self.console.print(f"num_gpu actualizado a [cyan]{layers}[/cyan].")
            return True
        if cmd == "/hilos":
            try:
                th = max(1, min(32, int(arg)))
            except ValueError:
                self.console.print("Uso: /hilos <número> (ej. /hilos 2)")
                return True
            self.settings = self.storage.save_settings(self.settings.model_copy(update={"num_thread": th}))
            self.console.print(f"num_thread actualizado a [cyan]{th}[/cyan].")
            return True
        if cmd == "/proveedor":
            if arg not in ("ollama", "llamacpp", "lmstudio"):
                self.console.print("Proveedores válidos: ollama, llamacpp, lmstudio")
                return True
            self.settings = self.storage.save_settings(self.settings.model_copy(update={"provider": arg}))  # type: ignore[arg-type]
            self.console.print(f"Proveedor cambiado a [cyan]{arg}[/cyan].")
            return True
        if cmd == "/modelo":
            if not arg:
                self.console.print("Uso: /modelo <nombre_del_modelo>")
                return True
            self.settings = self.storage.save_settings(self.settings.model_copy(update={"model": arg}))
            self.console.print(f"Modelo cambiado a [cyan]{arg}[/cyan].")
            return True
        if cmd == "/carpeta":
            if not arg:
                self.console.print(f"Carpeta actual: {self.settings.workspace_path}")
                return True
            try:
                ws = SafeWorkspace(arg)
            except WorkspaceError as exc:
                self.console.print(f"[red]{exc}[/red]")
                return True
            self.settings = self.storage.save_settings(self.settings.model_copy(update={"workspace_path": str(ws.root)}))
            self.storage.update_session(self.session["id"], workspace_path=str(ws.root))
            self.console.print(f"Workspace cambiado a [cyan]{ws.root}[/cyan].")
            return True
        if cmd == "/archivos":
            try:
                ws = SafeWorkspace(self.settings.workspace_path)
                res = ws.list_files(path=arg or ".", max_depth=3, max_entries=120)
                self.console.print(Panel(res["text"], title=f"Archivos en {res['base']}", border_style="blue"))
            except WorkspaceError as exc:
                self.console.print(f"[red]{exc}[/red]")
            return True
        if cmd == "/historial":
            changes = self.storage.list_changes(session_id=self.session["id"])
            if not changes:
                self.console.print("Sin cambios registrados en esta sesión.")
                return True
            table = Table(title="Historial de cambios")
            table.add_column("ID", style="cyan")
            table.add_column("Archivo")
            table.add_column("Acción")
            table.add_column("Estado")
            for ch in changes:
                table.add_row(ch["id"], ch["file_path"], ch["action"], ch["status"])
            self.console.print(table)
            return True
        if cmd == "/revertir":
            target_id = arg
            if not target_id:
                applied = [c for c in self.storage.list_changes(session_id=self.session["id"]) if c["status"] == "applied"]
                if not applied:
                    self.console.print("No hay cambios aplicados para revertir.")
                    return True
                target_id = applied[0]["id"]
            try:
                res = self.engine.revert_change(target_id)
                self.console.print(f"[green]Revertido:[/green] {res['file_path']} ({res['id']})")
            except WorkspaceError as exc:
                self.console.print(f"[red]Error al revertir:[/red] {exc}")
            return True
        if cmd == "/limpiar":
            self.session = self.storage.create_session(
                title="Sesión CLI",
                workspace_path=self.settings.workspace_path,
                provider=self.settings.provider,
                model=self.settings.model,
            )
            self.console.print("Nueva sesión iniciada.")
            return True

        self.console.print(f"Comando desconocido: {cmd}. Escribe /ayuda.")
        return True

    async def run_interactive(self, initial_prompt: str | None = None) -> int:
        await self.print_status_banner()
        if initial_prompt:
            await self.execute_prompt(initial_prompt)
            return 0

        while True:
            try:
                line = self.console.input("[bold green]Tú>[/bold green] ").strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\nHasta luego.")
                return 0
            if not line:
                continue
            if line.startswith("/"):
                keep_going = await self.handle_slash(line)
                if not keep_going:
                    self.console.print("Hasta luego.")
                    return 0
                continue
            await self.execute_prompt(line)
