"""Small, explicit launch plans for the bundled language tools."""
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


@dataclass(frozen=True)
class LanguagePlan:
    program: Path | None
    arguments: list[str]
    output_directory: Path | None = None
    preview: bool = False
    note: str = ''


def language_plan(runtime, project, target, kind):
    runtime, project, target = Path(runtime), Path(project).resolve(), Path(target).resolve()
    if not target.is_relative_to(project):
        raise ValueError('El archivo debe estar dentro del proyecto seleccionado.')
    suffix = target.suffix.lower()
    if suffix in {'.html', '.htm'}:
        if kind == 'build':
            raise ValueError('HTML5 no necesita compilación. Usa Ejecutar para abrir su vista previa.')
        return LanguagePlan(None, [], preview=kind == 'run', note='Revisión básica de lectura HTML; no sustituye un validador HTML5 completo.')
    if suffix in {'.js', '.mjs', '.cjs'}:
        if kind == 'build':
            raise ValueError('JavaScript se ejecuta con Node.js. Usa Verificar o Ejecutar; no se genera un EXE automáticamente.')
        return LanguagePlan(runtime/'herramientas/node/node.exe', ['--max-old-space-size=256'] + (['--check'] if kind == 'check' else []) + [str(target)])
    if suffix == '.php':
        if kind == 'build':
            raise ValueError('PHP se interpreta. Usa Verificar o Ejecutar; no se genera un EXE automáticamente.')
        return LanguagePlan(runtime/'herramientas/php/php.exe', ['-n', '-d', 'memory_limit=128M'] + (['-l'] if kind == 'check' else []) + [str(target)], note='Ejecución PHP por consola; no inicia un servidor web.')
    if suffix == '.java':
        if kind == 'run':
            return LanguagePlan(runtime/'herramientas/jdk/bin/java.exe', ['-Xmx256m', '-XX:ActiveProcessorCount=2', '-Dfile.encoding=UTF-8', str(target)])
        output = project/'build'/'aurax-java'
        if not output.resolve().is_relative_to(project):
            raise ValueError('La carpeta de compilación debe estar dentro del proyecto.')
        return LanguagePlan(runtime/'herramientas/jdk/bin/javac.exe', ['-J-Xmx256m', '-J-XX:ActiveProcessorCount=2', '-encoding', 'UTF-8', '-proc:none', '-d', str(output), str(target)], output_directory=output, note='Java genera archivos .class en build/aurax-java. No es un EXE de Windows.')
    raise ValueError('Lenguaje no configurado para estos botones.')


def check_html(path):
    parser = HTMLParser(convert_charrefs=True)
    parser.feed(Path(path).read_text(encoding='utf-8-sig'))
    parser.close()
    return 'HTML leído correctamente. Comprobación básica; revisa la vista previa para comprobar su presentación.'
