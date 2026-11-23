"""Pruebas del estudio local de diseño gráfico, video cinemático 2.5D, avatar parlante WAV y script 3D Blender 5."""

from __future__ import annotations

import ast
import math
import struct
import wave
from pathlib import Path

from PIL import Image

from agente_ia.skills import SkillStore
from agente_ia.slash_palette import build_slash_catalog, resolve_slash_command
from agente_ia.video_studio import (
    compose_graphic_design,
    generate_blender_3d_video_script,
    render_cinematic_video,
    render_talking_avatar_video,
)
from agente_ia.workspace import SafeWorkspace


def _make_sample_wav(path: Path, seconds: float = 1.0, rate: int = 8000) -> None:
    n = int(seconds * rate)
    samples = [int(16000 * math.sin(2 * math.pi * 440 * i / rate) * (0.3 + 0.7 * (i % 1000 < 500))) for i in range(n)]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{n}h", *samples))


def test_graphic_design_cinematic_video_avatar_and_blender_script(tmp_path: Path):
    ws = SafeWorkspace(str(tmp_path))

    # 1. Imagen base local para pruebas
    base_img = tmp_path / "base.png"
    Image.new("RGB", (320, 320), (24, 60, 110)).save(base_img)

    # 2. Diseño gráfico profesional 16:9 con tipografía nítida
    gd = compose_graphic_design(
        ws,
        "diseno/portada.png",
        title="AURA IA · Estudio Creativo",
        subtitle="Diseño gráfico, 3D y video 100 % offline",
        badge="NUEVO",
        background_path="base.png",
        width=640,
        height=360,
    )
    assert gd["ok"] is True and gd["bytes"] > 1000
    assert (tmp_path / gd["path"]).is_file()

    # 3. Video cinemático 2.5D Ken Burns offline
    vid = render_cinematic_video(
        ws,
        ["diseno/portada.png"],
        "videos/promo.webp",
        width=320,
        height=180,
        fps=8,
        seconds_per_slide=1.0,
        captions=["Escena 1 · Estudio AURA"],
    )
    assert vid["ok"] is True and vid["frames"] == 8
    assert (tmp_path / vid["path"]).is_file()

    # 4. Avatar parlante sincronizado con audio WAV real
    wav_file = tmp_path / "voz.wav"
    _make_sample_wav(wav_file, seconds=1.0)
    av = render_talking_avatar_video(
        ws,
        "base.png",
        "videos/avatar.webp",
        audio_wav_path="voz.wav",
        caption="Hola, soy AURA IA funcionando local",
        width=256,
        height=256,
        fps=8,
    )
    assert av["ok"] is True and av["frames"] >= 6
    assert (tmp_path / av["path"]).is_file()

    # 5. Script Blender 5.x para video 3D realista MP4 H.264 (válido en AST)
    b3d = generate_blender_3d_video_script(ws, "escenas/render_3d.py", video_output_path="renders/clip.mp4", frames=48)
    assert b3d["ok"] is True
    code = (tmp_path / b3d["script"]).read_text(encoding="utf-8")
    ast.parse(code)
    assert "FFMPEG" in code and "H264" in code and "Principled BSDF" in code


def test_slash_video_and_diseno_work_with_and_without_skill(tmp_path: Path):
    r = resolve_slash_command("/video crea un clip 3D realista en Blender 5", None)
    assert r["type"] == "prompt" and r.get("auto_autonomous") is True

    store = SkillStore(tmp_path / "skills")
    bundle = tmp_path / "bundle"
    (bundle / "video-diseno-studio").mkdir(parents=True)
    (bundle / "video-diseno-studio" / "SKILL.md").write_text(
        "---\nname: video-diseno-studio\ndescription: Video local, avatar y diseño gráfico\n---\n\n# Estudio\n",
        encoding="utf-8",
    )
    sid = store.install_bundled(bundle, "video-diseno-studio")
    cmds = {e.command for e in build_slash_catalog(store)}
    assert {"/video", "/video-diseno-studio"} <= cmds
    r2 = resolve_slash_command("/diseno diseña una miniatura moderna para mi app", store)
    assert r2["type"] == "invoke_skill" and r2["skill_id"] == sid and r2.get("auto_autonomous") is True
