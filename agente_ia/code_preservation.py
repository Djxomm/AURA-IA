"""Reject accidental loss of existing entry points in agent whole-file replacements."""
import ast,re
from pathlib import Path


def _python_names(tree,prefix=''):
    names=set()
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            name=prefix+node.name;names.add(name)
            if isinstance(node,ast.ClassDef):names.update(_python_names(node,name+'.'))
    return names


def validate_agent_change(path,original,proposed,whole_file=False):
    if proposed is None:return
    suffix=Path(path).suffix.lower()
    if suffix=='.py':
        try:new=ast.parse(proposed)
        except SyntaxError as error:raise ValueError(f'El cambio contiene un error de sintaxis Python en línea {error.lineno}: {error.msg}. Corrige la propuesta antes de escribir.') from error
        if not whole_file or not original:return
        try:old=ast.parse(original)
        except SyntaxError:return
        missing=_python_names(old)-_python_names(new)
    elif suffix in {'.js','.mjs','.cjs','.ts','.tsx'} and whole_file and original:
        pattern=r'(?m)^(?:export\s+(?:default\s+)?)?(?:async\s+)?(?:function\s*\*?\s*|class\s+|(?:const|let|var)\s+)([A-Za-z_$][\w$]*)'
        missing=set(re.findall(pattern,original))-set(re.findall(pattern,proposed))
    else:return
    if missing:raise ValueError('La sustitución completa eliminaría funciones o componentes existentes: '+', '.join(sorted(missing)[:12])+'. Lee el archivo y usa edit_file con el bloque exacto para un cambio localizado; conserva el resto del módulo.')
