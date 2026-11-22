"""Configuración, perfiles de hardware y detección local para CódigoLocal."""

from __future__ import annotations

import ctypes
import os
import platform
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

ProviderName = Literal["ollama", "llamacpp", "lmstudio"]
HardwareProfileName = Literal["legacy_i5_1gb", "balanced_cpu", "gpu_standard"]
ToolModeName = Literal["auto", "native", "xml"]


HARDWARE_PROFILES: dict[str, dict[str, Any]] = {
    "legacy_i5_1gb": {
        "id": "legacy_i5_1gb",
        "label": "CPU compatible · i5 y 16 GB RAM",
        "short_label": "CPU · 16 GB",
        "description": (
            "Minimiza KV-cache y lotes (batch 128) para CPUs sin AVX/AVX2 "
            "y modo CPU compatible; aceleración gráfica opcional."
        ),
        "num_ctx": 4096,
        "num_batch": 128,
        "num_thread": 2,
        "num_gpu": 0,
        "max_predict_tokens": 512,
        "max_history_messages": 6,
        "max_read_lines": 80,
        "max_tool_output_chars": 1800,
        "max_steps": 6,
        "compact_prompt": True,
        "default_model": "qwen2.5-coder:1.5b",
    },
    "balanced_cpu": {
        "id": "balanced_cpu",
        "label": "CPU Moderno (8-16 GB RAM)",
        "short_label": "CPU 8-16 GB",
        "description": (
            "Contexto medio de 4096 tokens en CPU pura para procesadores con AVX2 "
            "y 8-16 GB de memoria RAM."
        ),
        "num_ctx": 4096,
        "num_batch": 256,
        "num_thread": 4,
        "num_gpu": 0,
        "max_predict_tokens": 1024,
        "max_history_messages": 12,
        "max_read_lines": 180,
        "max_tool_output_chars": 5000,
        "max_steps": 10,
        "compact_prompt": False,
        "default_model": "qwen2.5-coder:3b",
    },
    "gpu_standard": {
        "id": "gpu_standard",
        "label": "GPU Dedicada (4 GB+ VRAM)",
        "short_label": "GPU 4 GB+",
        "description": (
            "Offload completo a GPU con contexto de 8192 tokens y lectura ampliada "
            "para tarjetas con 4 GB o más de VRAM."
        ),
        "num_ctx": 8192,
        "num_batch": 512,
        "num_thread": 4,
        "num_gpu": 99,
        "max_predict_tokens": 2048,
        "max_history_messages": 20,
        "max_read_lines": 250,
        "max_tool_output_chars": 10000,
        "max_steps": 12,
        "compact_prompt": False,
        "default_model": "qwen2.5-coder:7b",
    },
}


RECOMMENDED_MODELS: list[dict[str, Any]] = [
    {
        "id": "qwen2.5-coder:0.5b",
        "name": "Qwen 2.5 Coder 0.5B (Q4_K_M)",
        "gguf_hint": "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf",
        "size_mb": 398,
        "vram_fit": "1 GB completo",
        "speed_i5_gen1": "Por medir en tu PC",
        "ollama_cmd": "ollama pull qwen2.5-coder:0.5b",
        "best_for": "Cabe íntegro en NVIDIA 1 GB VRAM; ideal para ediciones rápidas y autocompletado.",
    },
    {
        "id": "qwen2.5-coder:1.5b",
        "name": "Qwen 2.5 Coder 1.5B (Q4_K_M / Q3_K_M)",
        "gguf_hint": "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        "size_mb": 986,
        "vram_fit": "Híbrido 1 GB + RAM",
        "speed_i5_gen1": "Por medir en tu PC",
        "ollama_cmd": "ollama pull qwen2.5-coder:1.5b",
        "best_for": "Mejor equilibrio calidad/velocidad en i5 1ra Gen con 6-10 capas en GPU 1 GB.",
    },
    {
        "id": "deepseek-coder:1.3b",
        "name": "DeepSeek Coder 1.3B (Q4_K_M)",
        "gguf_hint": "deepseek-coder-1.3b-instruct.Q4_K_M.gguf",
        "size_mb": 776,
        "vram_fit": "Híbrido 1 GB + RAM",
        "speed_i5_gen1": "Por medir en tu PC",
        "ollama_cmd": "ollama pull deepseek-coder:1.3b",
        "best_for": "Alternativa ligera probada para Python, JS y SQL con bajo consumo de RAM.",
    },
    {
        "id": "qwen2.5-coder:3b",
        "name": "Qwen 2.5 Coder 3B (Q4_K_M)",
        "gguf_hint": "qwen2.5-coder-3b-instruct-q4_k_m.gguf",
        "size_mb": 1930,
        "vram_fit": "Solo CPU (≥8 GB RAM)",
        "speed_i5_gen1": "Por medir en tu PC",
        "ollama_cmd": "ollama pull qwen2.5-coder:3b",
        "best_for": "Mayor precisión lógica cuando se prioriza calidad sobre velocidad en CPU.",
    },
]


def default_workspace_dir() -> str:
    """Devuelve la carpeta de trabajo inicial válida sin depender de rutas fijas."""
    pkg_parent = Path(__file__).resolve().parent.parent
    cwd = Path.cwd()
    if cwd.exists() and cwd.is_dir():
        return str(cwd)
    return str(pkg_parent)


