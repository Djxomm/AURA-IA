"""Pruebas unitarias del sandbox de workspace, diffs y escritura atómica."""

from __future__ import annotations

from pathlib import Path

import pytest

from agente_ia.workspace import (
    MISSING_HASH,
    SafeWorkspace,
    WorkspaceSecurityError,
    WorkspaceValidationError,
    compute_file_hash,
)


def test_security_blocks_traversal_and_git(tmp_path: Path) -> None:
    ws_dir = tmp_path / "proyecto"
    ws_dir.mkdir()
    (ws_dir / ".git").mkdir()
    (ws_dir / ".git" / "config").write_text("secret", encoding="utf-8")
    outside = tmp_path / "fuera.txt"
    outside.write_text("no deberia leerse", encoding="utf-8")

    ws = SafeWorkspace(ws_dir)

    with pytest.raises(WorkspaceSecurityError):
        ws.read_file("../fuera.txt")

    with pytest.raises(WorkspaceSecurityError):
        ws.read_file(str(outside))

    with pytest.raises(WorkspaceSecurityError):
        ws.prepare_write(".git/config", "corrupto")


def test_list_and_search_ignore_dirs_and_binary(tmp_path: Path) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("needle", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def saludar():\n    return 'hola needle'\n", encoding="utf-8")
    (tmp_path / "src" / "binario.bin").write_bytes(b"\x00\x01\x02needle")

    ws = SafeWorkspace(tmp_path)
    listing = ws.list_files()
    assert "src/app.py" in listing["entries"]
    assert all("node_modules" not in e for e in listing["entries"])

    matches = ws.search_in_files("needle")
    assert len(matches) == 1
    assert matches[0]["file"] == "src/app.py"
    assert matches[0]["line"] == 2

    regex_matches = ws.search_in_files(r"def\s+saludar", use_regex=True)
    assert len(regex_matches) == 1

    with pytest.raises(WorkspaceValidationError):
        ws.read_file("src/binario.bin")


def test_prepare_edit_crlf_and_unique_checks(tmp_path: Path) -> None:
    target = tmp_path / "win.py"
    target.write_bytes(b"linea1 = 1\r\nlinea2 = 2\r\nlinea3 = 2\r\n")
    ws = SafeWorkspace(tmp_path)

    # Coincidencia inexistente
    with pytest.raises(WorkspaceValidationError):
        ws.prepare_edit("win.py", "no_existe", "x")

    # Coincidencia ambigua (>1 vez)
    with pytest.raises(WorkspaceValidationError):
        ws.prepare_edit("win.py", "= 2", "= 9")

    # Edición usando LF contra archivo CRLF preserva CRLF original
    orig, prop, base_hash, diff = ws.prepare_edit("win.py", "linea1 = 1\nlinea2 = 2", "linea1 = 1\nlinea2 = 42")
    assert "\r\n" in prop
    assert diff["added"] == 1
    assert diff["removed"] == 1
    assert any(h["type"] == "add" and "linea2 = 42" in h["text"] for h in diff["hunks"])

    # Aplicar y verificar en disco
    ws.apply_change("win.py", "edit", prop, base_hash)
    assert target.read_bytes() == b"linea1 = 1\r\nlinea2 = 42\r\nlinea3 = 2\r\n"

    # Protección stale hash si cambió en disco
    with pytest.raises(WorkspaceValidationError):
        ws.apply_change("win.py", "edit", orig, base_hash)

    # Revertir restaura el original
    ws.revert_change("win.py", orig)
    assert target.read_bytes() == b"linea1 = 1\r\nlinea2 = 2\r\nlinea3 = 2\r\n"


def test_create_and_revert_deletes_created_file(tmp_path: Path) -> None:
    ws = SafeWorkspace(tmp_path)
    orig, prop, base_hash, diff = ws.prepare_create("nuevo/hola.py", "print('hola')\n")
    assert orig is None
    assert base_hash == MISSING_HASH
    assert diff["added"] == 1

    ws.apply_change("nuevo/hola.py", "create", prop, base_hash)
    created = tmp_path / "nuevo" / "hola.py"
    assert created.exists()
    assert compute_file_hash(created.read_text(encoding="utf-8")) == compute_file_hash(prop)

    # No permite prepare_create si ya existe
    with pytest.raises(WorkspaceValidationError):
        ws.prepare_create("nuevo/hola.py", "otro")

    # Revertir un archivo creado lo elimina
    ws.revert_change("nuevo/hola.py", None)
    assert not created.exists()
