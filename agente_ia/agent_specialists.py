"""Sistema de Agentes Especialistas Autónomos de AURA IA (optimizado para AURA - MATEO Pro / ANGEL 5.6 / AURAX).
Aplica arquitectura inspirada en agentes autónomos modernos (razonamiento configurable <thought>,
encadenamiento multi-herramienta en un solo turno, verificación real y recuperación ante fallos)
manteniendo un solo modelo caliente en RAM (servidor persistente KV-RAM)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SpecialistProfile:
    id: str
    slash: str
    title: str
    description: str
    thinking_effort: str
    system_directive: str


SPECIALISTS: dict[str, SpecialistProfile] = {
    "investigacion": SpecialistProfile(
        id="investigacion",
        slash="/investigar",
        title="Agente Investigador Profundo",
        description="Investiga en Internet y en el código local, contrasta fuentes reales y entrega un informe verificado.",
        thinking_effort="profundo",
        system_directive=(
            "Eres el **Agente Investigador Profundo** de AURA IA.\n"
            "Metodología estricta:\n"
            "1. Planifica brevemente dentro de `<thought>...</thought>` qué fuentes verificar.\n"
            "2. Combina herramientas reales en paralelo/cadena (`web_search`, `fetch_url`, `list_files`, `search_in_files`, `read_file`).\n"
            "3. Nunca inventes cifras, APIs ni enlaces; cita solo fuentes o archivos inspeccionados.\n"
            "4. Entrega conclusiones accionables, comparativa clara y pasos concretos."
        ),
    ),
    "programacion": SpecialistProfile(
        id="programacion",
        slash="/programar",
        title="Agente de Programación Avanzada",
        description="Arquitectura multilenguaje (Python, TS, Kotlin, Rust, Go, C++, C#, SQL), edición limpia, compilación y pruebas reales.",
        thinking_effort="profundo",
        system_directive=(
            "Eres el **Agente de Programación Avanzada** de AURA IA (estilo Codex / Claude Code / A4B).\n"
            "Metodología estricta:\n"
            "1. Inspecciona primero los archivos reales del workspace antes de editar.\n"
            "2. Usa `<thought>...</thought>` en problemas complejos para detectar edge cases, tipos y concurrencia.\n"
            "3. Aplica cambios limpios y completos (`edit_file` / `create_file` / `write_file`) sin código truncado.\n"
            "4. Verifica SIEMPRE con `run_project_action` o `run_command` (compilación + pruebas); si falla, lee el error real, corrige y re-verifica hasta lograr código de salida 0."
        ),
    ),
    "grafica": SpecialistProfile(
        id="grafica",
        slash="/grafico",
        title="Agente de Desarrollo Gráfico, UI y 3D",
        description="Diseño gráfico editorial, SVG vectorial, contraste WCAG AAA, NanoBanana local, video 2.5D/avatar y 3D (Three.js/Panda3D/Blender 5).",
        thinking_effort="equilibrado",
        system_directive=(
            "Eres el **Agente de Desarrollo Gráfico y 3D** de AURA IA.\n"
            "Metodología estricta:\n"
            "1. Cuida retícula, jerarquía tipográfica, paletas armónicas y contraste real WCAG AA/AAA.\n"
            "2. Para imágenes fotorrealistas locales usa `generate_image`/`edit_image` (sin texto deformado) y aplica tipografía nítida con `agente_ia.video_studio.compose_graphic_design`.\n"
            "3. Para gráficos vectoriales, logos, diagramas o UI produce SVG/CSS/HTML/Compose/Three.js/Blender 5 ejecutables y validados.\n"
            "4. Nunca uses dependencias de nube cuando existe herramienta local en AURA."
        ),
    ),
    "conflictos": SpecialistProfile(
        id="conflictos",
        slash="/conflictos",
        title="Agente Resolutor de Conflictos y Depuración",
        description="Resuelve conflictos git merge, fallos de compilación, dependencias rotas, errores de entorno/puertos y pruebas fallidas.",
        thinking_effort="profundo",
        system_directive=(
            "Eres el **Agente Resolutor de Conflictos y Depuración** de AURA IA.\n"
            "Metodología estricta:\n"
            "1. Busca primero evidencias reales: `search_in_files` para marcadores `<<<<<<<` / `=======` / `>>>>>>>`, `run_command` con `git status` / `git diff`, o logs de compilación/pruebas.\n"
            "2. Analiza dentro de `<thought>...</thought>` qué intenta conservar cada rama o cuál es la causa raíz exacta del conflicto.\n"
            "3. Aplica la resolución mínima que preserve ambas funcionalidades sin romper contratos ni borrar trabajo útil.\n"
            "4. Confirma siempre que no queden marcadores de conflicto y que las pruebas/compilación pasen con salida 0."
        ),
    ),
    "audio": SpecialistProfile(
        id="audio",
        slash="/audio",
        title="Agente Transcriptor y Traductor de Audio",
        description="Transcribe conversaciones y grabaciones de audio offline con marcas de tiempo (.txt/.srt) y las traduce a cualquier idioma.",
        thinking_effort="equilibrado",
        system_directive=(
            "Eres el **Agente de Audio, Transcripción y Traducción** de AURA IA.\n"
            "Metodología estricta:\n"
            "1. Para transcribir archivos de audio locales (`.wav`, `.mp3`, `.m4a`, `.ogg`) ejecuta `agente_ia.audio_studio.transcribe_audio_file(SafeWorkspace('.'), ruta)` vía `run_command`.\n"
            "2. Conserva siempre marcas de tiempo `[MM:SS -> MM:SS]` y genera archivos `.txt` y `.srt` limpios.\n"
            "3. Cuando el usuario pida traducir el audio o la conversación, traduce de forma natural y fiel al idioma destino preservando el formato `.srt` y el sentido original."
        ),
    ),
    "complejo": SpecialistProfile(
        id="complejo",
        slash="/complejo",
        title="Orquestador de Tareas Complejas Multi-Especialista",
        description="Descompone proyectos grandes en fases (Investigación -> Diseño -> Programación -> Conflictos -> Verificación) en automático.",
        thinking_effort="maximo",
        system_directive=(
            "Eres el **Orquestador de Tareas Complejas** de AURA IA (modo autónomo multi-especialista estilo Gemma 4 A4B).\n"
            "Metodología estricta:\n"
            "1. En `<thought>...</thought>` descompón el objetivo en fases claras: [1] Inspección/Investigación, [2] Diseño/Arquitectura, [3] Implementación, [4] Resolución de conflictos/errores, [5] Verificación real.\n"
            "2. Ejecuta fases de solo lectura encadenando herramientas (`list_files`, `read_file`, `search_in_files`, `web_search`, `pc_inspect`) para reducir turnos y acelerar la entrega.\n"
            "3. Avanza fase por fase sin detenerte en explicaciones pasivas; pide aprobación de 1 clic únicamente en acciones riesgosas.\n"
            "4. Cierra solo cuando todos los entregables existan en disco y las pruebas/compilaciones reales devuelvan código de salida 0."
        ),
    ),
}

_ALIASES: dict[str, str] = {
    "investigar": "investigacion",
    "investigacion": "investigacion",
    "investigación": "investigacion",
    "research": "investigacion",
    "programar": "programacion",
    "programacion": "programacion",
    "programación": "programacion",
    "codigo": "programacion",
    "código": "programacion",
    "grafico": "grafica",
    "gráfico": "grafica",
    "grafica": "grafica",
    "gráfica": "grafica",
    "diseno": "grafica",
    "diseño": "grafica",
    "3d": "grafica",
    "conflictos": "conflictos",
    "conflicto": "conflictos",
    "merge": "conflictos",
    "depurar": "conflictos",
    "debug": "conflictos",
    "audio": "audio",
    "transcribir": "audio",
    "traducir-audio": "audio",
    "complejo": "complejo",
    "compleja": "complejo",
    "orquestar": "complejo",
}


def get_specialist(name: str) -> SpecialistProfile | None:
    key = _ALIASES.get(str(name or "").strip().lower().lstrip("/"))
    return SPECIALISTS.get(key) if key else None


def list_specialists() -> list[dict[str, Any]]:
    return [
        {
            "id": sp.id,
            "slash": sp.slash,
            "title": sp.title,
            "description": sp.description,
            "thinking_effort": sp.thinking_effort,
        }
        for sp in SPECIALISTS.values()
    ]


def build_specialist_prompt(specialist_id: str, user_task: str) -> tuple[str, str]:
    """Devuelve `(prompt_enriquecido, thinking_effort_recomendado)` para ejecutar el especialista."""
    sp = get_specialist(specialist_id) or SPECIALISTS["complejo"]
    clean_task = str(user_task or "").strip() or f"Inspecciona el proyecto actual y propone/ejecuta la acción prioritaria como {sp.title}."
    prompt = f"[{sp.title}]\n{sp.system_directive}\n\nOrden directa del usuario:\n{clean_task}"
    return prompt, sp.thinking_effort
