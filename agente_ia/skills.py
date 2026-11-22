"""Catálogo local de habilidades (SKILL.md) con metadatos separados y lectura bajo demanda."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any


MAX_SKILLS_CATALOG = 100
MAX_ENABLED_SKILLS = 4
MAX_SINGLE_ADD_BYTES = 512 * 1024
MAX_FILE_BYTES_IMPORT = 512 * 1024
MAX_SKILL_TOTAL_BYTES = 8 * 1024 * 1024
MAX_FILES_PER_SKILL = 120
READ_CHUNK_CHARS = 1600


def max_enabled_for_context(num_ctx: int | None = None) -> int:
    """Ajusta el límite de habilidades activas al contexto real disponible del modelo/PC."""
    if num_ctx is None:
        return MAX_ENABLED_SKILLS
    ctx = int(num_ctx)
    if ctx <= 2048:
        return 4
    if ctx <= 4096:
        return 6
    if ctx <= 8192:
        return 8
    if ctx <= 16384:
        return 10
    return 12


def read_chunk_for_context(num_ctx: int | None = None) -> int:
    """Ajusta el tamaño de lectura bajo demanda de read_skill según el contexto activo."""
    if num_ctx is None or int(num_ctx) <= 4096:
        return READ_CHUNK_CHARS
    if int(num_ctx) <= 8192:
        return 2400
    return 3200

_SKILL_ID_RE = re.compile(r"^[a-f0-9]{12,24}$")
_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _extract_frontmatter_meta(content: str, fallback_name: str = "Habilidad local") -> tuple[str, str]:
    """Extrae name y description de las cabeceras YAML iniciales sin cargar todo el texto."""
    head = content[:4000]
    title_match = re.search(r"^name:\s*(.+)$", head, re.MULTILINE)
    desc_match = re.search(r"^description:\s*(.+)$", head, re.MULTILINE)
    raw_name = title_match.group(1).strip().strip("\"'") if title_match else fallback_name
    raw_desc = desc_match.group(1).strip().strip("\"'") if desc_match else "Guía local de instrucciones"
    return raw_name.strip()[:80] or fallback_name, raw_desc.strip()[:160] or "Guía local de instrucciones"


def _atomic_write_text(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".skilltmp_", dir=str(target.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp_path, target)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


class SkillStore:
    """Almacén local de habilidades con índice liviano (index.json) y lectura acotada."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.index_path = self.directory / "index.json"
        self.lock = threading.RLock()

    def _validate_id(self, skill_id: str) -> str:
        sid = (skill_id or "").strip()
        if not _SKILL_ID_RE.fullmatch(sid):
            raise ValueError("Identificador de habilidad inválido.")
        return sid

    def _skill_dir(self, skill_id: str) -> Path:
        sid = self._validate_id(skill_id)
        return self.directory / sid

    def _load_index_unlocked(self) -> list[dict[str, Any]]:
        self._migrate_legacy_json_unlocked()
        if not self.index_path.is_file():
            return []
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(raw, list):
            return []
        valid: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict) and _SKILL_ID_RE.fullmatch(str(item.get("id", ""))):
                valid.append(item)
        return valid[:MAX_SKILLS_CATALOG]

    def _save_index_unlocked(self, records: list[dict[str, Any]]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        _atomic_write_text(self.index_path, payload)

    def _migrate_legacy_json_unlocked(self) -> None:
        """Migra archivos heredados <id>.json al formato separado index.json + <id>/SKILL.md."""
        if not self.directory.is_dir():
            return
        legacy_files = [
            p for p in sorted(self.directory.glob("*.json"))
            if p.name != "index.json" and _SKILL_ID_RE.fullmatch(p.stem)
        ]
        if not legacy_files:
            return

        current: list[dict[str, Any]] = []
        if self.index_path.is_file():
            try:
                loaded = json.loads(self.index_path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    current = [x for x in loaded if isinstance(x, dict)]
            except (OSError, ValueError):
                current = []

        existing_ids = {str(r.get("id")) for r in current}
        changed = False
        for legacy in legacy_files:
            try:
                rec = json.loads(legacy.read_text(encoding="utf-8"))
                sid = str(rec.get("id") or legacy.stem)
                if not _SKILL_ID_RE.fullmatch(sid):
                    continue
                content = str(rec.get("content") or "")
                sdir = self.directory / sid
                if content and not (sdir / "SKILL.md").exists():
                    _atomic_write_text(sdir / "SKILL.md", content)
                if sid not in existing_ids and len(current) < MAX_SKILLS_CATALOG:
                    current.append(
                        {
                            "id": sid,
                            "name": str(rec.get("name") or "Habilidad importada")[:80],
                            "description": str(rec.get("description") or "Guía local")[:160],
                            "enabled": bool(rec.get("enabled", False)),
                            "bytes": int(rec.get("bytes") or len(content.encode("utf-8"))),
                            "source": str(rec.get("source") or "manual"),
                            "license": str(rec.get("license") or ""),
                            "files": ["SKILL.md"],
                        }
                    )
                    existing_ids.add(sid)
                    changed = True
                legacy.unlink()
            except (OSError, ValueError):
                continue

        if changed:
            self._save_index_unlocked(current)

    def catalog(self) -> list[dict[str, Any]]:
        """Devuelve únicamente los metadatos del índice sin leer el contenido Markdown."""
        with self.lock:
            return [dict(r) for r in self._load_index_unlocked()]

    def get(self, skill_id: str) -> dict[str, Any] | None:
        sid = self._validate_id(skill_id)
        with self.lock:
            for item in self._load_index_unlocked():
                if item.get("id") == sid:
                    return dict(item)
        return None

    def add(
        self,
        content: str,
        name: str = "",
        *,
        description: str = "",
        source: str = "manual",
        license_name: str = "",
    ) -> str:
        """Registra una nueva habilidad a partir del texto de su SKILL.md."""
        raw_bytes = (content or "").encode("utf-8")
        if not (content or "").strip() or len(raw_bytes) > MAX_SINGLE_ADD_BYTES:
            raise ValueError("Usa un SKILL.md no vacío de hasta 512 KB.")

        parsed_name, parsed_desc = _extract_frontmatter_meta(content)
        final_name = (name or parsed_name).strip()[:80] or "Habilidad importada"
        final_desc = (description or parsed_desc).strip()[:160] or "Guía local de instrucciones"

        with self.lock:
            records = self._load_index_unlocked()
            digest = hashlib.sha256(raw_bytes).hexdigest()
            for existing in records:
                if existing.get("sha256") == digest:
                    return str(existing["id"])
            if len(records) >= MAX_SKILLS_CATALOG:
                raise ValueError(f"El catálogo admite hasta {MAX_SKILLS_CATALOG} habilidades.")

            sid = uuid.uuid4().hex[:24]
            sdir = self.directory / sid
            _atomic_write_text(sdir / "SKILL.md", content)

            record = {
                "id": sid,
                "name": final_name,
                "description": final_desc,
                "enabled": False,
                "bytes": len(raw_bytes),
                "sha256": digest,
                "source": source,
                "license": license_name,
                "files": ["SKILL.md"],
            }
            records.append(record)
            self._save_index_unlocked(records)
            return sid

    def import_directory(
        self,
        folder_path: str | Path,
        *,
        name: str = "",
        description: str = "",
        source: str = "folder",
        license_name: str = "",
    ) -> str:
        """Importa una carpeta con SKILL.md y archivos .md en reference/ o references/."""
        src_root = Path(folder_path).expanduser().resolve()
        if not src_root.is_dir():
            raise ValueError(f"La carpeta de habilidad no existe: {folder_path}")

        main_skill = src_root / "SKILL.md"
        if not main_skill.is_file():
            raise ValueError(f"La carpeta debe contener un archivo SKILL.md en la raíz: {src_root}")

        candidates: list[tuple[Path, str]] = [(main_skill, "SKILL.md")]
        for ref_dir_name in ("reference", "references"):
            ref_dir = src_root / ref_dir_name
            if not ref_dir.is_dir():
                continue
            for file_path in sorted(ref_dir.rglob("*.md")):
                if not file_path.is_file():
                    continue
                try:
                    resolved = file_path.resolve()
                    if not resolved.is_relative_to(src_root):
                        continue
                except OSError:
                    continue
                rel = resolved.relative_to(src_root).as_posix()
                candidates.append((resolved, rel))

        if len(candidates) > MAX_FILES_PER_SKILL:
            raise ValueError(
                f"La carpeta supera el límite de {MAX_FILES_PER_SKILL} archivos Markdown."
            )

        collected: list[tuple[str, bytes]] = []
        total_bytes = 0
        for file_path, rel_posix in candidates:
            try:
                data = file_path.read_bytes()
            except OSError as exc:
                raise ValueError(f"No se pudo leer '{rel_posix}': {exc}") from exc
            if len(data) > MAX_FILE_BYTES_IMPORT:
                raise ValueError(
                    f"El archivo '{rel_posix}' supera el máximo permitido de {MAX_FILE_BYTES_IMPORT // 1024} KB por documento."
                )
            total_bytes += len(data)
            if total_bytes > MAX_SKILL_TOTAL_BYTES:
                raise ValueError(f"La habilidad completa supera el máximo permitido de {MAX_SKILL_TOTAL_BYTES // (1024 * 1024)} MB.")
            collected.append((rel_posix, data))

        main_text = collected[0][1].decode("utf-8", errors="replace")
        if not main_text.strip():
            raise ValueError("El archivo SKILL.md está vacío.")
        parsed_name, parsed_desc = _extract_frontmatter_meta(main_text, fallback_name=src_root.name)
        final_name = (name or parsed_name).strip()[:80] or src_root.name
        final_desc = (description or parsed_desc).strip()[:160]

        with self.lock:
            records = self._load_index_unlocked()
            if len(records) >= MAX_SKILLS_CATALOG:
                raise ValueError(f"El catálogo admite hasta {MAX_SKILLS_CATALOG} habilidades.")

            sid = uuid.uuid4().hex[:24]
            dest_root = self.directory / sid
            try:
                for rel_posix, data in collected:
                    dest_file = dest_root / rel_posix
                    _atomic_write_text(dest_file, data.decode("utf-8", errors="replace"))
            except Exception:
                shutil.rmtree(dest_root, ignore_errors=True)
                raise

            record = {
                "id": sid,
                "name": final_name,
                "description": final_desc,
                "enabled": False,
                "bytes": total_bytes,
                "source": source,
                "license": license_name,
                "files": [rel for rel, _ in collected],
            }
            records.append(record)
            self._save_index_unlocked(records)
            return sid

    def enable(self, skill_id: str, enabled: bool, *, max_enabled: int | None = None) -> dict[str, Any]:
        """Activa o desactiva una habilidad respetando el máximo ajustado al contexto."""
        sid = self._validate_id(skill_id)
        limit = max(1, int(max_enabled)) if max_enabled is not None else MAX_ENABLED_SKILLS
        with self.lock:
            records = self._load_index_unlocked()
            target = next((r for r in records if r.get("id") == sid), None)
            if target is None:
                raise ValueError("Habilidad no encontrada.")

            if enabled and not target.get("enabled"):
                active_count = sum(1 for r in records if r.get("enabled"))
                if active_count >= limit:
                    raise ValueError(f"Activa como máximo {limit} habilidades para ahorrar contexto.")

            target["enabled"] = bool(enabled)
            self._save_index_unlocked(records)
            return dict(target)

    def delete(self, skill_id: str) -> None:
        """Elimina una habilidad del índice y borra sus archivos en disco."""
        sid = self._validate_id(skill_id)
        with self.lock:
            records = self._load_index_unlocked()
            new_records = [r for r in records if r.get("id") != sid]
            if len(new_records) == len(records):
                raise ValueError("Habilidad no encontrada.")
            self._save_index_unlocked(new_records)
            shutil.rmtree(self.directory / sid, ignore_errors=True)

    def read(
        self,
        skill_id: str,
        offset: int = 0,
        file: str = "SKILL.md",
        *,
        allow_disabled: bool = False,
        query: str = "",
        chunk_chars: int | None = None,
    ) -> dict[str, Any]:
        """Lee un bloque acotado de una habilidad o referencia autorizada."""
        sid = self._validate_id(skill_id)
        rel_req = (file or "SKILL.md").strip().replace("\\", "/").lstrip("/")
        if not rel_req:
            rel_req = "SKILL.md"

        with self.lock:
            records = self._load_index_unlocked()
            record = next((r for r in records if r.get("id") == sid), None)
            if record is None:
                raise ValueError("Habilidad no encontrada.")
            if not allow_disabled and not record.get("enabled"):
                raise ValueError("La habilidad está desactivada.")

            skill_dir = (self.directory / sid).resolve()
            candidate = (skill_dir / rel_req).resolve(strict=False)
            if not candidate.is_relative_to(skill_dir):
                raise ValueError("Ruta de archivo de habilidad fuera del directorio permitido.")
            if candidate.suffix.lower() != ".md":
                raise ValueError("Solo se permite leer archivos Markdown (.md) de la habilidad.")

            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            except FileNotFoundError as exc:
                raise ValueError(f"El archivo '{rel_req}' no existe en la habilidad.") from exc
            except OSError as exc:
                raise ValueError(f"No se pudo leer '{rel_req}': {exc}") from exc

            safe_offset = max(0, int(offset))
            if query:
                found=content.lower().find(str(query).lower()[:200], safe_offset)
                if found < 0:
                    return {"name":record["name"],"content":"No se encontró el texto solicitado.","next_offset":None}
                safe_offset=max(0,found-100)
            chunk_size = max(400, min(6400, int(chunk_chars))) if chunk_chars is not None else READ_CHUNK_CHARS
            chunk = content[safe_offset : safe_offset + chunk_size]
            next_off = safe_offset + len(chunk) if safe_offset + len(chunk) < len(content) else None
            rel_clean = candidate.relative_to(skill_dir).as_posix()

            payload: dict[str, Any] = {
                "id": sid,
                "name": record["name"],
                "file": rel_clean,
                "content": chunk,
                "offset": safe_offset,
                "next_offset": next_off,
                "total_chars": len(content),
            }
            if safe_offset == 0:
                payload["available_files"] = list(record.get("files") or ["SKILL.md"])[:16]
                payload["file_count"] = len(record.get("files") or ["SKILL.md"])
            return payload

    def list_bundled(self, bundled_dir: Path | None) -> list[dict[str, Any]]:
        """Lista las habilidades empaquetadas offline disponibles para instalar."""
        if not bundled_dir or not bundled_dir.is_dir():
            return []

        with self.lock:
            installed_by_source = {
                str(r.get("source")): r
                for r in self._load_index_unlocked()
                if str(r.get("source", "")).startswith("bundled:")
            }

        items: list[dict[str, Any]] = []
        for sub in sorted(bundled_dir.iterdir(), key=lambda p: p.name.lower()):
            if not sub.is_dir() or not _SLUG_RE.fullmatch(sub.name):
                continue
            skill_md = sub / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                head = skill_md.read_bytes()[:4096].decode("utf-8", errors="replace")
            except OSError:
                continue
            name, desc = _extract_frontmatter_meta(head, fallback_name=sub.name)
            source_tag = f"bundled:{sub.name}"
            existing = installed_by_source.get(source_tag)
            items.append(
                {
                    "slug": sub.name,
                    "name": name,
                    "description": desc,
                    "installed": existing is not None,
                    "installed_id": existing["id"] if existing else None,
                    "license": "Apache-2.0" if sub.name == "impeccable" else "Local",
                }
            )
        return items

    def install_bundled(self, bundled_dir: Path | None, slug: str) -> str:
        """Instala una habilidad incluida offline evitando duplicados."""
        if not bundled_dir or not bundled_dir.is_dir():
            raise ValueError("No hay habilidades empaquetadas disponibles en este entorno.")
        if not _SLUG_RE.fullmatch(slug or ""):
            raise ValueError("Nombre de habilidad incluida inválido.")

        target = (bundled_dir / slug).resolve(strict=False)
        if not target.is_relative_to(bundled_dir.resolve()) or not (target / "SKILL.md").is_file():
            raise ValueError(f"Habilidad incluida no encontrada: {slug}")

        source_tag = f"bundled:{slug}"
        with self.lock:
            for existing in self._load_index_unlocked():
                if existing.get("source") == source_tag:
                    return str(existing["id"])

        license_note = "Apache-2.0 (pbakaus/impeccable)" if slug == "impeccable" else "Incluida en CódigoLocal"
        return self.import_directory(
            target,
            source=source_tag,
            license_name=license_note,
        )

    def install_defaults(self, folder):
        folder=Path(folder)
        marker=self.directory / ".defaults-installed"
        if marker.exists() or not folder.is_dir(): return
        for item in self.list_bundled(folder): self.install_bundled(folder,item["slug"])
        for file in sorted(folder.glob("*.md")):
            if not (folder / file.stem).is_dir(): self.add(file.read_text("utf-8-sig"))
        self.directory.mkdir(parents=True,exist_ok=True)
        marker.touch()

    def manifest(self, *, max_enabled: int | None = None) -> str:
        """Genera un resumen compacto para el prompt con solo las habilidades activas."""
        limit = max(1, int(max_enabled)) if max_enabled is not None else MAX_ENABLED_SKILLS
        enabled = [r for r in self.catalog() if r.get("enabled")][:limit]
        if not enabled:
            return ""
        lines: list[str] = []
        for r in enabled:
            files = r.get("files") or ["SKILL.md"]
            extra_refs = [f for f in files if f != "SKILL.md"]
            refs_hint = f" | refs: {len(extra_refs)}" if extra_refs else ""
            lines.append(
                f"{r['id']} | {str(r['name'])[:50]} | {str(r['description'])[:68]}{refs_hint}"
            )
        return (
            "\nHabilidades activas (guías Markdown locales, no agregan herramientas nuevas ni omiten "
            "tu aprobación de diffs). Lee la necesaria bajo demanda con read_skill(id, offset, file):\n"
            + "\n".join(lines)
        )
