"""Execute explicit user build/run/test requests, without asking the LLM to invent commands."""
from dataclasses import dataclass
from pathlib import Path
import os
import queue
import re
import subprocess
import threading
import time
import unicodedata
from .workspace import SafeWorkspace


def requested_actions(text):
    value=''.join(c for c in unicodedata.normalize('NFKD',text.lower()) if not unicodedata.combining(c)).strip(' ¿¡')
    value=re.sub(r'^(?:por favor[, ]+|puedes |podrias |quiero que )','',value)
    verbs=r'\b(compila(?:r(?:lo)?|lo)?|ejecuta(?:r(?:lo)?|lo)?|corre|prueba(?:lo)?|probemos|probamos|provamos|verifica(?:lo)?)\b'
    if not re.match(verbs,value):return []
    if re.search(r'\b(?:no compiles|sin ejecutar|explica|como compilar|primero modifica|primero corrige)\b',value):return []
    actions=[]
    for match in re.finditer(verbs,value):
        word=match[1]
        action='build' if word.startswith('compila') else 'run' if word.startswith(('ejecuta','corre')) else 'test' if word.startswith(('prueba','probe','proba','prova')) else 'check'
        if action not in actions:actions.append(action)
    return actions


@dataclass
class Command:
    program: Path
    arguments: list
    cwd: Path
    label: str
    timeout: int = 300
    artifact: Path | None = None


def choose_target(project, request, preferred=None):
    workspace=SafeWorkspace(str(project))
    explicit=re.findall(r'(?<![\w./\\-])([\w./\\-]+\.(?:py|cpp|cxx|cc|c|java|php|mjs|js|html|iss|exe))\b',request,re.I)
    for name in [*explicit,preferred]:
        if name:
            path=workspace.resolve_safe_path(str(name))
            if path.is_file():return path
            if name in explicit:raise ValueError('No existe el archivo solicitado: '+str(name))
    for name in ('main.py','app.py','main.cpp','main.c','Main.java','index.js','index.php','index.html'):
        path=workspace.root/name
        if path.is_file():return workspace.resolve_safe_path(name)
    files=[p for p in workspace.root.iterdir() if p.is_file() and p.suffix.lower() in {'.py','.c','.cpp','.cxx','.cc','.java','.php','.js','.iss'}]
    if len(files)==1:return workspace.resolve_safe_path(files[0].name)
    if (workspace.root/'package.json').is_file():return None
    raise ValueError('Abre el archivo en QbitX o indica su nombre: por ejemplo «compila main.py». No ejecuté ningún archivo.')


def plan(runtime, project, target, action):
    runtime,project=Path(runtime).resolve(),Path(project).resolve()
    if target and not Path(target).resolve().is_relative_to(project):raise ValueError('El archivo está fuera del proyecto.')
    from .framework_tools import find_web_project,npm_command
    web=find_web_project(project,target) if not target or target.suffix.lower() in {'.js','.html','.json'} else None
    if web:
        if action=='test':
            if 'test' not in web.scripts:raise ValueError('package.json no tiene un script test; no declararé pruebas aprobadas.')
            program=runtime/'herramientas/node/node.exe';args=[str(runtime/'herramientas/node/node_modules/npm/bin/npm-cli.js'),'run','test']
            if 'vitest' in web.scripts['test']:args+=['--','--run']
        else:program,args,_=npm_command(runtime,web,action)
        return [Command(program,args,web.root,'Proyecto web · '+action,3600 if action=='run' else 600)]
    if target is None:raise ValueError('Selecciona un archivo del proyecto.')
    target=Path(target).resolve();suffix=target.suffix.lower();output=project/'dist'/(target.stem+'.exe')
    if suffix=='.py':
        python=runtime/'herramientas/python/python.exe'
        if action=='test':
            tests=project/'tests'
            if tests.is_dir() and tests.resolve().is_relative_to(project) or list(project.glob('test_*.py')):
                return [Command(python,['-m','pytest','-q'],project,'Pruebas Python',300)]
            return [Command(python,[str(target)],project,'Ejecución de prueba · sin suite automatizada',120)]
        from .game_tools import is_pygame_file,pygame_arguments
        args=pygame_arguments(project,target,action) if is_pygame_file(project,target) else {'build':['-m','PyInstaller','--noconfirm','--onefile','--name',target.stem,str(target)],'run':[str(target)],'check':['-m','py_compile',str(target)]}[action]
        if action=='build' and target.stat().st_size<512*1024:
            source=target.read_text('utf-8-sig')
            if re.search(r'(?m)^\s*(?:from|import)\s+(?:panda3d|direct)(?:\.|\s)',source):
                args=args[:-1]+['--windowed','--collect-all','panda3d','--collect-all','direct',args[-1]]
        artifact=project/'dist'/((args[args.index('--name')+1] if '--name' in args else target.stem)+'.exe') if action=='build' else None
        return [Command(python,args,project,'Python · '+action,600 if action=='build' else 3600 if action=='run' else 120,artifact)]
    if suffix in {'.c','.cpp','.cc','.cxx'}:
        compiler=runtime/'herramientas/w64devkit/bin'/('gcc.exe' if suffix=='.c' else 'g++.exe')
        build=Command(compiler,['-std=c11' if suffix=='.c' else '-std=c++17','-Wall','-Wextra','-O2','-static',str(target),'-o',str(output)],project,'Compilar C/C++',artifact=output)
        if action=='check':return [Command(compiler,['-fsyntax-only',str(target)],project,'Sintaxis C/C++')]
        if action=='build':return [build]
        return ([] if output.is_file() and output.stat().st_mtime>=target.stat().st_mtime else [build])+[Command(output,[],project,'Ejecutar C/C++',3600 if action=='run' else 120)]
    if suffix=='.iss':
        if action!='build':raise ValueError('Un script Inno Setup se compila; no es un programa para ejecutar directamente.')
        return [Command(runtime/'herramientas/inno/ISCC.exe',[str(target)],project,'Crear instalador',600)]
    if suffix=='.exe':
        if action=='build':raise ValueError('Selecciona el código fuente, no el ejecutable, para compilar.')
        return [Command(target,[],project,'Ejecutar programa',3600 if action=='run' else 120)]
    from .language_tools import language_plan
    selected=language_plan(runtime,project,target,'run' if action=='test' else action)
    if selected.preview:raise ValueError('HTML se abre como vista previa desde Ejecutar en QbitX; no requiere compilación.')
    if selected.program is None:
        raise ValueError('HTML no se compila a EXE. Usa la vista previa del proyecto.')
    if selected.output_directory:selected.output_directory.mkdir(parents=True,exist_ok=True)
    return [Command(selected.program,selected.arguments,project,'Lenguaje · '+action)]


