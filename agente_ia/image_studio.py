"""Estudio local 100 % offline de generación y edición fotorrealista de imágenes para AURA.
Combina:
1. stable-diffusion.cpp (sd-cli.exe) con modelos locales cuantizados (txt2img e img2img).
2. Editor determinista instantáneo con Pillow (recorte, tamaño, brillo, contraste, color,
   nitidez, desenfoque, rotación, volteo, bordes, texto/marca de agua y conversión de formato).
Todas las rutas permanecen estrictamente dentro del workspace seguro del proyecto."""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .workspace import SafeWorkspace, WorkspaceError


IMAGE_OUTPUT_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MIN_DIM = 256
MAX_DIM = 1024


def _clamp_dim(value: Any, default: int = 512) -> int:
    try:
        v = int(value or default)
    except (TypeError, ValueError):
        v = default
    v = max(MIN_DIM, min(MAX_DIM, v))
    return (v // 64) * 64


def locate_image_engine(runtime: Path | None) -> tuple[Path | None, Path | None]:
    """Busca sd-cli.exe (o sd.exe) y un modelo GGUF/safetensors dentro de runtime/imagen."""
    roots: list[Path] = []
    if runtime is not None:
        roots.append(Path(runtime).resolve() / "imagen")
    default_rt = Path(__file__).resolve().parent.parent / "runtime" / "imagen"
    if default_rt not in roots:
        roots.append(default_rt)

    for root in roots:
        if not root.is_dir():
            continue
        exe = next((p for p in (root / "motor").rglob("sd-cli.exe")), None) if (root / "motor").is_dir() else None
        if exe is None and (root / "motor").is_dir():
            exe = next((p for p in (root / "motor").rglob("sd.exe")), None)
        model = None
        if (root / "modelos").is_dir():
            ggufs = sorted((root / "modelos").glob("*.gguf"), key=lambda p: p.stat().st_size)
            sts = sorted((root / "modelos").glob("*.safetensors"), key=lambda p: p.stat().st_size)
            model = (ggufs[0] if ggufs else (sts[0] if sts else None))
        if exe is not None and model is not None:
            return exe, model
    return None, None


def _run_sd_cli(
    exe: Path,
    args: list[str],
    *,
    timeout: int = 300,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[int, str, float]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    env = os.environ.copy()
    env["PATH"] = str(exe.parent) + os.pathsep + env.get("PATH", "")
    start = time.monotonic()
    proc = subprocess.Popen(
        [str(exe), *args],
        cwd=str(exe.parent),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    chunks: list[bytes] = []

    def _drain() -> None:
        assert proc.stdout is not None
        while data := proc.stdout.read(4096):
            chunks.append(data)

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()
    timed_out = False
    cancelled = False
    try:
        while proc.poll() is None:
            if cancel_check and cancel_check():
                cancelled = True
                proc.kill()
                break
            if time.monotonic() - start > timeout:
                timed_out = True
                proc.kill()
                break
            time.sleep(0.15)
    finally:
        code = proc.wait()
        reader.join(timeout=2.0)
        if proc.stdout is not None:
            proc.stdout.close()

    output = b"".join(chunks).decode("utf-8", "replace").strip()
    if cancelled:
        raise WorkspaceError("Generación de imagen detenida por el usuario.")
    if timed_out:
        raise WorkspaceError(f"La generación de imagen superó el tiempo límite de {timeout} s.")
    return code, output, round(time.monotonic() - start, 2)


def _save_pillow_image(img, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        img.convert("RGB").save(str(target), format="JPEG", quality=92)
    elif suffix == ".webp":
        img.save(str(target), format="WEBP", quality=90)
    else:
        img.save(str(target), format="PNG")


def apply_pillow_operations(input_file: Path, output_file: Path, operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Aplica edición determinista instantánea con Pillow (tamaño, recorte, color, luz, texto, filtros)."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

    with Image.open(str(input_file)) as src:
        img = src.convert("RGBA")
        applied: list[str] = []
        for raw_op in operations:
            if not isinstance(raw_op, dict):
                continue
            op = str(raw_op.get("op") or "").strip().lower()
            if op == "resize":
                w = max(16, min(4096, int(raw_op.get("width") or img.width)))
                h = max(16, min(4096, int(raw_op.get("height") or img.height)))
                img = img.resize((w, h), Image.Resampling.LANCZOS)
                applied.append(f"resize({w}x{h})")
            elif op == "crop":
                box = raw_op.get("box")
                if isinstance(box, (list, tuple)) and len(box) == 4:
                    x1, y1, x2, y2 = [int(v) for v in box]
                    x1 = max(0, min(img.width - 1, x1))
                    y1 = max(0, min(img.height - 1, y1))
                    x2 = max(x1 + 1, min(img.width, x2))
                    y2 = max(y1 + 1, min(img.height, y2))
                    img = img.crop((x1, y1, x2, y2))
                    applied.append(f"crop({x1},{y1},{x2},{y2})")
            elif op == "brightness":
                factor = max(0.1, min(3.0, float(raw_op.get("factor", 1.1))))
                img = ImageEnhance.Brightness(img).enhance(factor)
                applied.append(f"brightness({factor})")
            elif op == "contrast":
                factor = max(0.1, min(3.0, float(raw_op.get("factor", 1.15))))
                img = ImageEnhance.Contrast(img).enhance(factor)
                applied.append(f"contrast({factor})")
            elif op in {"color", "saturation"}:
                factor = max(0.0, min(3.0, float(raw_op.get("factor", 1.15))))
                img = ImageEnhance.Color(img).enhance(factor)
                applied.append(f"color({factor})")
            elif op == "sharpness":
                factor = max(0.0, min(4.0, float(raw_op.get("factor", 1.3))))
                img = ImageEnhance.Sharpness(img).enhance(factor)
                applied.append(f"sharpness({factor})")
            elif op == "blur":
                radius = max(0.1, min(25.0, float(raw_op.get("radius", 2.0))))
                img = img.filter(ImageFilter.GaussianBlur(radius=radius))
                applied.append(f"blur({radius})")
            elif op == "grayscale":
                img = ImageOps.grayscale(img).convert("RGBA")
                applied.append("grayscale")
            elif op == "autocontrast":
                rgb = ImageOps.autocontrast(img.convert("RGB"))
                img = rgb.convert("RGBA")
                applied.append("autocontrast")
            elif op == "rotate":
                deg = float(raw_op.get("degrees", 90))
                img = img.rotate(deg, expand=True)
                applied.append(f"rotate({deg})")
            elif op == "flip_horizontal":
                img = ImageOps.mirror(img)
                applied.append("flip_horizontal")
            elif op == "flip_vertical":
                img = ImageOps.flip(img)
                applied.append("flip_vertical")
            elif op == "border":
                bw = max(1, min(128, int(raw_op.get("width", 8))))
                color = str(raw_op.get("color") or "#0f172a")
                img = ImageOps.expand(img.convert("RGB"), border=bw, fill=color).convert("RGBA")
                applied.append(f"border({bw},{color})")
            elif op == "text":
                text_val = str(raw_op.get("text") or "").strip()
                if text_val:
                    draw = ImageDraw.Draw(img)
                    x = int(raw_op.get("x", 20))
                    y = int(raw_op.get("y", 20))
                    color = str(raw_op.get("color") or "#ffffff")
                    bg = str(raw_op.get("bg") or "")
                    if bg:
                        bbox = draw.textbbox((x, y), text_val)
                        pad = 6
                        draw.rectangle([bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad], fill=bg)
                    draw.text((x, y), text_val, fill=color)
                    applied.append("text")
            else:
                raise WorkspaceError(f"Operación de imagen no soportada: '{op}'.")

        _save_pillow_image(img, output_file)
        return {"width": img.width, "height": img.height, "applied": applied}


def generate_image(
    workspace: SafeWorkspace,
    runtime: Path | None,
    prompt: str,
    output_path: str,
    *,
    negative_prompt: str = "blurry, lowres, watermark, deformed, extra limbs, ugly",
    width: int = 512,
    height: int = 512,
    steps: int = 4,
    cfg_scale: float = 1.0,
    seed: int = -1,
    threads: int = 4,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Genera una imagen fotorrealista 100 % offline con stable-diffusion.cpp dentro del workspace."""
    clean_prompt = str(prompt or "").strip()
    if not clean_prompt:
        raise WorkspaceError("El parámetro `prompt` no puede estar vacío.")
    target = workspace.resolve_safe_path(str(output_path or "").strip(), allow_write=True)
    if target.suffix.lower() not in IMAGE_OUTPUT_SUFFIXES:
        raise WorkspaceError("Usa una extensión de imagen válida (.png, .jpg, .jpeg o .webp).")

    exe, model = locate_image_engine(runtime)
    if exe is None or model is None:
        raise WorkspaceError(
            "El motor offline de imágenes (runtime/imagen/motor/sd-cli.exe y modelo local) no está instalado."
        )

    w = _clamp_dim(width, 512)
    h = _clamp_dim(height, 512)
    st = max(1, min(20, int(steps or 4)))
    cfg = max(0.0, min(12.0, float(cfg_scale if cfg_scale is not None else 1.0)))
    thr = max(1, min(16, int(threads or 4)))

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_png = target if target.suffix.lower() == ".png" else target.with_suffix(".aura_tmp.png")
    cli_args = [
        "-m", str(model),
        "-p", clean_prompt,
        "-n", str(negative_prompt or ""),
        "-W", str(w),
        "-H", str(h),
        "--steps", str(st),
        "--cfg-scale", str(cfg),
        "--sampling-method", "lcm",
        "-t", str(thr),
        "-o", str(tmp_png),
    ]
    if seed is not None and int(seed) >= 0:
        cli_args += ["-s", str(int(seed))]

    code, out, elapsed = _run_sd_cli(exe, cli_args, timeout=300, cancel_check=cancel_check)
    if code != 0 or not tmp_png.is_file():
        tmp_png.unlink(missing_ok=True)
        raise WorkspaceError(f"Error al generar imagen (código {code}): {out[-600:]}")

    if tmp_png != target:
        from PIL import Image
        with Image.open(str(tmp_png)) as im:
            _save_pillow_image(im, target)
        tmp_png.unlink(missing_ok=True)

    return {
        "ok": True,
        "path": workspace.to_rel_posix(target),
        "width": w,
        "height": h,
        "steps": st,
        "bytes": target.stat().st_size,
        "seconds": elapsed,
        "engine": f"stable-diffusion.cpp offline ({model.name})",
    }


def edit_image(
    workspace: SafeWorkspace,
    runtime: Path | None,
    input_path: str,
    output_path: str,
    *,
    prompt: str = "",
    negative_prompt: str = "blurry, lowres, watermark, deformed, artifacts",
    strength: float = 0.55,
    steps: int = 4,
    cfg_scale: float = 1.0,
    operations: list[dict[str, Any]] | None = None,
    threads: int = 4,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Edita una imagen local 100 % offline con img2img (difusión local) y/o operaciones exactas Pillow."""
    src = workspace.resolve_safe_path(str(input_path or "").strip())
    if not src.is_file():
        raise WorkspaceError(f"No existe la imagen de entrada: {input_path}")
    dst = workspace.resolve_safe_path(str(output_path or "").strip(), allow_write=True)
    if dst.suffix.lower() not in IMAGE_OUTPUT_SUFFIXES:
        raise WorkspaceError("Usa una extensión de imagen válida (.png, .jpg, .jpeg o .webp).")

    clean_prompt = str(prompt or "").strip()
    ops = operations if isinstance(operations, list) else []
    if not clean_prompt and not ops:
        raise WorkspaceError("Indica `prompt` (edición semántica img2img) y/o `operations` (edición exacta Pillow).")

    started = time.monotonic()
    current_file = src
    temp_dir: Path | None = None
    engines_used: list[str] = []
    applied_ops: list[str] = []

    try:
        if clean_prompt:
            exe, model = locate_image_engine(runtime)
            if exe is None or model is None:
                raise WorkspaceError(
                    "Para edición semántica con `prompt` se requiere el motor offline en runtime/imagen/."
                )
            from PIL import Image
            with Image.open(str(src)) as im:
                w = _clamp_dim(im.width, 512)
                h = _clamp_dim(im.height, 512)
            temp_dir = Path(tempfile.mkdtemp(prefix="aura_img_edit_"))
            mid_png = temp_dir / "img2img.png"
            st = max(2, min(20, int(steps or 6)))
            cfg = max(0.0, min(12.0, float(cfg_scale if cfg_scale is not None else 1.5)))
            strg = max(0.15, min(0.95, float(strength if strength is not None else 0.55)))
            cli_args = [
                "-m", str(model),
                "-i", str(src),
                "-p", clean_prompt,
                "-n", str(negative_prompt or ""),
                "--strength", str(strg),
                "-W", str(w),
                "-H", str(h),
                "--steps", str(st),
                "--cfg-scale", str(cfg),
                "--sampling-method", "lcm",
                "-t", str(max(1, min(16, int(threads or 4)))),
                "-o", str(mid_png),
            ]
            code, out, _ = _run_sd_cli(exe, cli_args, timeout=300, cancel_check=cancel_check)
            if code != 0 or not mid_png.is_file():
                raise WorkspaceError(f"Error en edición img2img (código {code}): {out[-600:]}")
            current_file = mid_png
            engines_used.append(f"stable-diffusion.cpp img2img ({model.name}, strength={strg})")

        if ops:
            info = apply_pillow_operations(current_file, dst, ops)
            applied_ops = info["applied"]
            w_out, h_out = info["width"], info["height"]
            engines_used.append("Pillow offline")
        else:
            from PIL import Image
            with Image.open(str(current_file)) as im:
                _save_pillow_image(im, dst)
                w_out, h_out = im.width, im.height
    finally:
        if temp_dir is not None:
            for item in temp_dir.glob("*"):
                item.unlink(missing_ok=True)
            temp_dir.rmdir()

    return {
        "ok": True,
        "input": workspace.to_rel_posix(src),
        "path": workspace.to_rel_posix(dst),
        "width": w_out,
        "height": h_out,
        "bytes": dst.stat().st_size,
        "applied_operations": applied_ops,
        "seconds": round(time.monotonic() - started, 2),
        "engine": " + ".join(engines_used),
    }
