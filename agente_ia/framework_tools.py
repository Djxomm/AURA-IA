"""npm project discovery and reviewed commands. No project code runs here."""
from dataclasses import dataclass
import json
from pathlib import Path
import shutil


@dataclass(frozen=True)
class WebProject:
    root: Path
    label: str
    scripts: dict


def find_web_project(workspace, target=None):
    workspace = Path(workspace).resolve()
    current = Path(target).resolve().parent if target else workspace
    if not current.is_relative_to(workspace):
        raise ValueError('El proyecto web debe estar dentro de la carpeta seleccionada.')
    while current.is_relative_to(workspace):
        file = current/'package.json'
        if file.is_file():
            if not file.resolve().is_relative_to(workspace) or file.stat().st_size > 512*1024:
                raise ValueError('package.json no es válido para este proyecto.')
            data = json.loads(file.read_text('utf-8-sig'))
            dependencies = {**data.get('dependencies', {}), **data.get('devDependencies', {})}
            scripts = data.get('scripts', {})
            if not isinstance(scripts, dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in scripts.items()):
                raise ValueError('Los scripts de package.json no son válidos.')
            label = 'React' if 'react' in dependencies else 'Vue.js' if 'vue' in dependencies else 'Proyecto npm'
            return WebProject(current, label, scripts)
        if current == workspace:
            break
        current = current.parent
    return None


def npm_command(runtime, project, action, port=5173):
    runtime = Path(runtime)
    prefix = [str(runtime/'herramientas/node/node_modules/npm/bin/npm-cli.js')]
    if action == 'build':
        script = 'build'
    elif action == 'check':
        script = next((name for name in ('typecheck', 'type-check', 'lint', 'build') if name in project.scripts), None)
    else:
        script = 'dev'
    if not script or script not in project.scripts:
        raise ValueError('El proyecto no incluye un script para esta acción en package.json.')
    args = prefix + ['run', script]
    if action == 'run':
        if 'vite' not in project.scripts[script]:
            raise ValueError('La vista previa automática es para Vite. Para otros servidores usa Terminal y limita la dirección a 127.0.0.1.')
        args += ['--', '--host', '127.0.0.1', '--port', str(port), '--strictPort']
    return runtime/'herramientas/node/node.exe', args, script


def create_template(runtime, destination, framework):
    if framework not in {'react', 'vue'}:
        raise ValueError('Selecciona React o Vue.js.')
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Elige una carpeta nueva para conservar los archivos existentes.')
    source = Path(runtime)/'frameworks/templates'/framework
    if not (source/'package.json').is_file():
        raise ValueError('No se encontró la plantilla incluida.')
    shutil.copytree(source, destination)
    return destination
