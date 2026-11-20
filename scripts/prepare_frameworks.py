"""Build the Windows x64 React/Vue offline cache from the committed lockfiles."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    runtime = ROOT/'runtime'
    node = runtime/'herramientas/node/node.exe'
    compiler = runtime/'herramientas/w64devkit/bin/g++.exe'
    if not node.is_file() or not compiler.is_file():
        raise RuntimeError('Prepara Node.js y w64devkit en runtime/herramientas antes de continuar.')
    tools = runtime/'herramientas/aura-web'
    tools.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(compiler), '-std=c++17', '-O2', '-static', '-municode', str(ROOT/'scripts/windows_job.cpp'), '-o', str(tools/'aura-job.exe')], check=True)
    shutil.copy2(ROOT/'scripts/framework_prepare.py', tools/'prepare.py')
    cache = ROOT/'build/framework-cache'
    cache.mkdir(parents=True, exist_ok=True)
    env = {key:value for key,value in os.environ.items() if not key.upper().startswith('NPM_CONFIG_') and key.upper() != 'NODE_AUTH_TOKEN'}
    env['PATH'] = str(node.parent) + os.pathsep + env.get('PATH', '')
    configs = []
    for name in ('user', 'global'):
        file = ROOT/'build'/f'framework-empty-{name}.npmrc'
        file.write_text('', encoding='utf-8')
        configs.append(str(file))
    for framework in ('react', 'vue'):
        source = ROOT/'frameworks/templates'/framework
        target = runtime/'frameworks/templates'/framework
        shutil.copytree(source, target, dirs_exist_ok=True)
        stage = ROOT/'build/framework-package-check'/framework
        shutil.copytree(source, stage, dirs_exist_ok=True)
        subprocess.run([str(node), str(node.parent/'node_modules/npm/bin/npm-cli.js'), 'ci', '--ignore-scripts', '--no-audit', '--no-fund', '--update-notifier=false', '--registry=https://registry.npmjs.org/', '--userconfig='+configs[0], '--globalconfig='+configs[1], '--cache', str(cache)], cwd=stage, env=env, check=True)
    archive = runtime/'frameworks/npm-cache.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as output:
        for file in (cache/'_cacache').rglob('*'):
            if file.is_file():
                output.write(file, file.relative_to(cache).as_posix())
    manifest = json.loads((ROOT/'frameworks/manifest.json').read_text('utf-8'))
    with archive.open('rb') as stream:
        manifest['cache_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    (runtime/'frameworks/manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Plantillas y caché offline preparadas.')


if __name__ == '__main__':
    main()
