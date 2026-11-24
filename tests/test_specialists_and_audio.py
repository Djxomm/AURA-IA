"""Pruebas de Agentes Especialistas (estilo A4B), Razonamiento paso a paso <thought>,
Estudio de Audio offline (Vosk .txt/.srt), Voz Neural natural y servidor rápido KV-RAM."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


def test_strip_thought_and_parallel_tool_calls():
    from agente_ia.tools import parse_xml_tool_calls, strip_thought_blocks

    raw = (
        "<thought>\n"
        "1. Primero inspecciono archivos y RAM en paralelo.\n"
        "2. Luego decido qué compilar.\n"
        "</thought>\n"
        "```tool_call\n"
        '{"name": "list_files", "arguments": {"path": "."}}\n'
        "```\n"
        "```tool_call\n"
        '{"name": "pc_inspect", "arguments": {"action": "system_info"}}\n'
        "```"
    )
    visible, thought = strip_thought_blocks(raw)
    assert "Primero inspecciono" in thought and "<thought>" not in visible
    clean, calls = parse_xml_tool_calls(raw)
    assert clean == ""
    assert [c["name"] for c in calls] == ["list_files", "pc_inspect"]


def test_six_autonomous_specialists_and_slash_commands():
    from agente_ia.agent_specialists import build_specialist_prompt, list_specialists
    from agente_ia.slash_palette import resolve_slash_command

    specs = list_specialists()
    ids = {s["id"] for s in specs}
    assert ids == {"investigacion", "programacion", "grafica", "conflictos", "audio", "complejo"}

    prompt, eff = build_specialist_prompt("conflictos", "Resuelve los conflictos de git en app.py")
    assert "<<<<<<<" in prompt and eff == "profundo"

    assert resolve_slash_command("/conversar")["type"] == "toggle_live_conversation"
    r_raz = resolve_slash_command("/razonar arregla el algoritmo")
    assert r_raz["type"] == "prompt" and r_raz["thinking_effort"] == "profundo" and "<thought>" in r_raz["prompt"]
    for cmd in ("/investigar", "/programar", "/grafico", "/conflictos", "/audio", "/traducir-audio", "/complejo"):
        res = resolve_slash_command(f"{cmd} tarea de prueba")
        assert res["type"] == "prompt" and res["auto_autonomous"] is True


def test_neural_voice_persona_and_naturalizer():
    from agente_ia.native_voice import naturalize_spoken_text, pick_persona_neural_voice

    assert pick_persona_neural_voice("AURA-MATEO-Pro-Q4_K_M.gguf") == "es-MX-JorgeNeural"
    assert pick_persona_neural_voice("AURA-ANGEL-5.6-Q4_K_M.gguf") == "es-MX-JorgeNeural"
    assert pick_persona_neural_voice("AURA-Lumen-2.0IB_V2.gguf") == "es-MX-DaliaNeural"
    assert pick_persona_neural_voice("AURA-MATEO-Pro.gguf", "es-US-PalomaNeural") == "es-US-PalomaNeural"

    text = "<thought>secreto</thought>\n### Resultado\nRevisa `app.py`:\n```python\nprint(1)\n```\nVer https://ejemplo.com"
    spoken = naturalize_spoken_text(text)
    assert "secreto" not in spoken
    assert "```" not in spoken and "Te dejé el código en pantalla" in spoken
    assert "https://" not in spoken


def test_audio_studio_wav_resample_srt_and_vosk(tmp_path):
    from agente_ia.audio_studio import (
        build_audio_translation_prompt,
        find_vosk_model,
        format_srt,
        format_transcript_text,
        load_pcm16_mono_16k,
        transcribe_audio_file,
    )
    from agente_ia.workspace import SafeWorkspace

    # Generar WAV estéreo 44.1 kHz (0.5 s silencio/tono suave) para probar remuestreo puro Python
    wav_path = tmp_path / "prueba.wav"
    sr = 44100
    nframes = sr // 2
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(nframes):
            val = int(1200 * math.sin(2 * math.pi * 440.0 * i / sr))
            frames += struct.pack("<hh", val, val)
        wf.writeframes(bytes(frames))

    pcm, dur = load_pcm16_mono_16k(wav_path)
    assert len(pcm) > 10000 and 0.45 <= dur <= 0.55

    segs = [{"start": 0.0, "end": 3.5, "text": "hola mateo"}, {"start": 3.8, "end": 7.2, "text": "revisemos el proyecto"}]
    srt = format_srt(segs)
    assert "00:00:00,000 --> 00:00:03,500" in srt and "hola mateo" in srt
    txt = format_transcript_text(segs)
    assert "[00:00 -> 00:03] hola mateo" in txt
    tprompt = build_audio_translation_prompt(txt, "inglés")
    assert "inglés" in tprompt and ".srt" in tprompt

    # Si está el modelo Vosk local en runtime/voz, probar transcripción real 100 % offline
    model_dir = find_vosk_model()
    if model_dir is not None:
        ws = SafeWorkspace(str(tmp_path))
        res = transcribe_audio_file(ws, "prueba.wav")
        assert res["ok"] is True
        assert (tmp_path / "prueba_transcripcion.txt").is_file()
        assert (tmp_path / "prueba_subtitulos.srt").is_file()


def test_zamara_multimodal_pairing_and_payload(tmp_path):
    import struct
    from agente_ia.chat_controls import model_label
    from agente_ia.model_library import curate_proven_models, discover, find_paired_multimodal_files, is_helper_gguf
    from agente_ia.native_core import NativeClient
    from agente_ia.native_voice import pick_persona_neural_voice
    from agente_ia.slash_palette import resolve_slash_command

    def _mk_gguf(p: Path, arch: str = "gemma4", name: str = "Gemma 4 E4B It"):
        def _s(x: str) -> bytes:
            b = x.encode("utf-8")
            return struct.pack("<Q", len(b)) + b
        kvs = [("general.architecture", 8, _s(arch)), ("general.name", 8, _s(name)), (f"{arch}.block_count", 4, struct.pack("<I", 42)), (f"{arch}.context_length", 4, struct.pack("<I", 131072))]
        buf = bytearray(b"GGUF") + struct.pack("<IQQ", 3, 0, len(kvs))
        for k, kind, val in kvs:
            buf += _s(k) + struct.pack("<I", kind) + val
        p.write_bytes(bytes(buf) + b"\x00" * 1024)

    z = tmp_path / "AURA-Zamara-Multimodal-E4B-Q4_K_M.gguf"
    mm = tmp_path / "mmproj-AURA-Zamara-Multimodal-E4B-Q8_0.gguf"
    mtp = tmp_path / "mtp-AURA-Zamara-Multimodal-E4B-Q8_0.gguf"
    _mk_gguf(z); _mk_gguf(mm); _mk_gguf(mtp)

    assert is_helper_gguf(mm) and is_helper_gguf(mtp) and not is_helper_gguf(z)
    assert discover([tmp_path]) == [z.resolve()]
    assert curate_proven_models([z, mm, mtp]) == [z.resolve()]
    assert model_label(z) == "AURA - Zamara V8.2"
    assert model_label(tmp_path / "AURA-Zamara-V8.2-E4B-Q4_K_M.gguf") == "AURA - Zamara V8.2"
    assert pick_persona_neural_voice(z.name) == "es-MX-DaliaNeural"
    assert resolve_slash_command("/zamara analiza esta foto")["type"] == "switch_zamara"

    paired = find_paired_multimodal_files(z)
    assert paired["mmproj"] == mm.resolve() and paired["mtp"] == mtp.resolve()

    img = tmp_path / "foto.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    wav = tmp_path / "voz.wav"
    wav.write_bytes(b"RIFFfakeWAVE")
    mm_msgs = NativeClient._build_multimodal_messages([{"role": "user", "content": "Analiza ambos"}], [img, wav])
    parts = mm_msgs[0]["content"]
    assert isinstance(parts, list) and [p["type"] for p in parts] == ["text", "image_url", "input_audio"]


def test_repetition_loop_detector_catches_degenerate_import_loop_without_false_positives():
    from agente_ia.native_core import _has_repetition_loop

    loop = (
        'import math\nfrom panda3d.core import Vec3, Vec4, '
        + "AmbientLight, DirectionalLight, PointLight, Vec2, Vec3, Vec4, " * 6
    )
    assert _has_repetition_loop(loop) is True

    normal_code = "\n".join(f"def step_{i}(value):\n    return value + {i}" for i in range(12))
    assert _has_repetition_loop(normal_code) is False
    assert _has_repetition_loop("    \n" * 40) is False


def test_server_stream_peek_attribute_error_reports_clean_cancel(tmp_path, monkeypatch):
    import urllib.request
    from agente_ia.config import AppSettings
    from agente_ia.native_core import NativeClient
    from agente_ia.providers import ProviderError

    model = tmp_path / "dummy.gguf"
    model.write_bytes(b"GGUF")
    client = NativeClient(tmp_path, tmp_path / "data", model)
    monkeypatch.setattr(client, "_ensure_server", lambda *a, **kw: 18080)

    class _BrokenStream:
        def __iter__(self):
            return self
        def __next__(self):
            client.cancelled.set()
            raise AttributeError("'NoneType' object has no attribute 'peek'")
        def close(self):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=300: _BrokenStream())
    try:
        client._generate_server(
            "hola", 64, AppSettings(temperature=0.0), True, lambda _: None,
            tmp_path, 2048, [], None, ("<|im_end|>",),
        )
        assert False, "Debió lanzar ProviderError limpio"
    except ProviderError as exc:
        assert "detenida por el usuario" in str(exc).lower()


