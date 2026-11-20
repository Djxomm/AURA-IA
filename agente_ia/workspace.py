"""Sandbox seguro del workspace, búsqueda, lectura, diffs y escritura atómica."""

from __future__ import annotations

import difflib
import fnmatch
import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any


IGNORED_DIRS: set[str] = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".next",
    ".mypy_cache",
}

MISSING_HASH = "__MISSING__"
MAX_SEARCH_FILE_BYTES = 512 * 1024


class WorkspaceError(Exception):
    """Error base de operaciones en el workspace."""


class WorkspaceSecurityError(WorkspaceError):
    """Se intentó acceder o escribir fuera del sandbox permitido."""


class WorkspaceValidationError(WorkspaceError):
    """Error de validación de archivo, coincidencia o estado en disco."""


def compute_file_hash(content: str | None) -> str:
    """Calcula el SHA-256 del contenido o devuelve MISSING_HASH si no existe."""
    if content is None:
        return MISSING_HASH
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _is_binary_bytes(sample: bytes) -> bool:
    return b"\x00" in sample[:8192]


def _detect_newline(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n"


def _parse_hunks_from_unified(unified_lines: list[str]) -> tuple[list[dict[str, Any]], int, int]:
    """Convierte líneas de unified_diff en filas estructuradas para UI y CLI."""
    rows: list[dict[str, Any]] = []
    added = 0
    removed = 0
    old_ln = 0
    new_ln = 0
    hunk_re = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")

    for raw in unified_lines:
        line = raw.rstrip("\r\n")
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        m = hunk_re.match(line)
        if m:
            old_ln = int(m.group(1))
            new_ln = int(m.group(2))
            rows.append(
                {
                    "type": "hunk",
                    "old_line": None,
                    "new_line": None,
                    "text": line,
                }
            )
            continue
        if line.startswith("+"):
            added += 1
            rows.append(
                {
                    "type": "add",
                    "old_line": None,
                    "new_line": new_ln,
                    "text": line[1:],
                }
            )
            new_ln += 1
        elif line.startswith("-"):
            removed += 1
            rows.append(
                {
                    "type": "del",
                    "old_line": old_ln,
                    "new_line": None,
                    "text": line[1:],
                }
            )
            old_ln += 1
        elif line.startswith(" "):
            rows.append(
                {
                    "type": "context",
                    "old_line": old_ln,
                    "new_line": new_ln,
                    "text": line[1:],
                }
            )
            old_ln += 1
            new_ln += 1
    return rows, added, removed


def build_diff(rel_path: str, original: str | None, proposed: str | None) -> dict[str, Any]:
    """Genera diff unificado y filas estructuradas para vistas unificada y lado a lado."""
    norm_path = rel_path.replace("\\", "/")
    orig_lines = (original or "").splitlines(keepends=True)
    prop_lines = (proposed or "").splitlines(keepends=True)

    # Asegurar salto de línea final consistente para que difflib no marque falsos cambios
    if orig_lines and not orig_lines[-1].endswith(("\n", "\r")):
        orig_lines[-1] += "\n"
    if prop_lines and not prop_lines[-1].endswith(("\n", "\r")):
        prop_lines[-1] += "\n"

    from_name = "/dev/null" if original is None else f"a/{norm_path}"
    to_name = "/dev/null" if proposed is None else f"b/{norm_path}"

    diff_lines = list(
        difflib.unified_diff(
            orig_lines,
            prop_lines,
            fromfile=from_name,
            tofile=to_name,
            n=3,
        )
    )
    unified_text = "".join(diff_lines)
    hunks, added, removed = _parse_hunks_from_unified(diff_lines)
    return {
        "unified_diff": unified_text,
        "hunks": hunks,
        "added": added,
        "removed": removed,
    }


class SafeWorkspace:
    """Acceso restringido a archivos dentro de una carpeta de trabajo."""

    def __init__(self, root: str | Path) -> None:
        root_path = Path(root).expanduser().resolve()
        if not root_path.exists() or not root_path.is_dir():
            raise WorkspaceValidationError(f"La carpeta del workspace no existe: {root}")
        self.root = root_path

    def to_rel_posix(self, path: Path) -> str:
        rel = path.relative_to(self.root)
        posix = rel.as_posix()
        return "." if posix == "." else posix

    def resolve_safe_path(self, rel_path: str, *, allow_write: bool = False, allow_root: bool = False) -> Path:
        raw = (rel_path or "").strip()
        if not raw:
            if allow_root:
                return self.root
            raise WorkspaceValidationError("La ruta del archivo no puede estar vacía.")

        cleaned = raw.replace("\\", "/")
        candidate = Path(cleaned)
        if candidate.is_absolute():
            resolved = candidate.resolve(strict=False)
        else:
            resolved = (self.root / candidate).resolve(strict=False)

        if not resolved.is_relative_to(self.root):
            raise WorkspaceSecurityError(
                f"Acceso denegado fuera del workspace: '{rel_path}'"
            )

        if resolved == self.root and not allow_root:
            raise WorkspaceValidationError("Debes indicar un archivo específico, no la raíz del workspace.")

        rel_parts = resolved.relative_to(self.root).parts
        if allow_write and ".git" in rel_parts:
            raise WorkspaceSecurityError("No está permitido modificar archivos dentro de .git/.")

        return resolved

    def _read_text_file(self, path: Path) -> str:
        data = path.read_bytes()
        if _is_binary_bytes(data):
            raise WorkspaceValidationError(
                f"'{self.to_rel_posix(path)}' es un archivo binario y no puede editarse como texto."
            )
        return data.decode("utf-8", errors="replace")

    def list_files(
        self,
        path: str = ".",
        *,
        max_depth: int = 3,
        max_entries: int = 250,
    ) -> dict[str, Any]:
        target = self.resolve_safe_path(path, allow_root=True)
        if not target.exists() or not target.is_dir():
            raise WorkspaceValidationError(f"Directorio no encontrado: '{path}'")

        count = 0
        truncated = False
        flat_items: list[str] = []

        def walk_dir(current: Path, depth: int) -> list[dict[str, Any]]:
            nonlocal count, truncated
            if depth > max_depth or count >= max_entries:
                return []
            nodes: list[dict[str, Any]] = []
            try:
                entries = sorted(
                    current.iterdir(),
                    key=lambda p: (not p.is_dir(), p.name.lower()),
                )
            except OSError:
                return []

            for entry in entries:
                if entry.name in IGNORED_DIRS:
                    continue
                if count >= max_entries:
                    truncated = True
                    break
                is_dir = entry.is_dir()
                rel = self.to_rel_posix(entry)
                count += 1
                if is_dir:
                    flat_items.append(f"{rel}/")
                    children = walk_dir(entry, depth + 1) if depth < max_depth else []
                    nodes.append(
                        {
                            "name": entry.name,
                            "path": rel,
                            "type": "dir",
                            "children": children,
                        }
                    )
                else:
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                    flat_items.append(rel)
                    nodes.append(
                        {
                            "name": entry.name,
                            "path": rel,
                            "type": "file",
                            "size": size,
                        }
                    )
            return nodes

        tree = walk_dir(target, 1)
        summary_lines = flat_items[:]
        if truncated:
            summary_lines.append(f"... (listado truncado a {max_entries} entradas)")

        return {
            "root": str(self.root),
            "base": self.to_rel_posix(target),
            "tree": tree,
            "entries": flat_items,
            "truncated": truncated,
            "text": "\n".join(summary_lines) if summary_lines else "(carpeta vacía)",
        }

    def read_file(
        self,
        path: str,
        *,
        start_line: int = 1,
        end_line: int = 80,
    ) -> dict[str, Any]:
        target = self.resolve_safe_path(path)
        if not target.exists() or not target.is_file():
            raise WorkspaceValidationError(f"Archivo no encontrado: '{path}'")

        text = self._read_text_file(target)
        lines = text.splitlines()
        total_lines = len(lines)
        s = max(1, int(start_line))
        e = max(s, int(end_line))
        slice_lines = lines[s - 1 : e]
        numbered = "\n".join(f"{idx}: {line}" for idx, line in enumerate(slice_lines, start=s))

        return {
            "path": self.to_rel_posix(target),
            "start_line": s,
            "end_line": min(e, total_lines),
            "total_lines": total_lines,
            "size_bytes": target.stat().st_size,
            "sha256": compute_file_hash(text),
            "content": text,
            "numbered_excerpt": numbered or "(archivo vacío)",
            "truncated": e < total_lines,
        }

    def get_file_info(self, path: str) -> dict[str, Any]:
        target = self.resolve_safe_path(path)
        if not target.exists():
            return {
                "path": self.to_rel_posix(target),
                "exists": False,
                "type": None,
            }
        if target.is_dir():
            return {
                "path": self.to_rel_posix(target),
                "exists": True,
                "type": "dir",
            }
        data = target.read_bytes()
        is_bin = _is_binary_bytes(data)
        lines = 0 if is_bin else len(data.decode("utf-8", errors="replace").splitlines())
        return {
            "path": self.to_rel_posix(target),
            "exists": True,
            "type": "file",
            "is_binary": is_bin,
            "size_bytes": len(data),
            "total_lines": lines,
            "sha256": None if is_bin else hashlib.sha256(data).hexdigest(),
        }

    def search_in_files(
        self,
        query: str,
        *,
        path: str = ".",
        file_pattern: str = "*",
        use_regex: bool = False,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        if not query:
            raise WorkspaceValidationError("El término de búsqueda no puede estar vacío.")
        base = self.resolve_safe_path(path, allow_root=True)
        if not base.exists():
            raise WorkspaceValidationError(f"Ruta de búsqueda no encontrada: '{path}'")

        pattern: re.Pattern[str] | None = None
        if use_regex:
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error as exc:
                raise WorkspaceValidationError(f"Expresión regular inválida: {exc}") from exc

        results: list[dict[str, Any]] = []
        query_lower = query.lower()

        def scan_file(fp: Path) -> None:
            if len(results) >= max_results:
                return
            if file_pattern != "*" and not fnmatch.fnmatch(fp.name, file_pattern):
                return
            try:
                if fp.stat().st_size > MAX_SEARCH_FILE_BYTES:
                    return
                raw = fp.read_bytes()
            except OSError:
                return
            if _is_binary_bytes(raw):
                return
            text = raw.decode("utf-8", errors="replace")
            rel = self.to_rel_posix(fp)
            for idx, line in enumerate(text.splitlines(), start=1):
                matched = bool(pattern.search(line)) if pattern else (query_lower in line.lower())
                if matched:
                    results.append(
                        {
                            "file": rel,
                            "line": idx,
                            "text": line[:240],
                        }
                    )
                    if len(results) >= max_results:
                        return

        if base.is_file():
            scan_file(base)
            return results

        for root_dir, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
            for fname in sorted(files):
                scan_file(Path(root_dir) / fname)
                if len(results) >= max_results:
                    return results
        return results

    # ---------------- Preparación de cambios (sin tocar disco) ----------------

    def prepare_create(self, path: str, content: str) -> tuple[None, str, str, dict[str, Any]]:
        target = self.resolve_safe_path(path, allow_write=True)
        if target.exists():
            raise WorkspaceValidationError(
                f"El archivo '{self.to_rel_posix(target)}' ya existe. Usa edit_file o write_file."
            )
        rel = self.to_rel_posix(target)
        diff = build_diff(rel, None, content)
        return None, content, MISSING_HASH, diff

    def prepare_write(self, path: str, content: str) -> tuple[str | None, str, str, dict[str, Any]]:
        target = self.resolve_safe_path(path, allow_write=True)
        rel = self.to_rel_posix(target)
        if target.exists():
            if target.is_dir():
                raise WorkspaceValidationError(f"'{rel}' es una carpeta, no un archivo.")
            original = self._read_text_file(target)
        else:
            original = None
        base_hash = compute_file_hash(original)
        diff = build_diff(rel, original, content)
        return original, content, base_hash, diff

    def prepare_edit(self, path: str, old_text: str, new_text: str) -> tuple[str, str, str, dict[str, Any]]:
        target = self.resolve_safe_path(path, allow_write=True)
        rel = self.to_rel_posix(target)
        if not target.exists() or not target.is_file():
            raise WorkspaceValidationError(f"Archivo no encontrado para editar: '{rel}'")
        if not old_text:
            raise WorkspaceValidationError("old_text no puede estar vacío en edit_file.")

        original = self._read_text_file(target)
        base_hash = compute_file_hash(original)
        orig_nl = _detect_newline(original)

        count = original.count(old_text)
        if count == 1:
            proposed = original.replace(old_text, new_text, 1)
        else:
            # Normalizar CRLF <-> LF para no fallar en archivos Windows
            norm_orig = original.replace("\r\n", "\n")
            norm_old = old_text.replace("\r\n", "\n")
            norm_new = new_text.replace("\r\n", "\n")
            norm_count = norm_orig.count(norm_old)
            if norm_count == 0:
                raise WorkspaceValidationError(
                    f"No se encontró old_text en '{rel}'. Lee el archivo primero con read_file "
                    "para copiar el fragmento exacto incluyendo sangría."
                )
            if norm_count > 1:
                raise WorkspaceValidationError(
                    f"old_text aparece {norm_count} veces en '{rel}'. Incluye más líneas de contexto "
                    "para que la coincidencia sea única."
                )
            replaced_lf = norm_orig.replace(norm_old, norm_new, 1)
            proposed = replaced_lf.replace("\n", "\r\n") if orig_nl == "\r\n" else replaced_lf

        diff = build_diff(rel, original, proposed)
        return original, proposed, base_hash, diff

    def prepare_delete(self, path: str) -> tuple[str, None, str, dict[str, Any]]:
        target = self.resolve_safe_path(path, allow_write=True)
        rel = self.to_rel_posix(target)
        if not target.exists() or not target.is_file():
            raise WorkspaceValidationError(f"Archivo no encontrado para eliminar: '{rel}'")
        original = self._read_text_file(target)
        base_hash = compute_file_hash(original)
        diff = build_diff(rel, original, None)
        return original, None, base_hash, diff

    # ---------------- Aplicación atómica y reversión ----------------

    def _atomic_write(self, target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".codigolocal_", dir=str(target.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
            os.replace(tmp_path, target)
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    def apply_change(
        self,
        path: str,
        action: str,
        proposed_content: str | None,
        expected_base_hash: str,
    ) -> None:
        target = self.resolve_safe_path(path, allow_write=True)
        current_content = self._read_text_file(target) if target.exists() and target.is_file() else None
        current_hash = compute_file_hash(current_content)
        if current_hash != expected_base_hash:
            raise WorkspaceValidationError(
                f"El archivo '{self.to_rel_posix(target)}' cambió en disco mientras se revisaba la propuesta."
            )

        if action == "delete":
            if target.exists():
                target.unlink()
            return

        if proposed_content is None:
            raise WorkspaceValidationError("Contenido propuesto vacío para operación de escritura.")
        self._atomic_write(target, proposed_content)

    def revert_change(self, path: str, original_content: str | None) -> None:
        target = self.resolve_safe_path(path, allow_write=True)
        if original_content is None:
            if target.exists() and target.is_file():
                target.unlink()
            return
        self._atomic_write(target, original_content)
