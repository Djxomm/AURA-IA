"""Puente oficial local OpenAI-compatible para ejecutar Codex CLI y OpenCode
usando exclusivamente los modelos locales de AURA IA (ANGEL, MATEO, Zamara V8.2, Lumen)
mediante el servidor local `llama-server.exe`, sin claves en la nube ni costos de API."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .chat_controls import model_label


def _strip_toml_section(text: str, section_header: str) -> str:
    """Elimina una sección TOML `[header]` completa preservando las demás secciones del usuario."""
    lines = text.splitlines()
    out: list[str] = []
    skipping = False
    target = section_header.strip()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped == target:
                skipping = True
                continue
            skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out).strip()


def sync_codex_aura_profile(
    base_url: str,
    model_id: str,
    *,
    codex_home: Path | None = None,
) -> Path:
    """Actualiza `[model_providers.aura]` y `[profiles.aura]` en `~/.codex/config.toml`
    sin borrar configuraciones previas del usuario."""
    home = Path(codex_home) if codex_home is not None else (Path.home() / ".codex")
    home.mkdir(parents=True, exist_ok=True)
    cfg_path = home / "config.toml"
    existing = cfg_path.read_text(encoding="utf-8") if cfg_path.is_file() else ""
    cleaned = _strip_toml_section(existing, "[model_providers.aura]")
    cleaned = _strip_toml_section(cleaned, "[profiles.aura]")

    safe_url = str(base_url).rstrip("/")
    safe_model = re.sub(r'["\r\n]', "", str(model_id or "aura-local")).strip() or "aura-local"

    block = (
        "[model_providers.aura]\n"
        'name = "AURA IA Local"\n'
        f'base_url = "{safe_url}"\n'
        'env_key = "AURA_LOCAL_API_KEY"\n'
        'wire_api = "chat"\n\n'
        "[profiles.aura]\n"
        'model_provider = "aura"\n'
        f'model = "{safe_model}"\n'
    )
    final_text = (cleaned + "\n\n" + block) if cleaned else block
    cfg_path.write_text(final_text.rstrip() + "\n", encoding="utf-8")
    return cfg_path


def sync_opencode_aura_config(
    workspace_path: str | Path,
    base_url: str,
    model_id: str,
    model_display: str = "",
) -> Path:
    """Escribe o actualiza el bloque `provider.aura` en `opencode.json` para usar modelos AURA locales."""
    ws = Path(workspace_path).resolve()
    cfg_path = ws / "opencode.json"
    data: dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            data = {}
    providers = data.get("provider")
    if not isinstance(providers, dict):
        providers = {}
    safe_url = str(base_url).rstrip("/")
    safe_model = str(model_id or "aura-local").strip() or "aura-local"
    display = model_display or safe_model
    providers["aura"] = {
        "npm": "@ai-sdk/openai-compatible",
        "name": "AURA IA Local",
        "options": {
            "baseURL": safe_url,
            "apiKey": "aura-local",
        },
        "models": {
            safe_model: {
                "name": display,
            }
        },
    }
    data["provider"] = providers
    data["model"] = f"aura/{safe_model}"
    cfg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return cfg_path


def ensure_aura_openai_endpoint(client: Any, settings: Any) -> dict[str, Any]:
    """Asegura que `llama-server.exe` de AURA IA esté escuchando en localhost y devuelve su `/v1`."""
    from .acceleration import backend
    from .model_library import context_profile, find_paired_multimodal_files, limits, model_info

    model_path = Path(client.model).resolve()
    if not model_path.is_file():
        raise ValueError(f"No se encontró el modelo GGUF activo de AURA: {model_path}")

    info = model_info(model_path)
    arch = str(info.get("general.architecture") or "")
    effective_settings = limits(model_path, settings)
    layers = info.get(f"{arch or 'qwen2'}.block_count", 0)
    size = model_path.stat().st_size
    engine, gpu_args, _ = backend(client.runtime, client.data, getattr(client, "acceleration", "auto"), size, layers)
    profile = context_profile(model_path)
    effective_ctx = max(int(effective_settings.num_ctx), int(profile["recommended"]))
    paired = find_paired_multimodal_files(model_path) if arch == "gemma4" else {"mmproj": None, "mtp": None}

    port = client._ensure_server(
        engine,
        effective_ctx,
        effective_settings,
        gpu_args,
        arch=arch,
        mmproj=paired.get("mmproj"),
        mtp=paired.get("mtp"),
    )
    model_id = model_path.stem
    return {
        "port": int(port),
        "base_url": f"http://127.0.0.1:{int(port)}/v1",
        "model_id": model_id,
        "model_label": model_label(model_path),
        "model_path": str(model_path),
        "arch": arch,
    }
