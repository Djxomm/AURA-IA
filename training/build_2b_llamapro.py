"""Receta pública experimental: expansión de bloques estilo LLaMA Pro (1.5B -> ~2.01B, 38 capas)
sobre Qwen2.5-Coder-1.5B-Instruct (Apache-2.0) con inicialización a cero en o_proj y down_proj.

- Clona 10 capas (+468M parámetros) en streaming shard-por-shard (< 600 MB RAM pico).
- Inicializa self_attn.o_proj.weight y mlp.down_proj.weight a 0 exacto en las capas nuevas para
  preservar la función identidad en el paso 0 antes de entrenar.
- No modifica el modelo base original ni incluye pesos en el repositorio.
"""

from __future__ import annotations

import argparse
import gc
import json
import shutil
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file

CLONE_AFTER_ORIG = {2, 5, 8, 11, 14, 17, 20, 23, 25, 27}
ZERO_SUFFIXES = ("self_attn.o_proj.weight", "mlp.down_proj.weight")
LAYERS_PER_SHARD = 5


def expand_qwen_llamapro(src: Path, dst: Path) -> dict:
    src_sf = src / "model.safetensors"
    if not src_sf.is_file():
        raise FileNotFoundError(f"No se encontró {src_sf}")
    dst.mkdir(parents=True, exist_ok=True)

    cfg = json.loads((src / "config.json").read_text(encoding="utf-8"))
    orig_layers = int(cfg["num_hidden_layers"])
    if orig_layers != 28:
        raise ValueError(f"Esta receta espera una base Qwen2.5 1.5B de 28 capas (encontradas: {orig_layers}).")

    layer_plan: list[tuple[int, int, bool]] = []
    new_idx = 0
    for orig_idx in range(orig_layers):
        layer_plan.append((new_idx, orig_idx, False))
        new_idx += 1
        if orig_idx in CLONE_AFTER_ORIG:
            layer_plan.append((new_idx, orig_idx, True))
            new_idx += 1

    total_layers = len(layer_plan)
    expanded_indices = [n for n, _, exp in layer_plan if exp]
    groups: list[list[tuple[str, object]]] = [[("embed", None)]]
    for start in range(0, total_layers, LAYERS_PER_SHARD):
        chunk = [("layer", item) for item in layer_plan[start : start + LAYERS_PER_SHARD]]
        if start + LAYERS_PER_SHARD >= total_layers:
            chunk.append(("norm", None))
        groups.append(chunk)

    num_shards = len(groups)
    weight_map: dict[str, str] = {}
    total_bytes = 0
    total_params = 0
    expanded_params = 0

    with safe_open(str(src_sf), framework="pt", device="cpu") as f:
        layer_suffixes = sorted(
            k[len("model.layers.0.") :] for k in f.keys() if k.startswith("model.layers.0.")
        )
        for shard_num, entries in enumerate(groups, 1):
            shard_name = f"model-{shard_num:05d}-of-{num_shards:05d}.safetensors"
            tensors: dict[str, torch.Tensor] = {}
            for kind, payload in entries:
                if kind == "embed":
                    t = f.get_tensor("model.embed_tokens.weight").clone()
                    tensors["model.embed_tokens.weight"] = t
                    total_params += t.numel()
                    total_bytes += t.numel() * t.element_size()
                    weight_map["model.embed_tokens.weight"] = shard_name
                elif kind == "norm":
                    t = f.get_tensor("model.norm.weight").clone()
                    tensors["model.norm.weight"] = t
                    total_params += t.numel()
                    total_bytes += t.numel() * t.element_size()
                    weight_map["model.norm.weight"] = shard_name
                elif kind == "layer":
                    n_idx, o_idx, is_exp = payload
                    for suffix in layer_suffixes:
                        t = f.get_tensor(f"model.layers.{o_idx}.{suffix}")
                        t = torch.zeros_like(t) if (is_exp and suffix in ZERO_SUFFIXES) else t.clone()
                        dst_key = f"model.layers.{n_idx}.{suffix}"
                        tensors[dst_key] = t
                        total_params += t.numel()
                        total_bytes += t.numel() * t.element_size()
                        if is_exp:
                            expanded_params += t.numel()
                        weight_map[dst_key] = shard_name
            save_file(tensors, str(dst / shard_name), metadata={"format": "pt"})
            del tensors
            gc.collect()

    (dst / "model.safetensors.index.json").write_text(
        json.dumps({"metadata": {"total_size": total_bytes}, "weight_map": weight_map}, indent=2),
        encoding="utf-8",
    )
    cfg["num_hidden_layers"] = total_layers
    cfg["max_window_layers"] = total_layers
    (dst / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    for fname in ("LICENSE", "README.md", "generation_config.json", "merges.txt", "tokenizer.json", "tokenizer_config.json", "vocab.json"):
        if (src / fname).is_file():
            shutil.copy2(src / fname, dst / fname)

    manifest = {
        "method": "LLaMA Pro zero-initialized identity block expansion",
        "original_layers": orig_layers,
        "expanded_layers_added": len(expanded_indices),
        "total_layers": total_layers,
        "expanded_layer_indices": expanded_indices,
        "total_parameters": total_params,
        "expanded_parameters": expanded_params,
        "shards": num_shards,
    }
    (dst / "llamapro-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="Carpeta local de Qwen2.5-Coder-1.5B-Instruct.")
    parser.add_argument("--output", type=Path, required=True, help="Carpeta destino para la base expandida 2.01B.")
    args = parser.parse_args()
    print(json.dumps(expand_qwen_llamapro(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
