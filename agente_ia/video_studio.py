"""Estudio 100 % local de Diseño Gráfico (estilo NanoBanana + tipografía nítida),
Video Cinemático 2.5D, Avatar Parlante local por audio WAV y generador de scripts de Video 3D para Blender 5."""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .workspace import SafeWorkspace, WorkspaceError


def find_ffmpeg(runtime: Path | None = None) -> str | None:
    """Detecta ffmpeg.exe en el runtime de AURA o en PATH del sistema."""
    candidates: list[Path] = []
    if runtime is not None:
        rt = Path(runtime).resolve()
        candidates.extend([rt / "herramientas/ffmpeg/ffmpeg.exe", rt / "herramientas/ffmpeg/bin/ffmpeg.exe"])
    pkg_rt = Path(__file__).resolve().parent.parent / "runtime"
    candidates.extend([pkg_rt / "herramientas/ffmpeg/ffmpeg.exe", pkg_rt / "herramientas/ffmpeg/bin/ffmpeg.exe"])
    for cand in candidates:
        if cand.is_file():
            return str(cand.resolve())
    return shutil.which("ffmpeg")


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
        if bold
        else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
    )
    win_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for name in names:
        for cand in (win_fonts / name, Path(name)):
            if cand.is_file():
                try:
                    return ImageFont.truetype(str(cand), size=max(12, int(size)))
                except OSError:
                    continue
    return ImageFont.load_default()


def _hex_rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    c = str(color or "#0f172a").strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        return (15, 23, 42, alpha)
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> list[str]:
    words = str(text or "").split()
    if not words:
        return []
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        test = f"{cur} {w}"
        box = draw.textbbox((0, 0), test, font=font)
        if box[2] - box[0] <= max_width:
            cur = test
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def compose_graphic_design(
    workspace: SafeWorkspace,
    output_path: str,
    *,
    title: str,
    subtitle: str = "",
    badge: str = "",
    background_path: str | None = None,
    width: int = 1280,
    height: int = 720,
    accent_color: str = "#38bdf8",
    bg_color: str = "#091322",
    grade: str = "cinematic",
) -> dict[str, Any]:
    """Combina imagen fotorrealista local (o fondo degradado) con diseño gráfico tipográfico nítido
    (cartel, miniatura, banner o mockup publicitario) 100 % offline."""
    out_file = workspace.resolve_safe_path(output_path, allow_write=True)
    if out_file.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise WorkspaceError("El archivo de diseño debe terminar en .png, .jpg o .webp.")
    w = max(320, min(3840, int(width)))
    h = max(320, min(3840, int(height)))

    if background_path:
        bg_file = workspace.resolve_safe_path(background_path)
        if not bg_file.is_file():
            raise WorkspaceError(f"No existe la imagen de fondo: {background_path}")
        with Image.open(bg_file) as src:
            canvas = ImageOps.fit(src.convert("RGB"), (w, h), method=Image.Resampling.LANCZOS).convert("RGBA")
    else:
        base_r, base_g, base_b, _ = _hex_rgba(bg_color)
        acc_r, acc_g, acc_b, _ = _hex_rgba(accent_color)
        canvas = Image.new("RGBA", (w, h), (base_r, base_g, base_b, 255))
        draw_bg = ImageDraw.Draw(canvas)
        for y in range(0, h, 4):
            t = y / max(1, h - 1)
            r = int(base_r * (1 - t * 0.25) + acc_r * (t * 0.18))
            g = int(base_g * (1 - t * 0.25) + acc_g * (t * 0.18))
            b = int(base_b * (1 - t * 0.25) + acc_b * (t * 0.18))
            draw_bg.rectangle([(0, y), (w, min(h, y + 4))], fill=(r, g, b, 255))

    if grade == "cinematic":
        rgb = ImageEnhance.Contrast(canvas.convert("RGB")).enhance(1.12)
        rgb = ImageEnhance.Color(rgb).enhance(1.08)
        canvas = rgb.convert("RGBA")

    # Degradado oscuro inferior para contraste WCAG AA garantizado en tipografía
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    band_top = int(h * 0.42)
    for y in range(band_top, h, 2):
        frac = (y - band_top) / max(1, h - band_top)
        alpha = int(min(225, 225 * (frac ** 1.35)))
        ov_draw.rectangle([(0, y), (w, min(h, y + 2))], fill=(5, 11, 22, alpha))
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)
    pad = max(36, int(w * 0.055))
    acc_rgba = _hex_rgba(accent_color, 255)

    # Barra de acento superior izquierda
    draw.rounded_rectangle([(pad, pad), (pad + 76, pad + 8)], radius=4, fill=acc_rgba)

    if badge.strip():
        b_font = _load_font(max(16, int(h * 0.032)), bold=True)
        bbox = draw.textbbox((0, 0), badge.strip().upper(), font=b_font)
        bw = (bbox[2] - bbox[0]) + 28
        bh = (bbox[3] - bbox[1]) + 14
        by = pad + 22
        draw.rounded_rectangle([(pad, by), (pad + bw, by + bh)], radius=8, fill=_hex_rgba(accent_color, 45), outline=acc_rgba, width=2)
        draw.text((pad + 14, by + 6), badge.strip().upper(), fill=(240, 249, 255, 255), font=b_font)

    t_font = _load_font(max(28, int(h * 0.082)), bold=True)
    s_font = _load_font(max(18, int(h * 0.038)), bold=False)
    t_lines = _wrap_text(draw, title, t_font, w - pad * 2)[:3]
    s_lines = _wrap_text(draw, subtitle, s_font, w - pad * 2)[:2] if subtitle.strip() else []

    line_h_t = int(h * 0.095)
    line_h_s = int(h * 0.052)
    total_text_h = len(t_lines) * line_h_t + (len(s_lines) * line_h_s + 12 if s_lines else 0)
    cur_y = max(pad + 80, h - pad - total_text_h)

    for ln in t_lines:
        draw.text((pad + 2, cur_y + 3), ln, fill=(0, 0, 0, 175), font=t_font)
        draw.text((pad, cur_y), ln, fill=(248, 250, 252, 255), font=t_font)
        cur_y += line_h_t

    if s_lines:
        cur_y += 8
        for ln in s_lines:
            draw.text((pad, cur_y), ln, fill=(203, 213, 225, 255), font=s_font)
            cur_y += line_h_s

    out_file.parent.mkdir(parents=True, exist_ok=True)
    save_img = canvas.convert("RGB") if out_file.suffix.lower() in {".jpg", ".jpeg"} else canvas
    save_img.save(str(out_file))
    return {
        "ok": True,
        "path": workspace.to_rel_posix(out_file),
        "width": w,
        "height": h,
        "bytes": out_file.stat().st_size,
    }


