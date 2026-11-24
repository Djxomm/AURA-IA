"""Estudio local de Audio para AURA IA:
- Transcripción 100 % offline de conversaciones y archivos de audio (WAV nativo + MP3/M4A/OGG con ffmpeg)
  usando el motor Vosk incluido en AURA (`runtime/voz/vosk-model-*`).
- Exportación automática con marcas de tiempo a `.txt` y subtítulos `.srt`.
- Preparación de traducción de conversaciones de audio con `AURA - MATEO Pro` / `ANGEL 5.6`."""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

from .workspace import SafeWorkspace


def find_vosk_model(runtime: Path | str | None = None) -> Path | None:
    """Busca un modelo Vosk local instalado en runtime/voz o AppData."""
    candidates: list[Path] = []
    if runtime is not None:
        rt = Path(runtime).resolve()
        candidates.extend([rt / "voz", rt.parent / "runtime" / "voz"])
    pkg_voz = Path(__file__).resolve().parent.parent / "runtime" / "voz"
    candidates.append(pkg_voz)
    local_app = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AURA_IA" / "voz"
    candidates.append(local_app)

    for root in candidates:
        if not root.is_dir():
            continue
        for sub in sorted(root.iterdir()):
            if sub.is_dir() and sub.name.lower().startswith("vosk-model"):
                return sub
    return None


def _pcm16_resample_mono(raw: bytes, channels: int, sample_width: int, src_rate: int, dst_rate: int = 16000) -> bytes:
    """Convierte PCM WAV arbitrario (8/16/24-bit, mono/estéreo, cualquier Hz) a PCM16 mono 16 kHz sin dependencias externas."""
    if sample_width == 2:
        total_samples = len(raw) // 2
        samples = struct.unpack(f"<{total_samples}h", raw[: total_samples * 2])
    elif sample_width == 1:
        samples = tuple((b - 128) * 256 for b in raw)
    elif sample_width == 3:
        out_s: list[int] = []
        for i in range(0, len(raw) - 2, 3):
            val = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
            if val & 0x800000:
                val -= 0x1000000
            out_s.append(max(-32768, min(32767, val >> 8)))
        samples = tuple(out_s)
    else:
        raise ValueError(f"Profundidad de bits WAV no soportada: {sample_width * 8}-bit")

    if channels > 1:
        mono = [
            int(sum(samples[i : i + channels]) / channels)
            for i in range(0, len(samples) - channels + 1, channels)
        ]
    else:
        mono = list(samples)

    if not mono:
        return b""
    if src_rate == dst_rate:
        return struct.pack(f"<{len(mono)}h", *mono)

    ratio = src_rate / float(dst_rate)
    out_len = max(1, int(len(mono) / ratio))
    resampled: list[int] = []
    last_idx = len(mono) - 1
    for i in range(out_len):
        pos = i * ratio
        idx = int(pos)
        frac = pos - idx
        if idx >= last_idx:
            val = mono[last_idx]
        else:
            val = int(mono[idx] * (1.0 - frac) + mono[idx + 1] * frac)
        resampled.append(max(-32768, min(32767, val)))
    return struct.pack(f"<{len(resampled)}h", *resampled)


