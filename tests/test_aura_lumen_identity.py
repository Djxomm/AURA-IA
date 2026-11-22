"""Tests for custom GGUF model identity labels (AURA - Lumen) and bare Qwen2.5 tool JSON parsing."""

import struct
from pathlib import Path

from agente_ia.chat_controls import model_label
from agente_ia.tools import parse_xml_tool_calls


def _write_minimal_gguf(path: Path, general_name: str) -> None:
    def _str(value: str) -> bytes:
        raw = value.encode("utf-8")
        return struct.pack("<Q", len(raw)) + raw

    header = b"GGUF" + struct.pack("<IQQ", 3, 0, 2)
    kv1 = _str("general.architecture") + struct.pack("<I", 8) + _str("qwen2")
    kv2 = _str("general.name") + struct.pack("<I", 8) + _str(general_name)
    path.write_bytes(header + kv1 + kv2)


def test_model_label_reads_custom_gguf_general_name(tmp_path: Path) -> None:
    gguf = tmp_path / "AURA-Lumen-2.0IB_V1-Q4_K_M.gguf"
    _write_minimal_gguf(gguf, "AURA - Lumen 2.0IB_V1")
    assert model_label(gguf) == "AURA - Lumen 2.0IB_V1"


def test_model_label_fallback_for_aura_lumen_filename() -> None:
    assert model_label(Path("AURA-Lumen-2.0IB_V1-Q4_K_M.gguf")) == "AURA - Lumen 2.0IB_V1"
    assert model_label(Path("qwen2.5-coder-1.5b-instruct-q4_k_m.gguf")) == "AURA Ligero · 1.5B"


def test_parse_xml_tool_calls_accepts_bare_known_tool_json() -> None:
    raw = '{"name": "edit_file", "arguments": {"path": "ui/app.py", "old_text": "a", "new_text": "b", "reason": "add"}}extra'
    clean, calls = parse_xml_tool_calls(raw)
    assert clean == ""
    assert len(calls) == 1
    assert calls[0]["name"] == "edit_file"
    assert calls[0]["arguments"]["path"] == "ui/app.py"


def test_parse_xml_tool_calls_ignores_arbitrary_json() -> None:
    raw = '{"name": "unknown_fn", "arguments": {"x": 1}}'
    clean, calls = parse_xml_tool_calls(raw)
    assert calls == []
    assert clean == raw
