"""Paleta de comandos `/` (acciones, terminal, PowerShell/CMD y habilidades activas/instaladas)
y menciones `@` de archivos reales del workspace para AURA."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem


@dataclass
class SlashEntry:
    command: str
    title: str
    description: str
    category: str
    kind: str  # "builtin" | "skill" | "file"
    payload: dict[str, Any]


BUILTIN_ACTIONS: tuple[tuple[str, str, str, str], ...] = (
    ("/terminal", "Terminal integrada de AURA", "Abre la terminal propia de AURA o ejecuta un comando", "Terminal"),
    ("/powershell", "PowerShell (integrado / externo)", "Ejecuta en PowerShell o abre PowerShell en el proyecto", "Terminal"),
    ("/cmd", "CMD · Símbolo del sistema", "Ejecuta en CMD o abre CMD en el proyecto", "Terminal"),
    ("/autonomo", "Modo Constructor Autónomo", "Activa o alterna edición, pruebas y compilación automáticas", "Agente"),
    ("/compilar", "Compilar proyecto", "Compila el archivo o proyecto actual (EXE / C++ / Web / ISS)", "Construcción"),
    ("/probar", "Ejecutar pruebas", "Corre pytest, npm test o pruebas del archivo actual", "Construcción"),
    ("/verificar", "Verificar sintaxis", "Comprueba sintaxis sin ejecutar (py_compile / node --check / gcc)", "Construcción"),
    ("/imagen", "Estudio de imágenes offline", "Genera o edita una imagen fotorrealista 100 % local", "Creativo"),
    ("/diseno", "Diseño gráfico profesional", "Crea carteles, banners, miniaturas e identidad visual con tipografía nítida", "Creativo"),
    ("/video", "Video realista / Avatar / 3D MP4", "Crea videos 2.5D, avatar parlante local o scripts de video 3D realista para Blender 5", "Creativo"),
    ("/web", "Buscar en Internet", "Investiga documentación y soluciones técnicas con web_search", "Investigación"),
    ("/pc", "Control e inspección de la PC", "Inspecciona procesos/ventanas/pantalla o maneja apps con aprobación de 1 clic", "PC"),
    ("/android", "Android · UI, Depuración, ADB y Fastboot", "Crea o depura apps Android y administra teléfonos por ADB (USB/Wi-Fi) y Fastboot", "Android"),
    ("/kicad", "KiCad 10 · Esquemáticos y PCBs", "Crea diagramas electrónicos (.kicad_sch/.kicad_pro/.svg), ERC/DRC, Gerbers y STEP", "Diagramas"),
    ("/diagrama", "Diagramas de bloques, flujo y circuitos", "Genera diagramas vectoriales SVG, Mermaid y esquemáticos KiCad 10 offline", "Diagramas"),
    ("/entrenar", "Entrenar modelos IA locales (desde 0 / LLaMA Pro)", "Enseña, diseña y prepara pipelines locales para entrenar modelos desde 0 o subirlos de categoría", "IA / ML"),
    ("/agentes", "Apps CLI · Claude Code / Codex / OpenCode / Ollama", "Abre el lanzador de agentes CLI externos dentro del proyecto AuraX", "Agente"),
    ("/plan", "Planificar arquitectura", "Diseña un plan paso a paso antes de tocar archivos", "Agente"),
    ("/skills", "Administrar habilidades", "Abre el panel de habilidades (importar / activar / quitar)", "Paneles"),
    ("/modelos", "Modelos y habilidades", "Abre la configuración de modelos locales probados", "Paneles"),
    ("/cambios", "Cambios y deshacer", "Revisa el historial de diffs y revierte con 1 clic", "Paneles"),
)

_SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "reverse-engineer-anything": ("/rea",),
    "impeccable": ("/impecable",),
    "blender-3d": ("/blender",),
    "bases-sql": ("/sql",),
    "control-pc": ("/pc",),
    "android-adb-dev": ("/android", "/adb"),
    "kicad-diagramas": ("/kicad", "/diagrama"),
    "video-diseno-studio": ("/video", "/diseno"),
    "entrenar-modelos-ia": ("/entrenar",),
}


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower()).strip("-")
    return slug or "skill"


def build_slash_catalog(skills_store=None) -> list[SlashEntry]:
    """Construye el catálogo unificado de acciones integradas + todas las habilidades de SkillStore."""
    entries: list[SlashEntry] = []
    seen: set[str] = set()

    # 1. Habilidades instaladas en SkillStore (ej. /rea, /impeccable, /blender-3d, etc.)
    if skills_store is not None:
        try:
            skills = skills_store.catalog() if hasattr(skills_store, "catalog") else skills_store.list()
        except Exception:
            skills = []
        for sk in skills:
            name = str(sk.get("name") or "").strip()
            sid = str(sk.get("id") or "").strip()
            if not name or not sid:
                continue
            slug = _slugify(name)
            aliases = list(_SKILL_ALIASES.get(slug, ()))
            primary = aliases[0] if aliases else f"/{slug}"
            desc = str(sk.get("description") or "Habilidad local instalada").strip()[:110]
            state_tag = "activa" if sk.get("enabled") else "se activará al usarla"
            if primary not in seen:
                seen.add(primary)
                entries.append(
                    SlashEntry(
                        command=primary,
                        title=f"{primary} · {name}",
                        description=f"{desc} ({state_tag})",
                        category="Habilidades",
                        kind="skill",
                        payload={"id": sid, "name": name, "slug": slug, "aliases": [f"/{slug}", *aliases]},
                    )
                )
            alt_cmd = f"/{slug}"
            if alt_cmd not in seen:
                seen.add(alt_cmd)
                entries.append(
                    SlashEntry(
                        command=alt_cmd,
                        title=f"{alt_cmd} · {name}",
                        description=f"{desc} ({state_tag})",
                        category="Habilidades",
                        kind="skill",
                        payload={"id": sid, "name": name, "slug": slug, "aliases": [alt_cmd, *aliases]},
                    )
                )

    # 2. Acciones y herramientas integradas (/terminal, /powershell, /cmd, /imagen, /web, ...)
    for cmd, title, desc, cat in BUILTIN_ACTIONS:
        if cmd in seen:
            continue
        seen.add(cmd)
        entries.append(
            SlashEntry(
                command=cmd,
                title=f"{cmd} · {title}",
                description=desc,
                category=cat,
                kind="builtin",
                payload={"action": cmd.lstrip("/")},
            )
        )
    return entries


def list_workspace_mentions(workspace_path: str, query: str = "", limit: int = 30) -> list[SlashEntry]:
    """Lista archivos reales del workspace para autocompletar `@archivo`."""
    root = Path(workspace_path)
    if not root.is_dir():
        return []
    q = query.strip().lower()
    skip = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", "dist", "build"}
    found: list[SlashEntry] = []
    try:
        for p in root.rglob("*"):
            if len(found) >= limit:
                break
            rel = p.relative_to(root)
            if any(part in skip for part in rel.parts) or not p.is_file():
                continue
            rel_posix = rel.as_posix()
            if q and q not in rel_posix.lower():
                continue
            found.append(
                SlashEntry(
                    command=f"@{rel_posix}",
                    title=f"@{rel_posix}",
                    description=f"Adjuntar y mencionar {rel_posix}",
                    category="Archivos",
                    kind="file",
                    payload={"path": rel_posix},
                )
            )
    except OSError:
        pass
    return found


def filter_slash_entries(entries: list[SlashEntry], query: str) -> list[SlashEntry]:
    """Filtra comandos `/` por prefijo o coincidencia en comando, título o descripción."""
    q = query.strip().lower()
    if not q or q == "/":
        return entries
    if not q.startswith("/"):
        q = "/" + q
    bare = q.lstrip("/")
    scored: list[tuple[int, SlashEntry]] = []
    for item in entries:
        cmd_l = item.command.lower()
        if cmd_l.startswith(q):
            scored.append((0, item))
        elif bare in cmd_l or bare in item.title.lower():
            scored.append((1, item))
        elif bare in item.description.lower():
            scored.append((2, item))
    scored.sort(key=lambda pair: (pair[0], pair[1].command))
    return [pair[1] for pair in scored]


def resolve_slash_command(text: str, skills_store=None) -> dict[str, Any] | None:
    """Interpreta una orden que empieza por `/` y devuelve una acción estructurada para AURA.
    Devuelve None si el texto no empieza por `/`."""
    raw = str(text or "").strip()
    if not raw.startswith("/"):
        return None
    parts = raw.split(None, 1)
    cmd = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/terminal", "/term"):
        return {"type": "open_terminal", "shell": "powershell", "command": rest}
    if cmd in ("/powershell", "/ps"):
        if rest.lower() in ("externo", "ventana", "nueva"):
            return {"type": "external_shell", "shell": "powershell"}
        return {"type": "open_terminal", "shell": "powershell", "command": rest}
    if cmd == "/cmd":
        if rest.lower() in ("externo", "ventana", "nueva"):
            return {"type": "external_shell", "shell": "cmd"}
        return {"type": "open_terminal", "shell": "cmd", "command": rest}
    if cmd == "/autonomo":
        return {"type": "toggle_autonomous", "arg": rest}
    if cmd == "/skills":
        return {"type": "open_panel", "panel": "skills"}
    if cmd == "/modelos":
        return {"type": "open_panel", "panel": "settings"}
    if cmd == "/cambios":
        return {"type": "open_panel", "panel": "changes"}
    if cmd in ("/compilar", "/probar", "/verificar", "/ejecutar"):
        verb = cmd.lstrip("/")
        prompt = f"{verb} {rest}".strip() if rest else verb
        return {"type": "prompt", "prompt": prompt, "force_programming": True}
    if cmd == "/imagen":
        if not rest:
            return {"type": "notice", "message": "Indica la imagen a crear o editar. Ej.: /imagen foto realista de un reloj de acero en img/reloj.png"}
        return {
            "type": "prompt",
            "prompt": f"Usa las herramientas offline `generate_image` o `edit_image` para cumplir esta orden directa sin dar pasos manuales: {rest}",
            "force_programming": True,
            "auto_autonomous": True,
        }
    if cmd == "/web":
        if not rest:
            return {"type": "notice", "message": "Indica qué buscar en Internet. Ej.: /web documentación oficial de PySide6 QProcess"}
        return {
            "type": "prompt",
            "prompt": f"Usa `web_search` y `fetch_url` para investigar en Internet y responder con fuentes técnicas reales: {rest}",
            "force_programming": True,
            "auto_autonomous": True,
        }
    if cmd == "/plan":
        if not rest:
            return {"type": "notice", "message": "Indica qué quieres planificar. Ej.: /plan sistema de inventario en PySide6 y SQLite"}
        return {
            "type": "prompt",
            "prompt": f"Diseña primero un plan arquitectónico paso a paso (archivos, contratos, pruebas y riesgos) sin omitir detalles para: {rest}",
            "force_programming": True,
        }

    # Resolver contra cualquier habilidad instalada en SkillStore (/rea, /impeccable, /blender-3d, /pc, ...)
    catalog = build_slash_catalog(skills_store)
    for entry in catalog:
        if entry.kind != "skill":
            continue
        all_cmds = {entry.command.lower(), *(a.lower() for a in entry.payload.get("aliases", []))}
        if cmd in all_cmds:
            sid = entry.payload["id"]
            sname = entry.payload["name"]
            task = rest or f"Inspecciona el proyecto actual aplicando la habilidad {sname} y dime o ejecuta el primer paso concreto."
            return {
                "type": "invoke_skill",
                "skill_id": sid,
                "skill_name": sname,
                "auto_autonomous": True,
                "prompt": (
                    f"Activa y aplica directamente la habilidad `{sname}` (id `{sid}`): "
                    f"consúltala primero con `read_skill(id='{sid}')` y ejecuta esta orden directa en el proyecto: {task}"
                ),
            }

    if cmd == "/pc":
        task = rest or "Muestra el estado actual del sistema (CPU, RAM, discos y ventanas visibles) con pc_inspect."
        return {
            "type": "prompt",
            "prompt": (
                f"Usa `pc_inspect` para inspeccionar y `pc_control` (pedirá aprobación de 1 clic al usuario) "
                f"para cumplir esta orden directa sobre la PC Windows: {task}"
            ),
            "force_programming": True,
            "auto_autonomous": True,
        }

    if cmd in ("/android", "/adb", "/fastboot"):
        task = rest or "Inspecciona los dispositivos Android conectados (ADB USB/Wi-Fi y Fastboot) y el entorno SDK con pc_inspect(action='android_devices')."
        return {
            "type": "prompt",
            "prompt": (
                f"Usa `pc_inspect(action='android_devices')`, `run_command` (con `adb`/`fastboot`/`gradlew`, respetando aprobación de 1 clic en cambios al dispositivo) "
                f"y buenas prácticas Android/Kotlin/Jetpack Compose para cumplir esta orden directa: {task}"
            ),
            "force_programming": True,
            "auto_autonomous": True,
        }

    if cmd in ("/kicad", "/diagrama"):
        task = rest or "Crea un diagrama de bloques o esquemático KiCad 10 con vista previa SVG en el proyecto."
        return {
            "type": "prompt",
            "prompt": (
                f"Usa `agente_ia.diagram_studio` (`create_kicad_diagram_bundle` para circuitos `.kicad_sch`/`.kicad_pro`/`.svg` "
                f"o `render_architecture_svg` para bloques/arquitectura `.svg`/`.mmd`) y `kicad-cli` si está instalado "
                f"para cumplir esta orden directa: {task}"
            ),
            "force_programming": True,
            "auto_autonomous": True,
        }

    if cmd in ("/video", "/diseno"):
        task = rest or "Crea un diseño gráfico profesional o video animado realista 100 % local en el proyecto."
        return {
            "type": "prompt",
            "prompt": (
                f"Usa `generate_image`/`edit_image` y `agente_ia.video_studio` (`compose_graphic_design`, `render_cinematic_video`, "
                f"`render_talking_avatar_video`, `generate_blender_3d_video_script`) para cumplir esta orden directa: {task}"
            ),
            "force_programming": True,
            "auto_autonomous": True,
        }

    if cmd in ("/agentes", "/apps"):
        return {"type": "open_external_agents", "prompt": rest}
    if cmd in ("/codex", "/claude", "/claude-code", "/opencode", "/qwen-code", "/copilot", "/ollama"):
        agent_map = {
            "/codex": "codex",
            "/claude": "claude-code",
            "/claude-code": "claude-code",
            "/opencode": "opencode",
            "/qwen-code": "qwen-code",
            "/copilot": "copilot",
            "/ollama": "ollama",
        }
        return {"type": "launch_external_agent", "agent_id": agent_map[cmd], "prompt": rest}
    if cmd == "/entrenar":
        task = rest or "Explícame paso a paso y prepara el pipeline local para entrenar un modelo LLM desde 0 (BPE + LlamaForCausalLM + GGUF) o escalar uno existente con LLaMA Pro."
        return {
            "type": "prompt",
            "prompt": (
                f"Aplica prácticas rigurosas de entrenamiento local de LLMs (desde cero BPE + LlamaForCausalLM + pre-entrenamiento causal + GGUF "
                f"o expansión LLaMA Pro + SFT sin fuga de pruebas + compuerta >= 98%) para cumplir esta orden: {task}"
            ),
            "force_programming": True,
            "auto_autonomous": True,
        }

    return {"type": "notice", "message": f"Acción `{cmd}` no encontrada. Escribe `/` para ver todas las acciones y habilidades disponibles."}


class SlashPopup(QListWidget):
    """Menú flotante limpio sobre el cuadro de mensaje para autocompletar `/` y `@`."""

    entry_chosen = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMaximumHeight(240)
        self.setMinimumWidth(360)
        self.setStyleSheet(
            "QListWidget{background:#0e1d31;color:#edf5ff;border:1px solid #35587c;border-radius:10px;padding:4px;}"
            "QListWidget::item{padding:7px 10px;border-radius:6px;}"
            "QListWidget::item:selected{background:#1f4e79;color:#ffffff;}"
        )
        self.itemClicked.connect(self._emit_item)

    def set_entries(self, entries: list[SlashEntry]) -> None:
        self.clear()
        for entry in entries[:14]:
            item = QListWidgetItem(f"{entry.title}\n  {entry.description}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.addItem(item)
        if self.count():
            self.setCurrentRow(0)

    def move_selection(self, delta: int) -> None:
        if not self.count():
            return
        row = (self.currentRow() + delta) % self.count()
        self.setCurrentRow(row)

    def accept_current(self) -> bool:
        item = self.currentItem()
        if item is None:
            return False
        self._emit_item(item)
        return True

    def _emit_item(self, item: QListWidgetItem) -> None:
        entry = item.data(Qt.ItemDataRole.UserRole)
        self.hide()
        if entry is not None:
            self.entry_chosen.emit(entry)
