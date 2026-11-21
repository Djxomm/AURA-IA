"""Optional Windows Sandbox job preparation. Never enables Windows features or falls back silently."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET


def executable():
    path=Path(os.environ.get('WINDIR','C:/Windows'))/'System32/WindowsSandbox.exe'
    return path if path.is_file() else None


def prepare(runtime,project,request,actions,preferred,root,max_bytes=512*1024**2):
    from .project_actions import choose_target,plan
    runtime=Path(runtime).resolve();project=Path(project).resolve();target=choose_target(project,request,preferred)
    job=Path(root).resolve()/uuid.uuid4().hex;source=job/'input';output=job/'output';control=job/'control'
    files=[];total=0;excluded={'.git','.venv','venv','__pycache__','.cache'}
    for file in project.rglob('*'):
        rel=file.relative_to(project)
        if any(part in excluded for part in rel.parts) or file.is_symlink():continue
        if file.name.startswith('.env') or file.suffix.lower() in {'.db','.sqlite','.sqlite3','.bak','.key','.pem','.pfx','.dpapi'}:continue
        if file.is_file():
            if not file.resolve().is_relative_to(project):raise ValueError('Hay una ruta fuera del proyecto.')
            total+=file.stat().st_size
            if total>max_bytes or len(files)>=20000:raise ValueError('La copia aislada supera 512 MiB o 20000 archivos.')
            files.append((file,rel))
    source.mkdir(parents=True);output.mkdir();control.mkdir()
    for file,relative in files:
        destination=source/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,destination)
    def quote(value):return "'"+str(value).replace("'","''")+"'"
    def mapped(value):
        value=str(value)
        for host,guest in [(str(runtime/'herramientas'),'C:\\AURA-Tools'),(str(project),'C:\\Work')]:
            if value.lower().startswith(host.lower()):return guest+value[len(host):].replace('/','\\')
        return value
    script=["$ErrorActionPreference='Stop'", "$steps=@();$code=1", "New-Item -ItemType Directory -Force C:\\Work | Out-Null", "Get-ChildItem -LiteralPath C:\\AURA-Input | Copy-Item -Destination C:\\Work -Recurse -Force", "try {"]
    for action in actions:
        for command in plan(runtime,project,target,action):
            program=command.program.resolve()
            if not program.is_relative_to(runtime/'herramientas') and not program.is_relative_to(project):raise ValueError('La herramienta no está disponible dentro del entorno aislado.')
            script+=['Set-Location -LiteralPath '+quote(mapped(command.cwd)), '$program='+quote(mapped(program)), '$arguments=@('+','.join(quote(mapped(arg)) for arg in command.arguments)+')', "$ErrorActionPreference='Continue';$global:LASTEXITCODE=1", '& $program @arguments 2>&1 | Out-File -FilePath C:\\AURA-Output\\run.log -Append -Encoding utf8', '$code=$LASTEXITCODE', "$ErrorActionPreference='Stop'", '$steps+=@{action='+quote(action)+';exit_code=$code}', "if($code -ne 0){throw 'La herramienta devolvió un error.'}"]
    script += ["} catch { $_ | Out-File -FilePath C:\\AURA-Output\\run.log -Append -Encoding utf8 }", "if(Test-Path C:\\Work\\dist){Copy-Item -LiteralPath C:\\Work\\dist -Destination C:\\AURA-Output -Recurse -Force}", "@{exit_code=$code;steps=$steps;isolated=$true} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath C:\\AURA-Output\\result.json -Encoding utf8", "shutdown.exe /s /t 0"]
    (control/'Run.ps1').write_text('\n'.join(script),encoding='utf-8-sig')
    config=ET.Element('Configuration')
    for name,value in [('vGPU','Disable'),('ProtectedClient','Enable'),('Networking','Disable'),('ClipboardRedirection','Disable'),('AudioInput','Disable'),('VideoInput','Disable'),('PrinterRedirection','Disable'),('MemoryInMB','4096')]:ET.SubElement(config,name).text=value
    folders=ET.SubElement(config,'MappedFolders')
    for host,guest,readonly in [(source,'C:\\AURA-Input',True),(runtime/'herramientas','C:\\AURA-Tools',True),(control,'C:\\AURA-Control',True),(output,'C:\\AURA-Output',False)]:
        item=ET.SubElement(folders,'MappedFolder');ET.SubElement(item,'HostFolder').text=str(host);ET.SubElement(item,'SandboxFolder').text=guest;ET.SubElement(item,'ReadOnly').text=str(readonly).lower()
    login=ET.SubElement(config,'LogonCommand');ET.SubElement(login,'Command').text='powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\\AURA-Control\\Run.ps1'
    file=job/'AURA-Prueba-Aislada.wsb';ET.ElementTree(config).write(file,encoding='utf-8',xml_declaration=True)
    (job/'job.json').write_text(json.dumps({'project':str(project),'actions':actions,'snapshot_bytes':total,'source_files':len(files),'network':False,'original_project_mapped':False},indent=2),encoding='utf-8')
    return file,output


def run(runner,project,request,actions,preferred,on_output):
    path=executable()
    if path is None:
        raise ValueError('Windows Sandbox no está habilitado. No ejecuté la tarea en modo normal. Puedes habilitarlo desde Características de Windows en Windows Pro y reiniciar; AURA no modifica esa configuración automáticamente.')
    import psutil
    if any(p.info['name'] in {'WindowsSandboxClient.exe','WindowsSandbox.exe'} for p in psutil.process_iter(['name'])):
        raise ValueError('Ya hay un Windows Sandbox abierto. Ciérralo antes de iniciar esta prueba.')
    root=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'AURA_IA'/'PruebasAisladas'
    config,output=prepare(runner.runtime,project,request,actions,preferred,root)
    on_output('Iniciando copia aislada sin red ni portapapeles. Proyecto original no modificable.');runner.label='Prueba aislada de Windows';runner.process=subprocess.Popen([str(path),str(config)])
    owned={};start=time.monotonic()
    while not (output/'result.json').is_file():
        if runner.process.poll() is None:
            try:
                for child in psutil.Process(runner.process.pid).children(recursive=True):owned[child.pid]=child.create_time()
            except psutil.Error:pass
        if runner.cancelled.is_set() or time.monotonic()-start>900:
            runner.stop()
            for pid,created in owned.items():
                try:
                    child=psutil.Process(pid)
                    if child.create_time()==created:child.terminate()
                except psutil.Error:pass
            return {'status':'cancelled','content':'Se solicitó detener la prueba aislada. Si Windows Sandbox sigue visible, cierra su ventana. El proyecto original no fue modificado.','commands':[]}
        time.sleep(.3)
    result=json.loads((output/'result.json').read_text('utf-8-sig'));runner.process=None
    code=result.get('exit_code',1);text=('Prueba aislada terminada.' if code==0 else 'La prueba aislada informó un error.')+'\nCódigo de salida: '+str(code)+'\nResultados: '+str(output)+'\nNo se ejecutaron artefactos en el equipo anfitrión.'
    log=output/'run.log'
    if log.is_file():
        with log.open('rb') as stream:
            stream.seek(max(0,log.stat().st_size-4000));text+='\nSalida real:\n'+stream.read().decode('utf-8-sig','replace')[-1800:]
    return {'status':'done' if code==0 else 'error','content':text,'commands':result.get('steps',[]),'target':'.','isolated':True}
