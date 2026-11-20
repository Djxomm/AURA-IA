"""Persistencia SQLite thread-safe para configuración, sesiones, mensajes e historial."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AppSettings


def utc_now_iso() -> str:
    """Devuelve la marca temporal UTC en formato ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


def default_db_path() -> Path:
    """Ruta por defecto de la base SQLite dentro del proyecto."""
    return Path(__file__).resolve().parent.parent / "data" / "agente.db"


class Storage:
    """Almacén SQLite ligero para el estado de CódigoLocal."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._lock = threading.Lock()
        if db_path is None:
            resolved = default_db_path()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(resolved)
        elif str(db_path) == ":memory:":
            self.db_path = ":memory:"
        else:
            p = Path(db_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(p)

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages (session_id, created_at);
                CREATE TABLE IF NOT EXISTS change_history (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    before_content TEXT,
                    after_content TEXT,
                    unified_diff TEXT NOT NULL,
                    added_lines INTEGER NOT NULL,
                    removed_lines INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    feedback TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_changes_session
                    ON change_history (session_id, created_at);
                """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------------- Configuración ----------------

    def get_settings(self) -> AppSettings:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = 'app_settings'"
            ).fetchone()
        if row is None:
            settings = AppSettings()
            self.save_settings(settings)
            return settings
        try:
            data = json.loads(row["value"])
            return AppSettings.model_validate(data)
        except Exception:
            settings = AppSettings()
            self.save_settings(settings)
            return settings

    def save_settings(self, settings: AppSettings) -> AppSettings:
        payload = settings.model_dump_json()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO settings (key, value) VALUES ('app_settings', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (payload,),
            )
            self._conn.commit()
        return settings

    # ---------------- Sesiones ----------------

    def create_session(
        self,
        *,
        title: str = "Nueva sesión",
        workspace_path: str,
        provider: str,
        model: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        sid = session_id or uuid.uuid4().hex[:12]
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions (id, title, workspace_path, provider, model, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (sid, title, workspace_path, provider, model, now, now),
            )
            self._conn.commit()
        return self.get_session(sid)  # type: ignore[return-value]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT s.*,
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count
                FROM sessions s
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        workspace_path: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any] | None:
        existing = self.get_session(session_id)
        if not existing:
            return None
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                UPDATE sessions
                SET title = ?, workspace_path = ?, provider = ?, model = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    title if title is not None else existing["title"],
                    workspace_path if workspace_path is not None else existing["workspace_path"],
                    provider if provider is not None else existing["provider"],
                    model if model is not None else existing["model"],
                    now,
                    session_id,
                ),
            )
            self._conn.commit()
        return self.get_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM change_history WHERE session_id = ?", (session_id,))
            res = self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._conn.commit()
            return res.rowcount > 0

    # ---------------- Mensajes ----------------

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        msg_id = uuid.uuid4().hex[:14]
        now = utc_now_iso()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO messages (id, session_id, role, content, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (msg_id, session_id, role, content, meta_json, now),
            )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            self._conn.commit()
        return {
            "id": msg_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "created_at": now,
        }

    def get_messages(self, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if limit is not None:
                rows = self._conn.execute(
                    """
                    SELECT * FROM (
                        SELECT * FROM messages WHERE session_id = ?
                        ORDER BY created_at DESC LIMIT ?
                    ) sub ORDER BY created_at ASC
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                    (session_id,),
                ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            except Exception:
                item.pop("metadata_json", None)
                item["metadata"] = {}
            out.append(item)
        return out

    def get_first_user_message(self, session_id: str):
        """Keep the original request available when the recent-history window moves."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM messages WHERE session_id=? AND role='user' ORDER BY created_at,id LIMIT 1", (session_id,)).fetchone()
        return dict(row) if row else None

    def clear_session_messages(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (utc_now_iso(), session_id),
            )
            self._conn.commit()

    # ---------------- Historial de cambios ----------------

    def add_change_record(
        self,
        *,
        change_id: str,
        session_id: str,
        workspace_path: str,
        file_path: str,
        action: str,
        reason: str,
        before_content: str | None,
        after_content: str | None,
        unified_diff: str,
        added_lines: int,
        removed_lines: int,
        status: str = "pending",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO change_history (
                    id, session_id, workspace_path, file_path, action, reason,
                    before_content, after_content, unified_diff,
                    added_lines, removed_lines, status, feedback, created_at, resolved_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, NULL)
                """,
                (
                    change_id,
                    session_id,
                    workspace_path,
                    file_path,
                    action,
                    reason,
                    before_content,
                    after_content,
                    unified_diff,
                    added_lines,
                    removed_lines,
                    status,
                    now,
                ),
            )
            self._conn.commit()
        return self.get_change(change_id)  # type: ignore[return-value]

    def resolve_change_record(
        self,
        change_id: str,
        *,
        status: str,
        feedback: str = "",
    ) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                UPDATE change_history
                SET status = ?, feedback = ?, resolved_at = ?
                WHERE id = ?
                """,
                (status, feedback, now, change_id),
            )
            self._conn.commit()
        return self.get_change(change_id)

    def mark_change_reverted(self, change_id: str) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                UPDATE change_history
                SET status = 'reverted', resolved_at = ?
                WHERE id = ?
                """,
                (now, change_id),
            )
            self._conn.commit()
        return self.get_change(change_id)

    def get_change(self, change_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM change_history WHERE id = ?",
                (change_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_changes(self, session_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            if session_id:
                rows = self._conn.execute(
                    """
                    SELECT * FROM change_history
                    WHERE session_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM change_history ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]
