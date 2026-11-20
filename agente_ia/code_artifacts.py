"""Recover complete code proposals without treating snippets as finished work."""
import ast
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unicodedata


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))


def creation_request(text):
    text = normalized(text)
    if re.search(r'\b(explica|explicame|que es|como funciona|como crear|solo un ejemplo|no (?:lo )?(?:crees|escribas|generes|hagas))\b', text):
        return False
    return bool(re.search(r'\b(hazme|hasme|crea|creame|crear|genera|desarrolla|construye|implementa|has (?:el|un|una))\b', text) and re.search(r'\b(juego|guego|programa|aplicacion|app|web|pagina|archivo|script|proyecto)\b|\.(py|html|js)\b', text))


def task_brief(history, latest):
    users = [item['content'].replace('\r', '') for item in history if item.get('role') == 'user'] + [latest.replace('\r', '')]
    meaningful = [value.strip() for value in users if value.strip() and not re.fullmatch(r'(?i)(continua|sigue|ok|compila|compilalo|adelante)[ .!]*', value.strip())]
    selected = meaningful[:1] + meaningful[-4:]
    return '\n'.join(dict.fromkeys(value[:1800] for value in selected))[-7200:]


def expected_language(brief):
    language = None
    for line in brief.splitlines():
        text = normalized(line)
        if re.search(r'html|java\s*script|javascript|jaba\s*script|\.jsx?\b', text):
            language = 'html' if re.search(r'html|pagina|navegador', text) else 'javascript'
        elif re.search(r'python|pygame|\.py\b', text):
            language = 'python'
    return language


def validate_code(path, content, expected=None, runtime=None):
    suffix = Path(path).suffix.lower()
    actual = {'.py':'python', '.html':'html', '.htm':'html', '.js':'javascript', '.mjs':'javascript'}.get(suffix)
    if not actual:
        return
    if expected == 'html' and actual == 'python' or expected == 'python' and actual in {'html','javascript'}:
        raise ValueError('El lenguaje no coincide con la petición actual del usuario.')
    content = content.replace('\r', '')
    if re.search(r'(?im)^\s*(?:#|//|<!--)\s*(?:\.\.\.|TODO\b|resto del codigo|completa aqui)', content):
        raise ValueError('El código contiene partes pendientes o puntos suspensivos; no es un archivo completo.')
    if actual == 'python':
        tree = ast.parse(content, filename=path)
        if any(isinstance(node, ast.Constant) and node.value is Ellipsis for node in ast.walk(tree)):
            raise ValueError('El código Python contiene un marcador incompleto (...).')
        compile(tree, path, 'exec')
    elif actual == 'html':
        if not re.search(r'<html\b', content, re.I) or not re.search(r'</html\s*>', content, re.I):
            raise ValueError('Falta el documento HTML completo con su cierre.')
        scripts = re.findall(r'<script\b[^>]*>(.*?)</script\s*>', content, re.S | re.I)
        if len(scripts) != len(re.findall(r'<script\b', content, re.I)):
            raise ValueError('Hay un bloque JavaScript sin cerrar.')
        for script in scripts:
            check_javascript(script, runtime)
    elif actual == 'javascript':
        check_javascript(content, runtime)


def check_javascript(content, runtime):
    if not runtime:
        return
    node = Path(runtime)/'herramientas/node/node.exe'
    if not node.is_file():
        return
    import os
    env = os.environ.copy()
    env.pop('NODE_OPTIONS', None)
    with tempfile.TemporaryDirectory(prefix='aura-syntax-') as folder:
        file = Path(folder)/'proposal.mjs'
        file.write_text(content, encoding='utf-8')
        result = subprocess.run([str(node), '--check', str(file)], env=env, capture_output=True, text=True, timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('JavaScript no pasa la revisión de sintaxis: '+result.stderr[-1200:])


def code_proposal(text, expected, workspace, runtime=None):
    blocks = list(re.finditer(r'```(python|py|html|html5|javascript|js)\s*\n(.*?)```', text.replace('\r',''), re.S | re.I))
    if len(blocks) != 1:
        raise ValueError('Se necesita un archivo de código completo, no fragmentos separados o incompletos.')
    match = blocks[0]
    language = {'py':'python','html5':'html','js':'javascript'}.get(match[1].lower(), match[1].lower())
    if expected and language != expected:
        raise ValueError('El modelo respondió en '+language+' pero se pidió '+expected+'.')
    path = {'python':'main.py','html':'index.html','javascript':'main.js'}[language]
    content = match[2].replace('\r','').strip()+'\n'
    validate_code(path, content, expected, runtime)
    target = workspace.resolve_safe_path(path, allow_write=True)
    return ('write_file' if target.exists() else 'create_file'), {'path':path,'content':content,'reason':'Guardar el archivo completo solicitado; requiere revisión del usuario.'}


def file_task_requested(text, history=()):
    if creation_request(text):
        return True
    followup = bool(re.match(r'(?i)^\s*(continua|sigue|compila|compilalo|hazlo|dale|ok entonces|que sea|cambialo)', normalized(text)))
    return followup and creation_request(task_brief(history, text))