class AppSettings(BaseModel):
    """Configuración persistente del agente de codificación local."""

    reduced_effects: bool = True
    intro_video: bool = True
    default_mode: Literal["chat", "code"] = "chat"
    local_model_id: str = "incluido"
    thinking_effort: Literal["rapido", "equilibrado", "profundo"] = "equilibrado"
    show_explanation: bool = True
    reasoning_supported: bool = False
    provider: ProviderName = "llamacpp"
    ollama_url: str = "http://127.0.0.1:11434"
    llamacpp_url: str = "http://127.0.0.1:8080/v1"
    lmstudio_url: str = "http://127.0.0.1:1234/v1"
    model: str = "qwen2.5-coder:1.5b"
    workspace_path: str = Field(default_factory=default_workspace_dir)
    hardware_profile: HardwareProfileName = "legacy_i5_1gb"
    temperature: float = Field(default=0.15, ge=0.0, le=1.5)
    num_ctx: int = Field(default=4096, ge=512, le=32768)
    num_batch: int = Field(default=128, ge=16, le=2048)
    num_thread: int = Field(default=2, ge=1, le=64)
    num_gpu: int = Field(default=0, ge=0, le=999)
    max_predict_tokens: int = Field(default=512, ge=0, le=32768)
    max_history_messages: int = Field(default=6, ge=2, le=60)
    max_read_lines: int = Field(default=80, ge=20, le=1000)
    max_tool_output_chars: int = Field(default=1800, ge=400, le=30000)
    max_steps: int = Field(default=6, ge=1, le=25)
    compact_prompt: bool = True
    tool_mode: ToolModeName = "auto"
    autonomous_mode: bool = False


def apply_hardware_profile(
    settings: AppSettings,
    profile_name: HardwareProfileName,
    *,
    keep_model: bool = False,
) -> AppSettings:
    """Aplica un preset de hardware preservando URLs y carpeta de trabajo."""
    profile = HARDWARE_PROFILES[profile_name]
    updates: dict[str, Any] = {
        "hardware_profile": profile_name,
        "num_ctx": profile["num_ctx"],
        "num_batch": profile["num_batch"],
        "num_thread": profile["num_thread"],
        "num_gpu": profile["num_gpu"],
        "max_predict_tokens": profile["max_predict_tokens"],
        "max_history_messages": profile["max_history_messages"],
        "max_read_lines": profile["max_read_lines"],
        "max_tool_output_chars": profile["max_tool_output_chars"],
        "max_steps": profile["max_steps"],
        "compact_prompt": profile["compact_prompt"],
    }
    if not keep_model:
        updates["model"] = profile["default_model"]
    return settings.model_copy(update=updates)


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _get_windows_ram_gb() -> float | None:
    if os.name != "nt":
        return None
    try:
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return round(stat.ullTotalPhys / (1024 ** 3), 1)
    except Exception:
        return None
    return None


def _detect_cpu_simd_windows() -> dict[str, bool | None]:
    """Detecta soporte básico de instrucciones SIMD en Windows vía kernel32."""
    if os.name != "nt":
        return {"sse42": None, "avx": None, "avx2": None}
    try:
        fn = ctypes.windll.kernel32.IsProcessorFeaturePresent
        # Windows ProcessorFeature constants:
        # 38 = PF_SSE4_2_INSTRUCTIONS_AVAILABLE
        # 39 = PF_AVX_INSTRUCTIONS_AVAILABLE
        # 40 = PF_AVX2_INSTRUCTIONS_AVAILABLE
        return {
            "sse42": bool(fn(38)),
            "avx": bool(fn(39)),
            "avx2": bool(fn(40)),
        }
    except Exception:
        return {"sse42": None, "avx": None, "avx2": None}


def detect_local_hardware() -> dict[str, Any]:
    """Inspecciona hardware actual y entrega recomendaciones para i5 1ra Gen + 1 GB VRAM."""
    simd = _detect_cpu_simd_windows()
    ram_gb = _get_windows_ram_gb()
    avx_ok = simd["avx"]
    legacy_cpu_detected = avx_ok is False

    recommendations = [
        "Usa el perfil 'legacy_i5_1gb' (ctx=2048, batch=128, threads=2, gpu_layers=8).",
        "En Intel i5 1ra Gen (sin AVX/AVX2) prefiere KoboldCpp con '--noavx2 --noavx' o llama-server SSE4.2.",
        "Para GPU NVIDIA de 1 GB VRAM (~750 MB útiles en Windows): usa qwen2.5-coder:0.5b (cabe completo) o qwen2.5-coder:1.5b con 6-10 capas en GPU.",
        "Si tu GPU NVIDIA antigua no soporta CUDA 12/Vulkan en tu motor local, cambia Capas GPU (num_gpu) a 0 para CPU seguro.",
    ]

    return {
        "os": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "Desconocido",
        "logical_cores": os.cpu_count() or 2,
        "ram_gb": ram_gb,
        "simd": simd,
        "legacy_no_avx": legacy_cpu_detected,
        "recommended_profile": "legacy_i5_1gb",
        "recommendations": recommendations,
    }
