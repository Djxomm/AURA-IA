"""Pygame project helpers; importing AURA never initializes SDL."""
import ast
import json
from pathlib import Path
import re
import shutil


def game_manifest(project):
    root = Path(project).resolve()
    file = root/'aura-game.json'
    if not file.exists():
        return None
    if not file.resolve().is_relative_to(root) or file.stat().st_size > 32768:
        raise ValueError('El manifiesto del juego no es válido.')
    data = json.loads(file.read_text('utf-8-sig'))
    if not isinstance(data, dict) or data.get('engine') != 'pygame':
        raise ValueError('El manifiesto debe indicar engine: pygame.')
    return data


def is_pygame_file(project, target):
    if game_manifest(project):
        return True
    file = Path(target)
    if file.stat().st_size > 512*1024:
        return False
    try:
        tree = ast.parse(file.read_text('utf-8-sig'))
    except (SyntaxError, UnicodeError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name.split('.')[0] == 'pygame' for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] == 'pygame':
            return True
    return False


def pygame_arguments(project, target, kind):
    root, target = Path(project).resolve(), Path(target).resolve()
    if not target.is_relative_to(root):
        raise ValueError('El juego debe estar dentro del proyecto seleccionado.')
    if kind == 'check':
        return ['-m', 'py_compile', str(target)]
    if kind == 'run':
        return [str(target)]
    data = game_manifest(root) or {}
    name = data.get('name', target.stem)
    if not isinstance(name, str) or not re.fullmatch(r'[\w-]{1,64}', name):
        raise ValueError('El nombre del juego debe tener de 1 a 64 letras, números, guiones o guiones bajos.')
    args = ['-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed', '--name', name, '--collect-binaries', 'pygame', '--collect-data', 'pygame', '--exclude-module', 'pygame.tests', '--exclude-module', 'pygame.examples']
    folders = data.get('asset_folders', [])
    if not isinstance(folders, list) or len(folders) > 10:
        raise ValueError('Define hasta diez carpetas de recursos.')
    for relative in folders:
        if not isinstance(relative, str) or not relative or relative == '.' or Path(relative).is_absolute() or '..' in Path(relative).parts or ';' in relative or ':' in relative:
            raise ValueError('La carpeta de recursos debe ser una ruta relativa.')
        folder = (root/relative).resolve()
        if not folder.is_relative_to(root) or not folder.is_dir():
            raise ValueError('Las carpetas de recursos deben existir dentro del proyecto.')
        args += ['--add-data', str(folder)+';'+Path(relative).as_posix()]
    icon = data.get('icon')
    if icon:
        icon_path = (root/icon).resolve()
        if not icon_path.is_relative_to(root) or not icon_path.is_file():
            raise ValueError('El icono debe ser un archivo del proyecto.')
        args += ['--icon', str(icon_path)]
    return args + [str(target)]


def create_game(runtime, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Elige una carpeta nueva para conservar los archivos existentes.')
    source = Path(runtime)/'games/pygame'
    if not (source/'main.py').is_file():
        raise ValueError('No se encontró la plantilla Pygame incluida.')
    shutil.copytree(source, destination)
    return destination
