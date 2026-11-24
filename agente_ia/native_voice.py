"""Síntesis de voz refinada para AURA IA:
1. Voces neuronales naturales (es-MX-DaliaNeural para AURA/AURAX, es-MX-JorgeNeural para MATEO/ANGEL) vía edge-tts sin clave API.
2. ElevenLabs opcional con clave protegida por DPAPI de Windows.
3. Respaldo 100 % offline con prosodia natural y SSML limpio."""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import re
import urllib.request
from ctypes import wintypes
from pathlib import Path


NEURAL_VOICES: tuple[tuple[str, str], ...] = (
    ("auto", "Automática · Dalia (AURA/AURAX) / Jorge (MATEO/ANGEL)"),
    ("es-MX-DaliaNeural", "Dalia · Español México (femenina natural · AURA/AURAX)"),
    ("es-MX-JorgeNeural", "Jorge · Español México (masculina natural · MATEO/ANGEL)"),
    ("es-US-PalomaNeural", "Paloma · Español Latino (femenina cálida)"),
    ("es-US-AlonsoNeural", "Alonso · Español Latino (masculina cálida)"),
    ("es-ES-ElviraNeural", "Elvira · Español España (femenina clara)"),
    ("es-ES-AlvaroNeural", "Álvaro · Español España (masculina clara)"),
    ("en-US-AndrewMultilingualNeural", "Andrew · Multilingüe natural (ES/EN)"),
    ("en-US-AvaMultilingualNeural", "Ava · Multilingüe natural (ES/EN)"),
)


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("La clave protegida requiere Windows.")
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out = Blob()
    api = ctypes.windll.crypt32
    kernel = ctypes.windll.kernel32
    if decrypt:
        ok = api.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(out))
    else:
        ok = api.CryptProtectData(ctypes.byref(source), "AURA ElevenLabs", None, None, None, 1, ctypes.byref(out))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.data, out.size)
    finally:
        kernel.LocalFree(out.data)


class VoiceKey:
    def __init__(self, data):
        self.path = Path(data) / "elevenlabs.dpapi"

    def save(self, key):
        if not key.strip():
            return
        encrypted = protect(key.strip().encode())
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(encrypted)
        temporary.replace(self.path)

    def get(self):
        return protect(self.path.read_bytes(), True).decode() if self.path.exists() else ""

    def delete(self):
        self.path.unlink(missing_ok=True)


def naturalize_spoken_text(text: str, *, max_chars: int = 2400) -> str:
    """Limpia markdown, bloques de código, rutas y símbolos técnicos para que la voz suene humana y fluida."""
    if not text:
        return ""
    clean = re.sub(r"<(?:thought|think)>.*?</(?:thought|think)>", "", text, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"```.*?```", " Te dejé el código en pantalla. ", clean, flags=re.DOTALL)
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    clean = re.sub(r"https?://\S+", "enlace web", clean)
    clean = re.sub(r"`([^`]+)`", r"\1", clean)
    clean = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", clean)
    clean = re.sub(r"(?m)^\s*[-*•]\s+", "", clean)
    clean = re.sub(r"[*_~|>]", "", clean)
    clean = re.sub(r"\s*\n+\s*", ". ", clean)
    clean = re.sub(r"\.\s*\.+", ".", clean)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    if len(clean) > max_chars:
        cut = clean[:max_chars].rsplit(".", 1)[0].strip()
        clean = (cut + ".") if cut else clean[:max_chars]
    return clean


def pick_persona_neural_voice(model_name: str = "", configured_voice: str = "") -> str:
    """Selecciona voz neural mexicana cálida según el personaje activo (MATEO/ANGEL vs AURA/AURAX)."""
    pref = str(configured_voice or "").strip()
    if pref and pref != "auto" and "Neural" in pref:
        return pref
    low = str(model_name or "").lower()
    if any(k in low for k in ("mateo", "angel")):
        return "es-MX-JorgeNeural"
    return "es-MX-DaliaNeural"


def synthesize_neural(text: str, voice_name: str, out_path: str | Path, *, rate: int = 0) -> Path:
    """Sintetiza voz neural natural (MP3 24 kHz) con edge-tts sin clave API."""
    clean = naturalize_spoken_text(text)
    if not clean:
        raise ValueError("No hay texto hablable para sintetizar.")
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("edge-tts no está instalado.") from exc

    rate_pct = max(-35, min(35, int(rate) * 4))
    rate_str = f"{rate_pct:+d}%"
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    async def _run() -> None:
        comm = edge_tts.Communicate(clean, voice=voice_name, rate=rate_str)
        await comm.save(str(target))

    asyncio.run(_run())
    if not target.is_file() or target.stat().st_size < 128:
        raise RuntimeError("La síntesis neural no devolvió audio válido.")
    return target


def voices(key):
    if not key:
        raise ValueError("Introduce la clave de ElevenLabs dentro de AURA.")
    req = urllib.request.Request("https://api.elevenlabs.io/v2/voices?search=Kate&page_size=100", headers={"xi-api-key": key})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response).get("voices", [])


def synthesize(text, voice_id, key, path):
    if not re.fullmatch(r"[A-Za-z0-9_-]{5,100}", voice_id):
        raise ValueError("Selecciona o introduce el identificador de la voz Kate.")
    if not key:
        raise ValueError("Falta configurar la clave de ElevenLabs.")
    clean = naturalize_spoken_text(text)
    body = json.dumps(
        {
            "text": clean or text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25, "use_speaker_boost": True},
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/text-to-speech/" + voice_id + "?output_format=mp3_44100_128",
        data=body,
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        audio = response.read(20_000_001)
        if len(audio) > 20_000_000:
            raise ValueError("El audio supera el tamaño permitido.")
        if not audio:
            raise ValueError("ElevenLabs no devolvió audio.")
    Path(path).write_bytes(audio)
    return Path(path)