def load_pcm16_mono_16k(audio_path: Path) -> tuple[bytes, float]:
    """Carga un archivo de audio como PCM16 mono 16 kHz. WAV nativo; otros formatos usan ffmpeg si existe."""
    p = Path(audio_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"No existe el archivo de audio: {p}")

    ext = p.suffix.lower()
    if ext == ".wav":
        with wave.open(str(p), "rb") as wf:
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            sr = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        pcm = _pcm16_resample_mono(frames, ch, sw, sr, 16000)
        duration = len(pcm) / (2.0 * 16000.0)
        return pcm, round(duration, 2)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError(
            f"El formato '{ext}' requiere `ffmpeg` para convertirse a WAV 16 kHz mono; "
            "convierte el audio a `.wav` o instala `ffmpeg`."
        )
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = Path(tmp.name)
    try:
        proc = subprocess.run(
            [ffmpeg, "-y", "-i", str(p), "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(tmp_wav)],
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            raise ValueError(f"ffmpeg falló convirtiendo {p.name}: {proc.stderr[-300:]}")
        return load_pcm16_mono_16k(tmp_wav)
    finally:
        tmp_wav.unlink(missing_ok=True)


def _fmt_srt_time(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    hrs, rem = divmod(ms, 3_600_000)
    mins, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def format_srt(segments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for idx, seg in enumerate(segments, start=1):
        txt = str(seg.get("text") or "").strip()
        if not txt:
            continue
        start = float(seg.get("start", 0.0))
        end = max(start + 0.3, float(seg.get("end", start + 2.0)))
        lines.append(f"{idx}\n{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}\n{txt}\n")
    return "\n".join(lines).strip() + ("\n" if lines else "")


def format_transcript_text(segments: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for seg in segments:
        txt = str(seg.get("text") or "").strip()
        if not txt:
            continue
        s = int(float(seg.get("start", 0.0)))
        e = int(float(seg.get("end", s)))
        rows.append(f"[{s // 60:02d}:{s % 60:02d} -> {e // 60:02d}:{e % 60:02d}] {txt}")
    return "\n".join(rows) + ("\n" if rows else "")


def transcribe_audio_file(
    workspace: SafeWorkspace,
    audio_path: str,
    *,
    runtime: Path | str | None = None,
    save_txt: bool = True,
    save_srt: bool = True,
) -> dict[str, Any]:
    """Transcribe un archivo de audio/conversación 100 % offline con Vosk, generando `.txt` y `.srt`."""
    resolved = workspace.resolve_safe_path(audio_path)
    model_dir = find_vosk_model(runtime)
    if model_dir is None:
        raise ValueError("No se encontró un modelo Vosk en `runtime/voz/` para transcripción offline.")
    try:
        import vosk
    except ImportError as exc:
        raise ValueError("Falta la librería `vosk` en el entorno Python.") from exc

    pcm, duration = load_pcm16_mono_16k(resolved)
    vosk.SetLogLevel(-1)
    model = vosk.Model(str(model_dir))
    rec = vosk.KaldiRecognizer(model, 16000)
    rec.SetWords(True)

    segments: list[dict[str, Any]] = []
    chunk_bytes = 8000  # 0.25 s por bloque (16000 Hz * 2 bytes)

    def _collect(res_json: str) -> None:
        data = json.loads(res_json)
        txt = str(data.get("text") or "").strip()
        if not txt:
            return
        words = data.get("result") or []
        if words:
            start = float(words[0].get("start", 0.0))
            end = float(words[-1].get("end", start + 0.5))
        else:
            start = float(segments[-1]["end"]) if segments else 0.0
            end = min(duration, start + 2.0)
        segments.append({"start": round(start, 2), "end": round(end, 2), "text": txt})

    for offset in range(0, len(pcm), chunk_bytes):
        block = pcm[offset : offset + chunk_bytes]
        if rec.AcceptWaveform(block):
            _collect(rec.Result())
    _collect(rec.FinalResult())

    full_text = " ".join(s["text"] for s in segments).strip()
    txt_rel = None
    srt_rel = None
    stem = resolved.stem
    parent_rel = workspace.to_rel_posix(resolved.parent)
    prefix = f"{parent_rel}/{stem}" if parent_rel and parent_rel != "." else stem

    if save_txt:
        txt_target = workspace.resolve_safe_path(f"{prefix}_transcripcion.txt", allow_write=True)
        txt_target.parent.mkdir(parents=True, exist_ok=True)
        txt_target.write_text(format_transcript_text(segments) or (full_text + "\n"), encoding="utf-8")
        txt_rel = workspace.to_rel_posix(txt_target)

    if save_srt:
        srt_target = workspace.resolve_safe_path(f"{prefix}_subtitulos.srt", allow_write=True)
        srt_target.parent.mkdir(parents=True, exist_ok=True)
        srt_target.write_text(format_srt(segments), encoding="utf-8")
        srt_rel = workspace.to_rel_posix(srt_target)

    return {
        "ok": True,
        "audio": workspace.to_rel_posix(resolved),
        "duration_sec": duration,
        "segments_count": len(segments),
        "segments": segments,
        "text": full_text,
        "txt_path": txt_rel,
        "srt_path": srt_rel,
        "model_used": model_dir.name,
    }


def build_audio_translation_prompt(transcript_text: str, target_language: str = "inglés") -> str:
    return (
        f"Traduce fielmente la siguiente transcripción de conversación de audio al idioma **{target_language}**, "
        "conservando las marcas de tiempo `[MM:SS -> MM:SS]`, el tono natural y entregando además un bloque `.srt` limpio:\n\n"
        f"{transcript_text.strip()}"
    )
