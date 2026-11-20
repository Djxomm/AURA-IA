"""Punto de entrada unificado: web, cli y doctor."""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import webbrowser

import uvicorn

from . import APP_NAME, __version__
from .cli import CLIRunner, run_doctor
from .config import HARDWARE_PROFILES
from .storage import Storage
from .web_server import create_app
from .workspace import SafeWorkspace


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agente_ia",
        description=f"{APP_NAME} v{__version__} — Agente local de IA y codificación.",
    )
    sub = parser.add_subparsers(dest="command", required=False)

    web_p = sub.add_parser("web", help="Inicia la interfaz web local.")
    web_p.add_argument("--host", default="127.0.0.1", help="Host de escucha (por defecto 127.0.0.1).")
    web_p.add_argument("--port", type=int, default=8765, help="Puerto HTTP (por defecto 8765).")
    web_p.add_argument("--workspace", default=None, help="Carpeta inicial del proyecto.")
    web_p.add_argument("--no-browser", action="store_true", help="No abrir el navegador automáticamente.")

    cli_p = sub.add_parser("cli", help="Inicia la interfaz interactiva en consola.")
    cli_p.add_argument("--workspace", default=None, help="Carpeta del proyecto.")
    cli_p.add_argument("--provider", choices=["ollama", "llamacpp", "lmstudio"], default=None)
    cli_p.add_argument("--model", default=None, help="Nombre del modelo local.")
    cli_p.add_argument("--profile", choices=list(HARDWARE_PROFILES.keys()), default=None)
    cli_p.add_argument("--prompt", default=None, help="Ejecuta un único prompt y sale.")

    sub.add_parser("doctor", help="Diagnostica hardware y motores locales disponibles.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    cmd = args.command or "web"

    if cmd == "doctor":
        return asyncio.run(run_doctor())

    if cmd == "cli":
        runner = CLIRunner(
            workspace=args.workspace,
            provider=args.provider,
            model=args.model,
            profile=args.profile,
        )
        return asyncio.run(runner.run_interactive(initial_prompt=args.prompt))

    if cmd == "web":
        storage = Storage()
        if args.workspace:
            ws = SafeWorkspace(args.workspace)
            cur = storage.get_settings()
            storage.save_settings(cur.model_copy(update={"workspace_path": str(ws.root)}))

        app = create_app(storage=storage)
        url = f"http://{args.host}:{args.port}"
        if not args.no_browser:
            timer = threading.Timer(1.0, lambda: webbrowser.open(url))
            timer.daemon = True
            timer.start()
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
