"""Single resident GGUF model with transactional switching and local CPU inference."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, threading, time, urllib.request, urllib.error, uuid
from pathlib import Path
from urllib.parse import urlparse

class NativeBackend:
    def __init__(self, runtime, data):
        self.runtime=Path(runtime).resolve();self.data=Path(data).resolve();self.data.mkdir(parents=True,exist_ok=True)
        self.token=secrets.token_hex(32);self.key_file=self.data/'backend.key';self.key_file.write_text(self.token+'\n',encoding='ascii')
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.process=None;self.log=None;self.closed=threading.Event()
    @property
    def url(self):return f'http://127.0.0.1:{self.port}/v1'
    def request(self,path,timeout=5):
        req=urllib.request.Request(f'http://127.0.0.1:{self.port}'+path,headers={'Authorization':'Bearer '+self.token})
        with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)
    def start(self, model, settings):
        if self.closed.is_set():raise RuntimeError('AURA se está cerrando.')
        self.stop()
        exe=self.runtime/'llama-server.exe'
        if not exe.is_file():raise ValueError('Falta el motor CPU de AURA.')
        self.log=(self.data/'motor.log').open('a',encoding='utf-8')
        args=[str(exe),'-m',str(model),'--host','127.0.0.1','--port',str(self.port),'-c',str(settings.num_ctx),'-t',str(settings.num_thread),'-tb',str(settings.num_thread),'-b',str(settings.num_batch),'-ub',str(min(settings.num_batch,128)),'-ngl','0','--parallel','1','--poll','0','--prio','-1','--no-webui','--no-warmup','--alias','aura-local','--api-key-file',str(self.key_file)]
        self.process=subprocess.Popen(args,cwd=str(self.runtime),stdout=self.log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
        for _ in range(1200):
            if self.closed.is_set():self.stop();raise RuntimeError('AURA se cerró durante la carga.')
            if self.process is None or self.process.poll() is not None:raise ValueError('Este modelo no pudo cargarse. Consulta el registro del motor; el anterior se restaurará si es posible.')
            try:
                if self.request('/health',timeout=2).get('status')=='ok':
                    models=self.request('/v1/models');props=self.request('/props')
                    template=str(props.get('chat_template',''))
                    from .aura_api import conversation_system_prompt
                    warm={'model':models['data'][0]['id'],'messages':[{'role':'system','content':conversation_system_prompt(settings)},{'role':'user','content':'Hola'}],'max_tokens':1,'temperature':0,'stream':False,'cache_prompt':True}
                    if 'enable_thinking' in template:warm['chat_template_kwargs']={'enable_thinking':False}
                    req=urllib.request.Request(self.url+'/chat/completions',data=json.dumps(warm).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token})
                    try:
                        with urllib.request.urlopen(req,timeout=120) as response:response.read()
                    except urllib.error.HTTPError as exc:
                        raise ValueError('Este GGUF no respondió como modelo de conversación compatible: HTTP '+str(exc.code)) from exc
                    except Exception as exc:
                        if self.closed.is_set():raise RuntimeError('AURA se cerró durante la preparación.') from exc
                    return {'model':models['data'][0]['id'],'reasoning_supported':'enable_thinking' in template,'url':self.url}
            except (urllib.error.URLError, TimeoutError, ConnectionError):time.sleep(.5)
        self.stop();raise ValueError('Se agotaron diez minutos al cargar el modelo.')
    def stop(self):
        p=self.process
        if p is not None and p.poll() is None:
            p.terminate()
            try:p.wait(timeout=8)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
        self.process=None
        if self.log:self.log.close();self.log=None
    def close(self):self.closed.set();self.stop()

class ModelManager:
    def __init__(self, base, data, storage, backend=None):
        self.base=Path(base);self.data=Path(data);self.storage=storage
        self.index=self.data/'modelos'/'catalogo.json';self.backend=backend or NativeBackend(self.base/'motor',self.data/'runtime')
        self.lock=threading.RLock();self.phase='starting';self.detail='Preparando el motor local';self.error='';self.warning='';self.started=time.monotonic();self.active_id='';self.worker=None
    def _imports(self):
        try:r=json.loads(self.index.read_text('utf-8'));return r if isinstance(r,list) else []
        except (OSError,ValueError):return []
    def catalog(self):
        default=self.base/'modelos'/'qwen2.5-coder-1.5b-instruct-q4_k_m.gguf'
        records=[{'id':'incluido','name':'Qwen2.5 Coder 1.5B · incluido','path':str(default),'bundled':True}]+self._imports()
        result=[]
        for record in records:
            p=Path(record['path']);item=dict(record)
            item.update({'exists':p.is_file(),'bytes':p.stat().st_size if p.is_file() else 0,'active':record['id']==self.active_id})
            result.append(item)
        return result
    def import_model(self,path,name=''):
        p=Path(path).expanduser().resolve()
        if p.suffix.lower()!='.gguf' or not p.is_file():raise ValueError('Selecciona un archivo GGUF existente.')
        with p.open('rb') as file:
            if file.read(4)!=b'GGUF':raise ValueError('El archivo no tiene una cabecera GGUF válida.')
        if p.stat().st_size>12*1024**3:raise ValueError('Ese modelo supera 12 GiB. Usa otro equipo o un servidor local para modelos de ese tamaño.')
        with self.lock:
            for r in self.catalog():
                if os.path.normcase(str(Path(r['path']).resolve()))==os.path.normcase(str(p)):return r
            records=self._imports()
            if len(records)>=30:raise ValueError('El catálogo admite hasta treinta modelos adicionales.')
            record={'id':uuid.uuid4().hex[:16],'name':(name or p.stem)[:100],'path':str(p),'bundled':False};records.append(record)
            self.index.parent.mkdir(parents=True,exist_ok=True);temp=self.index.with_suffix('.tmp');temp.write_text(json.dumps(records,ensure_ascii=False),'utf-8');temp.replace(self.index)
            return record
    def status(self):
        with self.lock:return {'phase':self.phase,'detail':self.detail,'error':self.error,'warning':self.warning,'active_id':self.active_id,'elapsed_seconds':round(time.monotonic()-self.started,1) if self.phase in ('starting','loading','restoring') else 0,'cpu_only':True,'resident_models':1 if self.active_id else 0,'reasoning_supported':self.storage.get_settings().reasoning_supported}
    def auth_for(self,url):
        return self.backend.token if url.rstrip('/')==self.backend.url.rstrip('/') else 'local'
    def _load(self,record,settings):
        p=Path(record['path'])
        if not p.is_file():raise ValueError('El modelo ya no está en su carpeta. Vuelve a agregarlo o usa el incluido.')
        with p.open('rb') as file:
            if file.read(4)!=b'GGUF':raise ValueError('GGUF inválido.')
        info=self.backend.start(p,settings)
        current=self.storage.get_settings()
        self.storage.save_settings(current.model_copy(update={'local_model_id':record['id'],'provider':'llamacpp','model':info['model'],'llamacpp_url':info['url'],'reasoning_supported':info.get('reasoning_supported',False),'num_ctx':settings.num_ctx,'num_thread':settings.num_thread,'num_batch':settings.num_batch,'num_gpu':0}))
        self.active_id=record['id']
    def start_initial(self):
        settings=self.storage.get_settings();records=self.catalog();selected=next((r for r in records if r['id']==settings.local_model_id),records[0])
        try:self._load(selected,settings)
        except Exception as exc:
            if selected['id']=='incluido':self.phase='error';self.error=str(exc);raise
            self.warning='No se pudo abrir el modelo elegido; se recuperó el incluido. '+str(exc);self._load(records[0],settings)
        with self.lock:self.phase='ready';self.detail='Modelo local listo para responder.'
    def change(self,model_id,context=None,threads=None):
        with self.lock:
            if self.phase in ('starting','loading','restoring'):raise ValueError('Ya hay una carga de modelo en curso.')
            record=next((r for r in self.catalog() if r['id']==model_id),None)
            if record is None or not record['exists']:raise ValueError('El modelo seleccionado no está disponible.')
            previous=next((r for r in self.catalog() if r['id']==self.active_id),self.catalog()[0]);old=self.storage.get_settings()
            changes={}
            if context is not None:
                if context not in (2048,4096,8192):raise ValueError('Usa contexto 2048, 4096 u 8192 para este perfil.')
                changes['num_ctx']=context
            if threads is not None:
                if threads not in (1,2,4):raise ValueError('Usa uno, dos o cuatro hilos.')
                changes['num_thread']=threads
            target=old.model_copy(update=changes);self.phase='loading';self.started=time.monotonic();self.error='';self.warning='';self.detail='Cargando '+record['name'];self.active_id=''
        def work():
            try:
                self._load(record,target)
                with self.lock:self.phase='ready';self.detail='Modelo cargado. Las reglas y habilidades se conservan.'
            except Exception as exc:
                with self.lock:self.phase='restoring';self.detail='Restaurando el modelo anterior.';self.warning=str(exc)
                try:
                    self._load(previous,old)
                    with self.lock:self.phase='ready';self.detail='Se recuperó el modelo anterior.'
                except Exception as restore:
                    with self.lock:self.phase='error';self.active_id='';self.error='No pudo recuperarse el motor: '+str(restore)
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()
        return self.status()
    def close(self):self.backend.close()