def _read_wav_rms_envelope(wav_path: Path, fps: int, max_seconds: float = 30.0) -> tuple[list[float], float]:
    """Calcula la envolvente RMS normalizada (0.0..1.0) por fotograma usando stdlib `wave` + `struct`."""
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        duration = min(max_seconds, n_frames / max(1, framerate))
        frames_needed = int(duration * framerate)
        raw = wf.readframes(frames_needed)

    if sampwidth != 2 or not raw:
        total_out = max(1, int(round(duration * fps)))
        return [0.0] * total_out, duration

    samples = struct.unpack(f"<{len(raw) // 2}h", raw)
    mono = samples[::n_channels] if n_channels > 1 else samples
    step = max(1, int(framerate / max(1, fps)))
    env: list[float] = []
    peak = 1.0
    for i in range(0, len(mono), step):
        seg = mono[i : i + step]
        if not seg:
            continue
        rms = math.sqrt(sum(s * s for s in seg) / len(seg))
        env.append(rms)
        if rms > peak:
            peak = rms
    norm = [min(1.0, v / max(1.0, peak)) for v in env]
    return norm or [0.0], duration


def _encode_frames(
    frames: list[Image.Image],
    out_file: Path,
    *,
    fps: int,
    audio_path: Path | None = None,
    runtime: Path | None = None,
) -> tuple[Path, str]:
    """Codifica los fotogramas a MP4 H.264 (+ audio si existe) usando ffmpeg, o a WebP/GIF animado con Pillow."""
    out_file.parent.mkdir(parents=True, exist_ok=True)
    suffix = out_file.suffix.lower()
    ffmpeg_bin = find_ffmpeg(runtime)

    if suffix == ".mp4" and ffmpeg_bin:
        with tempfile.TemporaryDirectory(prefix="aura_vid_") as tmp:
            tdir = Path(tmp)
            for idx, fr in enumerate(frames):
                fr.convert("RGB").save(tdir / f"frame_{idx:05d}.png")
            cmd = [ffmpeg_bin, "-y", "-framerate", str(fps), "-i", str(tdir / "frame_%05d.png")]
            if audio_path and audio_path.is_file():
                cmd.extend(["-i", str(audio_path), "-c:a", "aac", "-shortest"])
            cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_file)])
            subprocess.run(cmd, check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return out_file, "ffmpeg_mp4"

    # Fallback 100 % offline sin ffmpeg: WebP animado o GIF con Pillow
    target = out_file if suffix in {".webp", ".gif"} else out_file.with_suffix(".webp")
    dur_ms = max(20, int(round(1000 / max(1, fps))))
    rgb_frames = [fr.convert("RGB") for fr in frames]
    rgb_frames[0].save(
        str(target),
        save_all=True,
        append_images=rgb_frames[1:],
        duration=dur_ms,
        loop=0,
    )
    return target, f"pillow_{target.suffix.lstrip('.')}"


def render_cinematic_video(
    workspace: SafeWorkspace,
    image_paths: list[str],
    output_path: str,
    *,
    width: int = 640,
    height: int = 360,
    fps: int = 12,
    seconds_per_slide: float = 2.0,
    captions: list[str] | None = None,
    audio_path: str | None = None,
    runtime: Path | None = None,
) -> dict[str, Any]:
    """Renderiza un video animado 2.5D estilo cine (zoom Ken Burns + subtítulos) a partir de imágenes locales."""
    if not image_paths:
        raise WorkspaceError("Proporciona al menos una imagen en `image_paths`.")
    out_file = workspace.resolve_safe_path(output_path, allow_write=True)
    w, h = max(256, min(1920, int(width))), max(256, min(1080, int(height)))
    fps = max(6, min(30, int(fps)))
    n_slide = max(4, int(round(max(0.5, float(seconds_per_slide)) * fps)))
    cap_font = _load_font(max(16, int(h * 0.055)), bold=True)

    frames: list[Image.Image] = []
    for s_idx, rel_img in enumerate(image_paths[:10]):
        img_file = workspace.resolve_safe_path(rel_img)
        if not img_file.is_file():
            raise WorkspaceError(f"Imagen no encontrada: {rel_img}")
        with Image.open(img_file) as raw_im:
            base = ImageOps.fit(raw_im.convert("RGB"), (int(w * 1.14), int(h * 1.14)), method=Image.Resampling.LANCZOS)
        bw, bh = base.size
        caption = captions[s_idx] if captions and s_idx < len(captions) else ""
        for f in range(n_slide):
            t = f / max(1, n_slide - 1)
            zoom = 1.0 + 0.10 * t
            cw, ch = int(w / zoom * 1.12), int(h / zoom * 1.12)
            cx = int((bw - cw) * (0.35 + 0.30 * t))
            cy = int((bh - ch) * 0.5)
            crop = base.crop((max(0, cx), max(0, cy), min(bw, cx + cw), min(bh, cy + ch)))
            frame = crop.resize((w, h), Image.Resampling.LANCZOS).convert("RGBA")
            if caption.strip():
                ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                od = ImageDraw.Draw(ov)
                od.rectangle([(0, h - int(h * 0.18)), (w, h)], fill=(6, 12, 24, 185))
                od.text((20, h - int(h * 0.14)), caption.strip()[:90], fill=(248, 250, 252, 255), font=cap_font)
                frame = Image.alpha_composite(frame, ov)
            frames.append(frame)

    aud = workspace.resolve_safe_path(audio_path) if audio_path else None
    saved, encoder = _encode_frames(frames, out_file, fps=fps, audio_path=aud, runtime=runtime)
    return {
        "ok": True,
        "path": workspace.to_rel_posix(saved),
        "encoder": encoder,
        "frames": len(frames),
        "fps": fps,
        "width": w,
        "height": h,
        "bytes": saved.stat().st_size,
    }


def render_talking_avatar_video(
    workspace: SafeWorkspace,
    avatar_image_path: str,
    output_path: str,
    *,
    audio_wav_path: str | None = None,
    caption: str = "",
    width: int = 512,
    height: int = 512,
    fps: int = 12,
    duration_sec: float = 3.0,
    runtime: Path | None = None,
) -> dict[str, Any]:
    """Crea una animación local de avatar parlante en CPU: micro-movimiento natural + pulso reactivo a voz WAV + subtítulos."""
    img_file = workspace.resolve_safe_path(avatar_image_path)
    if not img_file.is_file():
        raise WorkspaceError(f"Imagen de avatar no encontrada: {avatar_image_path}")
    out_file = workspace.resolve_safe_path(output_path, allow_write=True)
    w, h = max(256, min(1080, int(width))), max(256, min(1080, int(height)))
    fps = max(6, min(24, int(fps)))

    aud_file: Path | None = None
    if audio_wav_path:
        aud_file = workspace.resolve_safe_path(audio_wav_path)
        if not aud_file.is_file():
            raise WorkspaceError(f"Audio WAV no encontrado: {audio_wav_path}")
        envelope, dur = _read_wav_rms_envelope(aud_file, fps)
    else:
        n = max(6, int(round(max(1.0, float(duration_sec)) * fps)))
        envelope = [0.25 + 0.65 * abs(math.sin(i * 0.55)) for i in range(n)]
        dur = n / fps

    with Image.open(img_file) as raw_im:
        base = ImageOps.fit(raw_im.convert("RGB"), (int(w * 1.08), int(h * 1.08)), method=Image.Resampling.LANCZOS)
    bw, bh = base.size
    font = _load_font(max(15, int(h * 0.045)), bold=True)

    frames: list[Image.Image] = []
    for idx, amp in enumerate(envelope):
        t = idx / max(1, fps)
        # Micro-movimiento natural de respiración y habla
        dx = int(round(math.sin(t * 2.1) * 4.0))
        dy = int(round(math.sin(t * 3.4) * 3.0 - amp * 3.0))
        left = max(0, min(bw - w, (bw - w) // 2 + dx))
        top = max(0, min(bh - h, (bh - h) // 2 + dy))
        frame = base.crop((left, top, left + w, top + h)).convert("RGBA")

        # Indicador visual de voz / ecualizador sincronizado con RMS + subtítulo
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        bar_area_y = h - 42 if caption.strip() else h - 22
        bars = 14
        bar_w = max(4, (w - 80) // (bars * 2))
        start_x = (w - bars * bar_w * 2) // 2
        for b in range(bars):
            wave_f = 0.35 + 0.65 * abs(math.sin(t * 6.0 + b * 0.65))
            bh_px = max(4, int(24 * amp * wave_f))
            bx = start_x + b * bar_w * 2
            od.rounded_rectangle([(bx, bar_area_y - bh_px), (bx + bar_w, bar_area_y)], radius=2, fill=(56, 189, 248, 220))
        if caption.strip():
            od.rectangle([(0, h - 36), (w, h)], fill=(7, 14, 28, 195))
            od.text((16, h - 29), caption.strip()[:72], fill=(248, 250, 252, 255), font=font)
        frame = Image.alpha_composite(frame, ov)
        frames.append(frame)

    saved, encoder = _encode_frames(frames, out_file, fps=fps, audio_path=aud_file, runtime=runtime)
    return {
        "ok": True,
        "path": workspace.to_rel_posix(saved),
        "encoder": encoder,
        "frames": len(frames),
        "duration_sec": round(dur, 2),
        "fps": fps,
        "bytes": saved.stat().st_size,
    }


def generate_blender_3d_video_script(
    workspace: SafeWorkspace,
    output_script_path: str,
    *,
    video_output_path: str = "renders/video_3d.mp4",
    scene_title: str = "Escena 3D Realista AURA",
    frames: int = 96,
    fps: int = 24,
    width: int = 1280,
    height: int = 720,
    engine: str = "BLENDER_EEVEE_NEXT",
) -> dict[str, Any]:
    """Genera un script Python `bpy` completo para renderizar un video 3D realista MP4 (H.264) en Blender 5.x."""
    script_file = workspace.resolve_safe_path(output_script_path, allow_write=True)
    out_vid = workspace.resolve_safe_path(video_output_path, allow_write=True)
    script_code = f'''"""Script Blender 5.x (bpy) generado por AURA para renderizar video 3D realista MP4 (H.264).
Ejecutar headless: blender -b -P "{script_file.name}"
"""
import math
import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "{engine}"
scene.render.resolution_x = {int(width)}
scene.render.resolution_y = {int(height)}
scene.render.fps = {int(fps)}
scene.frame_start = 1
scene.frame_end = {max(24, int(frames))}

# Salida directa a video MP4 H.264 con FFmpeg interno de Blender 5
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
scene.render.filepath = r"{str(out_vid)}"

# Estudio PBR: suelo ciclorama + sujeto 3D con materiales Principled BSDF
bpy.ops.mesh.primitive_plane_add(size=18, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "Ciclorama"
m_floor = bpy.data.materials.new("MatSuelo")
m_floor.use_nodes = True
bsdf_f = m_floor.node_tree.nodes.get("Principled BSDF")
bsdf_f.inputs["Base Color"].default_value = (0.04, 0.06, 0.10, 1.0)
bsdf_f.inputs["Roughness"].default_value = 0.25
floor.data.materials.append(m_floor)

bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1.0, location=(0, 0, 1.15))
hero = bpy.context.active_object
hero.name = "SujetoPrincipal"
bpy.ops.object.shade_smooth()
m_hero = bpy.data.materials.new("MatMetalStudio")
m_hero.use_nodes = True
bsdf_h = m_hero.node_tree.nodes.get("Principled BSDF")
bsdf_h.inputs["Base Color"].default_value = (0.14, 0.62, 0.95, 1.0)
bsdf_h.inputs["Metallic"].default_value = 0.85
bsdf_h.inputs["Roughness"].default_value = 0.18
hero.data.materials.append(m_hero)

# Iluminación de estudio 3 puntos (Key + Rim + Fill)
for lname, energy, loc, col in [
    ("LuzClave", 420.0, (4.2, -3.8, 4.8), (1.0, 0.96, 0.92)),
    ("LuzRelleno", 160.0, (-4.5, -2.5, 3.0), (0.65, 0.84, 1.0)),
    ("LuzContraluz", 280.0, (0.0, 4.6, 3.6), (0.35, 0.82, 1.0)),
]:
    ld = bpy.data.lights.new(name=lname, type="AREA")
    ld.energy = energy
    ld.size = 2.6
    ld.color = col
    lo = bpy.data.objects.new(name=lname, object_data=ld)
    bpy.context.collection.objects.link(lo)
    lo.location = loc
    tr = lo.constraints.new(type="TRACK_TO")
    tr.target = hero
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"

# Cámara cinematográfica con órbita suave
cam_d = bpy.data.cameras.new("CamaraCine")
cam_d.lens = 50.0
cam_o = bpy.data.objects.new("CamaraCine", cam_d)
bpy.context.collection.objects.link(cam_o)
scene.camera = cam_o
tr_c = cam_o.constraints.new(type="TRACK_TO")
tr_c.target = hero
tr_c.track_axis = "TRACK_NEGATIVE_Z"
tr_c.up_axis = "UP_Y"

total_f = scene.frame_end
for f in range(1, total_f + 1, max(1, total_f // 8)):
    ang = (f - 1) / float(total_f) * math.tau * 0.5
    cam_o.location = (math.sin(ang) * 5.2, -math.cos(ang) * 5.2, 2.2 + 0.35 * math.sin(ang))
    cam_o.keyframe_insert(data_path="location", frame=f)

bpy.ops.render.render(animation=True)
print("RENDER_VIDEO_3D_OK:", scene.render.filepath)
'''
    script_file.parent.mkdir(parents=True, exist_ok=True)
    script_file.write_text(script_code, encoding="utf-8")
    return {
        "ok": True,
        "script": workspace.to_rel_posix(script_file),
        "video_target": workspace.to_rel_posix(out_vid),
        "frames": max(24, int(frames)),
        "fps": int(fps),
        "title": scene_title,
    }
