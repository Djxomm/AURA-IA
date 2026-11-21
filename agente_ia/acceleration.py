"""Optional Vulkan backend, isolated from the legacy CPU runtime."""
import functools
import json
import re
import subprocess
from pathlib import Path


@functools.lru_cache(maxsize=4)
def devices(runtime):
    engine = Path(runtime)/'motor-vulkan'/'llama-completion.exe'
    if not engine.is_file():
        return []
    try:
        result = subprocess.run([str(engine),'--list-devices'], cwd=engine.parent,
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=12,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:
            return []
        return [(m[0],m[1],int(m[2])) for m in re.findall(r'(Vulkan\d+): (.*?) \((\d+) MiB',result.stdout+result.stderr)]
    except (OSError, subprocess.TimeoutExpired):
        return []


def backend(runtime, data, mode='auto'):
    root=Path(runtime)
    if mode=='cpu':
        return root/'motor', [], 'CPU compatible'
    available=devices(str(root))
    selected=next((d for d in available if 'NVIDIA' in d[1] and d[2]>=5000),None)
    if mode=='vulkan' and available:
        selected=selected or available[0]
    if mode=='auto' and not selected:
        try:
            policy=json.loads((Path(data)/'acceleration.json').read_text('utf-8'))
            selected=next((d for d in available if d[1]==policy.get('device') and policy.get('gpu_faster') is True),None)
        except (OSError,ValueError,TypeError):
            pass
    if selected:
        layers='28' if 'NVIDIA' in selected[1] else '12'
        return root/'motor-vulkan', ['--device',selected[0],'-ngl',layers], selected[1]+' · Vulkan'
    return root/'motor', [], 'CPU compatible · GPU sin mejora verificada'