class ProjectRunner:
    def __init__(self,runtime):
        self.runtime=Path(runtime).resolve();self.cancelled=threading.Event();self.process=None;self.label='Preparando herramientas'

    def stop(self):
        self.cancelled.set()
        if self.process is not None and self.process.poll() is None:
            try:self.process.kill()
            except OSError:pass

    def run(self,project,request,actions,preferred=None,on_output=lambda value:None):
        if re.search(r'(?i)\baislad[oa]s?\b',request):
            from .windows_isolation import run
            return run(self,project,request,actions,preferred,on_output)
        project=Path(project).resolve();target=choose_target(project,request,preferred)
        reports=[];logs=[];success=True;last_artifact=None
        for action in actions:
            commands=[Command(last_artifact,[],project,'Ejecutar EXE compilado',3600 if action=='run' else 120)] if last_artifact is not None and (action=='run' or action=='test' and not (project/'tests').exists() and not list(project.glob('test_*.py'))) else plan(self.runtime,project,target,action)
            for command in commands:
                if self.cancelled.is_set():return {'status':'cancelled','content':'Proceso detenido por el usuario.','commands':reports}
                if not command.program.is_file():raise ValueError('No se encontró la herramienta incluida: '+str(command.program))
                (project/'dist').mkdir(exist_ok=True)
                if not (project/'dist').resolve().is_relative_to(project):raise ValueError('La salida está fuera del proyecto.')
                self.label=command.label
                display=subprocess.list2cmdline([str(command.program),*command.arguments]);on_output('> '+display)
                env=os.environ.copy();env.update({'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'})
                env.pop('PYTHONPATH',None);env.pop('NODE_OPTIONS',None);env['PATH']=str(command.program.parent)+os.pathsep+env.get('PATH','')
                wrapper=self.runtime/'herramientas/aura-web/aura-job.exe'
                args=([str(wrapper)] if wrapper.is_file() else [])+[str(command.program),*command.arguments]
                self.process=subprocess.Popen(args,cwd=command.cwd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
                channel=queue.Queue(maxsize=128)
                def read(process):
                    count=0
                    try:
                        while line:=process.stdout.readline(4096):
                            count+=len(line)
                            if count>4*1024**2:
                                channel.put('Límite de salida de 4 MiB alcanzado; se detuvo el proceso.\n');self.stop();break
                            while not self.cancelled.is_set():
                                try:channel.put(line.decode('utf-8','replace'),timeout=.2);break
                                except queue.Full:pass
                    finally:
                        try:channel.put(None,timeout=.2)
                        except queue.Full:pass
                threading.Thread(target=read,args=(self.process,),daemon=True).start();start=time.monotonic();timeout=False
                while True:
                    if self.cancelled.is_set() or time.monotonic()-start>command.timeout:
                        timeout=not self.cancelled.is_set();self.stop()
                    try:line=channel.get(timeout=.1)
                    except queue.Empty:
                        if self.process.poll() is not None:break
                        continue
                    if line is None:break
                    logs.append(line);logs=logs[-40:];on_output(line.rstrip())
                code=self.process.wait();self.process.stdout.close();self.process=None
                if code==0 and command.artifact is not None:
                    if command.artifact.is_file():last_artifact=command.artifact
                    else:code=1;logs.append('No se encontró el archivo que debía producir el compilador.\n')
                reports.append({'artifact':str(command.artifact) if command.artifact else None,'action':action,'command':display,'exit_code':code,'seconds':round(time.monotonic()-start,2),'timeout':timeout})
                on_output('Código de salida: '+str(code))
                if code!=0 or timeout or self.cancelled.is_set():success=False;break
            if not success:break
        status='cancelled' if self.cancelled.is_set() else 'done' if success else 'error'
        title='Acciones terminadas correctamente.' if success else 'La herramienta informó un error; no marqué la compilación como correcta.'
        if status=='cancelled':title='Proceso detenido por el usuario o por tiempo límite.'
        text=title+'\n'+'\n'.join(r['action']+': salida '+str(r['exit_code']) for r in reports)
        if last_artifact is not None:text+='\nArchivo generado: '+str(last_artifact)
        elif 'build' in actions and success:text+='\nLa salida de la herramienta indica dónde se guardó el resultado.'
        if logs:text+='\n\nÚltima salida real:\n'+''.join(logs)[-1800:]
        return {'status':status,'content':text,'commands':reports,'target':str(target) if target else '.'}
