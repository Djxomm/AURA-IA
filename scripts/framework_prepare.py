"""Prepare npm dependencies using the bundled cache; no lifecycle scripts."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import zipfile


def main():
    runtime, project = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    offline = sys.argv[3] == 'offline'
    if not (project/'package.json').is_file():
        raise ValueError('No se encontró package.json en el proyecto seleccionado.')
    cache = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))/'AURA_IA'/'npm-framework-cache'
    cache.mkdir(parents=True, exist_ok=True)
    archive = runtime/'frameworks/npm-cache.zip'
    manifest = json.loads((runtime/'frameworks/manifest.json').read_text('utf-8'))
    expected = manifest['cache_sha256']
    marker = cache/'aura-cache-version.txt'
    if not marker.exists() or marker.read_text('ascii') != expected:
        print('Preparando dependencias incluidas…', flush=True)
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('El paquete de dependencias no coincide con su huella de comprobación.')
        with zipfile.ZipFile(archive) as package:
            for index, entry in enumerate(package.infolist()):
                target = (cache/entry.filename).resolve()
                if not target.is_relative_to(cache.resolve()) or stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError('Ruta no válida en el paquete de dependencias.')
                package.extract(entry, cache)
                if index % 100 == 0:
                    print(f'Preparando caché… {index} archivos', flush=True)
        marker.write_text(expected, encoding='ascii')
    args = [str(runtime/'herramientas/node/node.exe'), str(runtime/'herramientas/node/node_modules/npm/bin/npm-cli.js'), 'ci' if (project/'package-lock.json').is_file() else 'install', '--ignore-scripts', '--no-audit', '--no-fund', '--update-notifier=false', '--cache', str(cache)]
    if offline:
        args.append('--offline')
    env = os.environ.copy()
    env['PATH'] = str(runtime/'herramientas/node') + os.pathsep + env.get('PATH', '')
    print('Instalando dependencias ' + ('sin conexión…' if offline else 'con Internet…'), flush=True)
    return subprocess.call(args, cwd=project, env=env)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(str(error), flush=True)
        sys.exit(1)
