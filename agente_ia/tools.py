"""Definiciones de herramientas, prompts compactos y parser XML para modelos locales."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any


READ_TOOLS: set[str] = {
    "inspect_binary",
    "inspect_artifact",
    "read_skill",
    "list_files",
    "read_file",
    "search_in_files",
    "get_file_info",
}
WRITE_TOOLS: set[str] = {"create_file", "edit_file", "write_file", "delete_file"}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "inspect_binary",
            "description": "Inspecciona hash, formato PE, secciones, DLL importadas y muestra de cadenas; no ejecuta ni descompila el archivo.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_artifact",
            "description": "Inspección estática local básica de ejecutables PE/EXE/DLL, ELF, paquetes ZIP/APK/JAR, cadenas ASCII y SHA-256.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta relativa del archivo dentro del workspace."},
                    "mode": {"type": "string", "description": "Modo: summary, pe, archive o strings."},
                    "max_items": {"type": "integer", "description": "Límite de elementos a devolver (por defecto 30)."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": "Lee un bloque de una habilidad activa o archivo de referencia; el id está en el catálogo del sistema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "ID de la habilidad activa."},
                    "offset": {"type": "integer", "description": "Posición inicial en caracteres (0 por defecto)."},
                    "query": {"type": "string", "description": "Texto opcional para ubicar un bloque específico."},
                    "file": {"type": "string", "description": "Archivo Markdown relativo dentro de la habilidad (por defecto 'SKILL.md')."},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Lista archivos y subcarpetas dentro del workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Subcarpeta relativa (por defecto '.')."},
                    "max_depth": {"type": "integer", "description": "Profundidad máxima (1-5)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee un archivo de texto con números de línea.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta relativa del archivo."},
                    "start_line": {"type": "integer", "description": "Línea inicial (desde 1)."},
                    "end_line": {"type": "integer", "description": "Línea final."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_files",
            "description": "Busca texto o regex en archivos del workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Texto o expresión a buscar."},
                    "path": {"type": "string", "description": "Carpeta o archivo inicial ('.')."},
                    "file_pattern": {"type": "string", "description": "Patrón glob (ej. '*.py')."},
                    "use_regex": {"type": "boolean", "description": "Usar regex si es true."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_info",
            "description": "Consulta si existe un archivo, su tamaño y líneas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta relativa."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Propone crear un archivo nuevo (el usuario verá el diff y confirmará).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta del archivo nuevo."},
                    "content": {"type": "string", "description": "Contenido completo del archivo."},
                    "reason": {"type": "string", "description": "Motivo breve del cambio."},
                },
                "required": ["path", "content", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Propone reemplazar un bloque exacto y único en un archivo existente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta del archivo."},
                    "old_text": {"type": "string", "description": "Texto exacto a reemplazar (único)."},
                    "new_text": {"type": "string", "description": "Texto nuevo."},
                    "reason": {"type": "string", "description": "Motivo breve del cambio."},
                },
                "required": ["path", "old_text", "new_text", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Propone sobrescribir por completo un archivo (o crearlo si no existe).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta del archivo."},
                    "content": {"type": "string", "description": "Contenido completo nuevo."},
                    "reason": {"type": "string", "description": "Motivo breve del cambio."},
                },
                "required": ["path", "content", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Propone eliminar un archivo existente (requiere confirmación).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta del archivo a borrar."},
                    "reason": {"type": "string", "description": "Motivo breve."},
                },
                "required": ["path", "reason"],
            },
        },
    },
]


COMPACT_TOOL_SUMMARY = (
    "Herramientas disponibles:\n"
    "- list_files(path?, max_depth?)\n"
    "- read_file(path, start_line?, end_line?)\n"
    "- search_in_files(query, path?, file_pattern?, use_regex?)\n"
    "- get_file_info(path)\n"
    "- inspect_artifact(path, mode?, max_items?)\n"
    "- read_skill(id, offset?, file?)\n"
    "- create_file(path, content, reason)\n"
    "- edit_file(path, old_text, new_text, reason)\n"
    "- write_file(path, content, reason)\n"
    "- delete_file(path, reason)"
)


def build_system_prompt(
    workspace_path: str,
    *,
    include_xml_protocol: bool = False,
    compact: bool = True,
) -> str:
    """Construye el prompt del sistema adaptado a modelos locales pequeños o estándar."""
    if compact:
        base = (
            "Eres AURA Inteligencia Artificial, un agente de programación en español.\n"
            f"Workspace actual: {workspace_path}\n"
            "Reglas:\n"
            "1. Lee o busca archivos reales antes de editar; no inventes rutas ni código.\n"
            "2. Prefiere edit_file sobre write_file para cambios puntuales.\n"
            "3. Todo cambio en archivos requiere aprobación del usuario mediante diff.\n"
            "4. Sé claro, breve y directo."
        )
    else:
        base = (
            "Eres AURA Inteligencia Artificial, un agente experto en análisis y edición de código que responde en español.\n"
            f"Carpeta de trabajo (workspace): {workspace_path}\n"
            "Reglas estrictas:\n"
            "1. Inspecciona el proyecto con list_files, search_in_files o read_file antes de proponer cambios.\n"
            "2. Nunca inventes rutas, funciones o contenido de archivos que no hayas leído.\n"
            "3. Usa edit_file con contexto exacto y único siempre que modifiques un archivo existente; "
            "usa create_file para archivos nuevos y delete_file solo si el usuario lo pide.\n"
            "4. Cada modificación genera una vista previa diff que el usuario aprobará o rechazará; "
            "si la rechaza con comentario, corrige tu propuesta según sus indicaciones.\n"
            "5. Explica tus cambios de forma concisa y precisa."
        )

    if include_xml_protocol:
        xml_block = (
            "\n\nCuando necesites usar una herramienta, responde ÚNICAMENTE con uno o más bloques:\n"
            '<tool_call>{"name": "read_file", "arguments": {"path": "app.py"}}</tool_call>\n'
            f"{COMPACT_TOOL_SUMMARY}\ninspect_binary(path): inspección PE local de solo lectura.\n"
            "inspect_artifact(path, mode?, max_items?): inspección estática PE/ELF/ZIP/APK/cadenas.\n"
            "read_skill(id, offset=0, query, file): leer instrucciones de habilidad activa en bloques.\n"
            "Usa JSON válido dentro de <tool_call>...</tool_call>."
        )
        return base + xml_block
    return base


_XML_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL | re.IGNORECASE)
_FENCE_CALL_RE = re.compile(r"```tool_call\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _try_parse_json_obj(raw: str) -> dict[str, Any] | None:
    cleaned = raw.strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        # Intento secundario limpiando comas finales antes de } o ]
        fixed = re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            parsed = json.loads(fixed)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def parse_xml_tool_calls(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Extrae llamadas <tool_call>{...}</tool_call> o ```tool_call``` del texto del modelo."""
    if not text:
        return "", []

    calls: list[dict[str, Any]] = []
    spans: list[tuple[int, int]] = []

    for pattern in (_XML_CALL_RE, _FENCE_CALL_RE):
        for match in pattern.finditer(text):
            obj = _try_parse_json_obj(match.group(1))
            if not obj or "name" not in obj:
                continue
            name = str(obj["name"]).strip()
            args = obj.get("arguments") or obj.get("args") or {}
            if isinstance(args, str):
                parsed_args = _try_parse_json_obj(args)
                args = parsed_args if parsed_args is not None else {}
            if not isinstance(args, dict):
                args = {}
            calls.append(
                {
                    "id": f"xml_{uuid.uuid4().hex[:10]}",
                    "name": name,
                    "arguments": args,
                }
            )
            spans.append(match.span())

    if not spans:
        return text, []

    # Remover únicamente los bloques reconocidos para conservar el texto humano restante
    spans.sort()
    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        if start > cursor:
            parts.append(text[cursor:start])
        cursor = max(cursor, end)
    if cursor < len(text):
        parts.append(text[cursor:])

    clean_text = re.sub(r"\n{3,}", "\n\n", "".join(parts)).strip()
    return clean_text, calls


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimación ligera de tokens totales (~3.8 caracteres por token en español/código)."""
    total_chars = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total_chars += len(content)
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            try:
                total_chars += len(json.dumps(tool_calls, ensure_ascii=False))
            except Exception:
                pass
    return max(1, int(total_chars / 3.8))
