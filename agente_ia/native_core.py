"""Native-only inference, explicit local memory and offline dictation."""
from __future__ import annotations
import asyncio, atexit, base64, codecs, hashlib, http.client, json, mimetypes, os, re, socket, sqlite3, subprocess, threading, time, urllib.error, urllib.request, uuid
from pathlib import Path
from .providers import ProviderResponse, ProviderError, ToolCall, _adapt_messages_for_xml
from .tools import parse_xml_tool_calls


class _RepetitionLoopError(Exception):
 """Señal interna cuando el modelo local entra en un bucle repetitivo degenerado."""


def _has_repetition_loop(text: str, *, min_unit: int = 16, max_unit: int = 180, repeats: int = 5) -> bool:
 if len(text) < min_unit * repeats:
  return False
 tail = text[-(max_unit * repeats + 32):]
 max_p = min(max_unit, len(tail) // repeats)
 for p in range(min_unit, max_p + 1):
  unit = tail[-p:]
  if len(unit.strip()) < 10:
   continue
  if tail.endswith(unit * repeats):
   return True
 return False

class Memory:
 def __init__(self,path):
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock()
  self.db=sqlite3.connect(self.path,check_same_thread=False);self.db.row_factory=sqlite3.Row
  self.db.executescript('''CREATE TABLE IF NOT EXISTS memory(id TEXT PRIMARY KEY,project TEXT NOT NULL,content TEXT NOT NULL,source TEXT NOT NULL,updated REAL NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content,content=memory,content_rowid=rowid);
CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory BEGIN INSERT INTO memory_fts(rowid,content) VALUES(new.rowid,new.content); END;
CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory BEGIN INSERT INTO memory_fts(memory_fts,rowid,content) VALUES('delete',old.rowid,old.content); END;
CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory BEGIN INSERT INTO memory_fts(memory_fts,rowid,content) VALUES('delete',old.rowid,old.content); INSERT INTO memory_fts(rowid,content) VALUES(new.rowid,new.content); END;''');self.db.commit()
 def save(self,content,project='',source='Indicación del usuario',ident=None):
  content=content.strip()
  if not content:raise ValueError('Escribe el recuerdo.')
  if len(content)>12000:raise ValueError('El recuerdo supera 12000 caracteres.')
  if re.search(r'(?i)(api[_ -]?key|password|contrase[nñ]a|clave privada|-----BEGIN|sk-[a-z0-9]{12})',content):raise ValueError('No guardes contraseñas ni claves en la memoria.')
  ident=ident or uuid.uuid4().hex
  with self.lock:self.db.execute('INSERT INTO memory VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET content=excluded.content,project=excluded.project,source=excluded.source,updated=excluded.updated',(ident,project,content,source,time.time()));self.db.commit()
  return ident
 def delete(self,ident):
  with self.lock:self.db.execute('DELETE FROM memory WHERE id=?',(ident,));self.db.commit()
 def list(self,project=None):
  with self.lock:return [dict(x) for x in self.db.execute('SELECT * FROM memory '+('WHERE project IN (?,\'\') ' if project is not None else '')+'ORDER BY updated DESC',() if project is None else (project,))]
 def search(self,text,project='',limit=5):
  terms=re.findall(r'\w{3,}',text.lower(),re.UNICODE)[:20]
  if not terms:return self.list(project)[:limit]
  query=' OR '.join('"'+x+'"' for x in terms)
  with self.lock:return [dict(x) for x in self.db.execute('SELECT m.* FROM memory_fts f JOIN memory m ON m.rowid=f.rowid WHERE memory_fts MATCH ? AND m.project IN (?,\'\') ORDER BY rank LIMIT ?',(query,project,limit))]
 def close(self):self.db.close()

class NativeOutputFilter:
 def __init__(self):self.start=True;self.held='';self.discard=False
 def feed(self,text):
  out=[];prefix='llama_completion:'
  for ch in text:
   if ch=='\r':continue
   if self.discard:
    if ch=='\n':self.discard=False;self.start=True;self.held=''
    continue
   if self.start:
    self.held+=ch
    if self.held.startswith(prefix):self.held='';self.discard=True;self.start=False;continue
    if prefix.startswith(self.held):continue
    out.append(self.held);self.start=False;self.held=''
   else:out.append(ch)
   if ch=='\n':self.start=True
  return ''.join(out)
 def finish(self):return self.held if not self.discard else ''

class NativeClient:
 def __init__(self,runtime,data,model=None):
  self.runtime=Path(runtime).resolve();self.data=Path(data).resolve();self.data.mkdir(parents=True,exist_ok=True)
  self.model=Path(model or self.runtime/'modelos/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf').resolve();self.process=None;self.cancelled=threading.Event();self.first_text=None;self.lock=threading.Lock();self.auto_context=True;self.effective_context=None;self.acceleration="auto";self.backend_note="CPU compatible"
  self.use_persistent_server=True;self._server_proc=None;self._server_port=None;self._server_sig=None;self._server_log=None;self._active_http=None
  atexit.register(self.close)
 def close(self):
  proc=getattr(self,'_server_proc',None)
  self._server_proc=None;self._server_port=None;self._server_sig=None
  if proc is not None and proc.poll() is None:
   try:proc.terminate();proc.wait(timeout=3)
   except Exception:
    try:proc.kill()
    except OSError:pass
  log=getattr(self,'_server_log',None);self._server_log=None
  if log is not None:
   try:log.close()
   except Exception:pass
 def stop(self):
  self.cancelled.set();p=self.process
  if p is not None and p.poll() is None:
   p.terminate()
  req=getattr(self,'_active_http',None)
  if req is not None:
   try:
    raw=getattr(getattr(req,'fp',None),'raw',None)
    sock=getattr(raw,'_sock',None)
    if sock is not None:sock.close()
   except Exception:pass
   try:req.close()
   except Exception:pass
 def _ensure_server(self,engine,effective,settings,gpu_args,*,arch='',mmproj=None,mtp=None):
  sig=(str(engine.resolve()),str(self.model.resolve()),self.model.stat().st_mtime_ns,int(effective),tuple(gpu_args or ()),int(settings.num_thread),arch,str(mmproj or ''),str(mtp or ''))
  if self._server_proc is not None and self._server_proc.poll() is None and self._server_sig==sig and self._server_port:
   return self._server_port
  self.close()
  with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
   s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  prefill_batch=str(max(128,min(512,max(int(settings.num_batch),256))))
  ubatch=str(max(64,min(256,int(prefill_batch)//2)))
  args=[
   str(engine/'llama-server.exe'),'-m',str(self.model),'-c',str(effective),
   '-t',str(settings.num_thread),'-tb',str(settings.num_thread),
   '-b',prefill_batch,'-ub',ubatch,
   '-fa','on','-ctk','q8_0','-ctv','q8_0',
   '--cache-reuse','256','-sps','0.5','--no-webui','--no-warmup',
   '-np','1','-ngl','0','--host','127.0.0.1','--port',str(port),
  ]
  if arch=='gemma4':
   args.append('--jinja')
  if mmproj is not None and Path(mmproj).is_file():
   args+=['--mmproj',str(mmproj)]
  if mtp is not None and Path(mtp).is_file():
   args+=['--spec-type','draft-mtp','-md',str(mtp)]
  if gpu_args:
   args[args.index('-ngl')+1]=gpu_args[-1];args+=gpu_args[:2]
  self._server_log=(self.data/'motor-server.log').open('a',encoding='utf-8')
  flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
  self._server_proc=subprocess.Popen(args,cwd=engine,stdin=subprocess.DEVNULL,stdout=self._server_log,stderr=self._server_log,creationflags=flags)
  self._server_port=port;self._server_sig=sig
  deadline=time.monotonic()+60.0
  health_url=f'http://127.0.0.1:{port}/health'
  while time.monotonic()<deadline:
   if self.cancelled.is_set():
    self.close();raise ProviderError('Respuesta detenida por el usuario.')
   if self._server_proc.poll() is not None:
    self.close()
    if mtp is not None:
     return self._ensure_server(engine,effective,settings,gpu_args,arch=arch,mmproj=mmproj,mtp=None)
    raise ProviderError('El servidor local de inferencia no pudo iniciar.')
   try:
    with urllib.request.urlopen(health_url,timeout=0.8) as resp:
     if resp.status==200:
      return port
   except Exception:
    time.sleep(0.15)
  self.close();raise ProviderError('Tiempo agotado al iniciar el servidor local de inferencia.')
 def supports_native_multimodal(self):
  try:
   from .model_library import model_info,find_paired_multimodal_files
   arch=str(model_info(self.model).get('general.architecture') or '')
   return arch=='gemma4' and find_paired_multimodal_files(self.model).get('mmproj') is not None
  except Exception:
   return False
 @staticmethod
 def _build_multimodal_messages(messages,media_paths=()):
  out=[]
  for m in messages:
   role=str(m.get('role') or 'user')
   content=str(m.get('content') or '')
   out.append({'role':role,'content':content})
  paths=[Path(p) for p in (media_paths or ()) if Path(p).is_file()]
  if not paths or not out:
   return out
  target_idx=next((i for i in range(len(out)-1,-1,-1) if out[i]['role']=='user'),len(out)-1)
  parts=[{'type':'text','text':out[target_idx]['content']}]
  for p in paths[:4]:
   ext=p.suffix.lower()
   raw=p.read_bytes()
   if len(raw)>20*1024*1024:continue
   b64=base64.b64encode(raw).decode('ascii')
   if ext in {'.png','.jpg','.jpeg','.webp','.bmp','.gif'}:
    mime=mimetypes.guess_type(p.name)[0] or 'image/png'
    parts.append({'type':'image_url','image_url':{'url':f'data:{mime};base64,{b64}'}})
   elif ext in {'.wav','.mp3'}:
    fmt='mp3' if ext=='.mp3' else 'wav'
    parts.append({'type':'input_audio','input_audio':{'data':b64,'format':fmt}})
  out[target_idx]={'role':out[target_idx]['role'],'content':parts}
  return out
 def _generate_server_chat(self,messages,budget,settings,callback,engine,effective,gpu_args,mmproj,mtp,media_paths=(),anti_repeat=False):
  start=time.monotonic()
  port=self._ensure_server(engine,effective,settings,gpu_args,arch='gemma4',mmproj=mmproj,mtp=mtp)
  mm_msgs=self._build_multimodal_messages(messages,media_paths)
  enable_thinking=str(getattr(settings,'thinking_effort','equilibrado')).lower() in ('profundo','maximo')
  temp=max(0.25,float(settings.temperature)) if anti_repeat else float(settings.temperature)
  body_obj={
   'model':self.model.stem,
   'messages':mm_msgs,
   'max_tokens':int(budget),
   'temperature':temp,
   'stream':True,
   'chat_template_kwargs':{'enable_thinking':enable_thinking},
  }
  if anti_repeat:
   body_obj['repeat_penalty']=1.15;body_obj['repeat_last_n']=128
  elif temp>0.01:
   body_obj['repeat_penalty']=1.08;body_obj['repeat_last_n']=64
  payload=json.dumps(body_obj).encode('utf-8')
  req=urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions',data=payload,headers={'Content-Type':'application/json'},method='POST')
  answer='';last_loop_check=0
  try:
   resp=urllib.request.urlopen(req,timeout=300)
   self._active_http=resp
   try:
    for raw_line in resp:
     if self.cancelled.is_set():raise ProviderError('Respuesta detenida por el usuario.')
     line=raw_line.decode('utf-8','replace').strip()
     if not line.startswith('data:'):continue
     body=line[5:].strip()
     if not body or body=='[DONE]':break
     try:chunk=json.loads(body)
     except ValueError:continue
     choices=chunk.get('choices') or []
     if not choices:continue
     delta=choices[0].get('delta') or {}
     text=str(delta.get('content') or '')
     if text:
      if self.first_text is None and text.strip():self.first_text=time.monotonic()-start
      answer+=text;callback(text)
      if len(answer)-last_loop_check>=64:
       last_loop_check=len(answer)
       if _has_repetition_loop(answer):
        raise _RepetitionLoopError('Bucle repetitivo detectado en servidor multimodal.')
     if choices[0].get('finish_reason'):break
   finally:
    self._active_http=None
    try:resp.close()
    except Exception:pass
  except _RepetitionLoopError:
   if not anti_repeat and not self.cancelled.is_set():
    return self._generate_server_chat(messages,budget,settings,callback,engine,effective,gpu_args,mmproj,mtp,media_paths=media_paths,anti_repeat=True)
   raise ProviderError('Se detectó un bucle de repetición en el modelo local y se detuvo automáticamente. Prueba con Razonamiento · Equilibrado o reformula la tarea.')
  except (urllib.error.URLError,http.client.HTTPException,AttributeError,OSError,ValueError) as exc:
   if self.cancelled.is_set():raise ProviderError('Respuesta detenida por el usuario.')
   self.close()
   raise ProviderError(f'Error de conexión con servidor multimodal local: {exc}') from exc
  if self.cancelled.is_set():raise ProviderError('Respuesta detenida por el usuario.')
  answer=answer.replace('[end of text]','').strip()
  if not answer:raise ProviderError('El modelo no produjo texto.')
  return answer,time.monotonic()-start
 def _generate_server(self,prompt,budget,settings,use_cache,callback,engine,effective,gpu_args,harmony_filter,stop_tokens,anti_repeat=False):
  start=time.monotonic()
  port=self._ensure_server(engine,effective,settings,gpu_args)
  temp=max(0.25,float(settings.temperature)) if anti_repeat else float(settings.temperature)
  body_obj={
   'prompt':prompt,
   'n_predict':int(budget),
   'temperature':temp,
   'stream':True,
   'cache_prompt':bool(use_cache) and not anti_repeat,
   'stop':list(stop_tokens),
  }
  if anti_repeat:
   body_obj['repeat_penalty']=1.15;body_obj['repeat_last_n']=128
  elif temp>0.01:
   body_obj['repeat_penalty']=1.08;body_obj['repeat_last_n']=64
  payload=json.dumps(body_obj).encode('utf-8')
  req=urllib.request.Request(f'http://127.0.0.1:{port}/completion',data=payload,headers={'Content-Type':'application/json'},method='POST')
  answer='';last_loop_check=0
  try:
   resp=urllib.request.urlopen(req,timeout=300)
   self._active_http=resp
   try:
    for raw_line in resp:
     if self.cancelled.is_set():raise ProviderError('Respuesta detenida por el usuario.')
     line=raw_line.decode('utf-8','replace').strip()
     if not line.startswith('data:'):continue
     body=line[5:].strip()
     if not body or body=='[DONE]':break
     try:chunk=json.loads(body)
     except ValueError:continue
     text=str(chunk.get('content') or '')
     if harmony_filter and text:text=harmony_filter.feed(text)
     if text:
      if self.first_text is None and text.strip():self.first_text=time.monotonic()-start
      answer+=text;callback(text)
      if len(answer)-last_loop_check>=64:
       last_loop_check=len(answer)
       if _has_repetition_loop(answer):
        raise _RepetitionLoopError('Bucle repetitivo detectado en servidor local.')
     if chunk.get('stop'):break
   finally:
    self._active_http=None
    try:resp.close()
    except Exception:pass
  except _RepetitionLoopError:
   if not anti_repeat and not self.cancelled.is_set():
    return self._generate_server(prompt,budget,settings,use_cache,callback,engine,effective,gpu_args,harmony_filter,stop_tokens,anti_repeat=True)
   raise ProviderError('Se detectó un bucle de repetición en el modelo local y se detuvo automáticamente. Prueba con Razonamiento · Equilibrado o reformula la tarea.')
  except (urllib.error.URLError,http.client.HTTPException,AttributeError,OSError,ValueError) as exc:
   if self.cancelled.is_set():raise ProviderError('Respuesta detenida por el usuario.')
   self.close()
   raise ProviderError(f'Error de conexión con servidor local: {exc}') from exc
  if self.cancelled.is_set():raise ProviderError('Respuesta detenida por el usuario.')
  if harmony_filter:
   tail=harmony_filter.finish()
   if tail:answer+=tail;callback(tail)
  answer=answer.replace('[end of text]','').strip()
  if not answer:raise ProviderError('El modelo no produjo texto.')
  return answer,time.monotonic()-start
 def generate(self,settings,messages,callback,use_cache=True):
  with self.lock:
   from .acceleration import backend
   from .model_library import model_info,limits
   try:
    info=model_info(self.model);settings=limits(self.model,settings);layers=info.get(str(info.get('general.architecture','qwen2'))+'.block_count',0);size=self.model.stat().st_size
   except (OSError,ValueError,AttributeError):layers=0;size=0
   engine,gpu_args,self.backend_note=backend(self.runtime,self.data,self.acceleration,size,layers)
   try:return self._generate(settings,messages,callback,use_cache,engine,gpu_args)
   except (ProviderError,OSError) as error:
    if self.cancelled.is_set() or self.first_text is not None:raise
    if gpu_args:
     self.backend_note='GPU no disponible; continuando por CPU'
     return self._generate(settings,messages,callback,False,self.runtime/'motor',[])
    if use_cache and isinstance(error,ProviderError) and any(message in str(error) for message in ('El motor terminó con error','El modelo no produjo texto')):
     self.backend_note+=' · recuperación sin caché'
     return self._generate(settings,messages,callback,False,engine,[])
    raise
 def _generate(self,settings,messages,callback,use_cache,engine=None,gpu_args=None):
  engine=engine or self.runtime/"motor";gpu_args=gpu_args or []
  self.cancelled.clear();self.first_text=None
  if not self.model.is_file():raise ProviderError('No se encontró el modelo GGUF.')
  from .model_library import model_info,context_profile
  from .harmony_transport import prompt as harmony_prompt,HarmonyOutput
  info=model_info(self.model)
  arch=str(info.get("general.architecture") or "")
  gname=str(info.get("general.name") or "").lower()
  harmony=arch=="gpt-oss"
  if arch=="llama" and "mateo-nano" in gname:
   prompt=''.join(f"[{str(x['role']).upper()}]\n{str(x.get('content','')).replace(chr(13),'')}\n" for x in messages if x.get('role') in ('user','assistant'))+'[ASSISTANT]\n'
   stop_tokens=('[USER]','</s>')
  else:
   prompt=''.join('<|im_start|>'+str(x['role'])+'\n'+str(x.get('content','')).replace('\r','')+'<|im_end|>\n' for x in messages)+'<|im_start|>assistant\n'
   stop_tokens=('<|im_end|>','<|endoftext|>')
  if harmony:prompt=harmony_prompt(messages,settings.thinking_effort)
  budget=settings.max_predict_tokens or {'rapido':256,'equilibrado':512,'profundo':2048,'maximo':4096}[settings.thinking_effort]
  effective=settings.num_ctx
  profile=context_profile(self.model)
  automatic=min(profile['maximum'],16384) if settings.thinking_effort=='maximo' else profile['automatic']
  if self.auto_context and settings.thinking_effort=='maximo' and effective<automatic:effective=automatic
  elif self.auto_context and len(prompt)//2+128+min(budget,512)>effective and effective<automatic:effective=automatic
  self.effective_context=effective
  if len(prompt)//2+96>=effective:raise ProviderError('Este texto supera el contexto disponible ('+str(effective)+' tokens). Conservé el historial: divide la especificación o usa un archivo con las partes necesarias. Puedes ajustar la barra de contexto; no es una cuota de uso.')
  budget=min(budget,max(32,effective-len(prompt)//2-64))
  harmony_filter=HarmonyOutput() if harmony else None
  if self.use_persistent_server and (engine/'llama-server.exe').is_file() and not harmony:
   try:
    if arch=='gemma4':
     from .model_library import find_paired_multimodal_files
     paired=find_paired_multimodal_files(self.model)
     media_paths=list(getattr(self,'pending_media_paths',()) or ())
     self.pending_media_paths=[]
     res=self._generate_server_chat(messages,budget,settings,callback,engine,effective,gpu_args,paired.get('mmproj'),paired.get('mtp'),media_paths=media_paths)
     tag=' · Zamara V8.2 Multimodal nativo' + (' + MTP' if paired.get('mtp') else '')
     if tag not in self.backend_note:
      self.backend_note+=tag
     return res
    res=self._generate_server(prompt,budget,settings,use_cache,callback,engine,effective,gpu_args,harmony_filter,stop_tokens)
    if 'servidor rápido' not in self.backend_note:
     self.backend_note+=' · servidor rápido KV-RAM'
    return res
   except ProviderError:
    if self.cancelled.is_set() or self.first_text is not None:raise
    self.close()
  path=self.data/'turno.txt';path.write_bytes(prompt.encode('utf-8'));log=(self.data/'motor-nativo.log').open('a',encoding='utf-8');start=time.monotonic();answer=''
  batch=str(max(64,min(256,max(int(settings.num_batch),128))))
  args=[str(engine/'llama-completion.exe'),'-m',str(self.model),'-c',str(effective),'-t',str(settings.num_thread),'-tb',str(settings.num_thread),'-b',batch,'-ub',batch,'-fa','on','-ctk','q8_0','-ctv','q8_0','-ngl','0','--no-warmup','-no-cnv','--simple-io','--no-display-prompt','--color','off','--no-perf','--temp',str(settings.temperature),'-n',str(budget),'--no-escape','-bf',str(path)]
  if harmony:args.append("--special")
  if gpu_args:
   args[args.index('-ngl')+1]=gpu_args[-1];args+=gpu_args[:2]
  cache_dir=self.data/'cache';cache_dir.mkdir(exist_ok=True);engine_signature=';'.join(f.name+':'+str(f.stat().st_mtime_ns)+':'+str(f.stat().st_size) for f in sorted(engine.glob('*.dll')));cache_key=hashlib.sha256(('native-prompt-v3|'+str(engine)+str(gpu_args)+engine_signature+str(self.model.resolve())+str(self.model.stat().st_mtime_ns)+str(effective)).encode()).hexdigest()[:20];cache=cache_dir/(cache_key+'.bin')
  if use_cache:args+=['--prompt-cache',str(cache),'--prompt-cache-all']
  decoder=codecs.getincrementaldecoder('utf-8')('replace');output_filter=NativeOutputFilter();harmony_filter=HarmonyOutput() if harmony else None
  try:
   self.process=subprocess.Popen(args,cwd=engine,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
   while True:
    b=self.process.stdout.read(1)
    if not b:break
    text=output_filter.feed(decoder.decode(b))
    if harmony_filter:text=harmony_filter.feed(text)
    if text:
     if self.first_text is None and text.strip():self.first_text=time.monotonic()-start
     answer+=text;callback(text)
   tail=output_filter.finish()
   if harmony_filter:tail=harmony_filter.feed(tail)
   if tail:answer+=tail;callback(tail)
   code=self.process.wait()
   if self.cancelled.is_set():raise ProviderError('Respuesta detenida por el usuario.')
   if code:
    if use_cache:cache.unlink(missing_ok=True)
    raise ProviderError('El motor terminó con error '+str(code)+'. Consulta motor-nativo.log.')
   if harmony_filter:
    tail=harmony_filter.finish()
    if tail:answer+=tail;callback(tail)
   answer=answer.replace('[end of text]','').strip()
   if not answer:
    if use_cache:cache.unlink(missing_ok=True)
    raise ProviderError('El modelo no produjo texto.')
   return answer,time.monotonic()-start
  finally:
   p=self.process
   if p is not None and p.poll() is None:
    p.terminate()
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:p.kill()
   self.process=None;log.close();path.unlink(missing_ok=True)
   if use_cache and self.cancelled.is_set():cache.unlink(missing_ok=True)
 async def stream_chat(self,settings,messages,tools,on_token=None):
  loop=asyncio.get_running_loop()
  def callback(text):
   if on_token:
    f=on_token(text)
    if asyncio.iscoroutine(f):asyncio.run_coroutine_threadsafe(f,loop).result()
  messages=_adapt_messages_for_xml(messages)
  text,elapsed=await asyncio.to_thread(self.generate,settings,messages,callback)
  clean,calls=parse_xml_tool_calls(text)
  return ProviderResponse(content=clean,raw_content=text,tool_calls=[ToolCall(uuid.uuid4().hex,x['name'],x['arguments']) for x in calls],elapsed_ms=int(elapsed*1000),used_tool_mode='xml')

class Dictation:
 def __init__(self,runtime):self.runtime=Path(runtime);self.stop_event=threading.Event();self._vosk_model=None
 def stop(self):self.stop_event.set()
 def _get_model(self):
  import vosk
  if self._vosk_model is None:
   vosk.SetLogLevel(-1)
   self._vosk_model=vosk.Model(str(self.runtime/'voz/vosk-model-small-es-0.42'))
  return self._vosk_model
 def listen(self,device=None):
  import vosk,sounddevice as sd,queue
  self.stop_event.clear();rec=vosk.KaldiRecognizer(self._get_model(),16000);chunks=queue.Queue(maxsize=80);parts=[]
  def receive(data,frames,timing,status):
   try:chunks.put_nowait(bytes(data))
   except queue.Full:pass
  with sd.RawInputStream(samplerate=16000,blocksize=4000,dtype='int16',channels=1,device=device,callback=receive):
   deadline=time.monotonic()+60
   while not self.stop_event.is_set() and time.monotonic()<deadline:
    try:data=chunks.get(timeout=.3)
    except queue.Empty:continue
    if rec.AcceptWaveform(data):parts.append(json.loads(rec.Result()).get('text',''))
  parts.append(json.loads(rec.FinalResult()).get('text',''));return ' '.join(x for x in parts if x).strip()
 def listen_turn(self,device=None,*,silence_sec=1.5,initial_wait=12.0,max_sec=28.0):
  """Escucha manos libres para conversación en vivo: detecta voz y cierra el turno tras pausa natural."""
  import vosk,sounddevice as sd,queue
  self.stop_event.clear();rec=vosk.KaldiRecognizer(self._get_model(),16000);chunks=queue.Queue(maxsize=80);parts=[]
  def receive(data,frames,timing,status):
   try:chunks.put_nowait(bytes(data))
   except queue.Full:pass
  heard_speech=False;started=time.monotonic();last_voice=started
  with sd.RawInputStream(samplerate=16000,blocksize=4000,dtype='int16',channels=1,device=device,callback=receive):
   while not self.stop_event.is_set():
    now=time.monotonic()
    if now-started>=max_sec:break
    if not heard_speech and now-started>=initial_wait:break
    if heard_speech and now-last_voice>=silence_sec:break
    try:data=chunks.get(timeout=.2)
    except queue.Empty:continue
    if rec.AcceptWaveform(data):
     txt=str(json.loads(rec.Result()).get('text') or '').strip()
     if txt:parts.append(txt);heard_speech=True;last_voice=time.monotonic()
    else:
     partial=str(json.loads(rec.PartialResult()).get('partial') or '').strip()
     if partial:heard_speech=True;last_voice=time.monotonic()
  tail=str(json.loads(rec.FinalResult()).get('text') or '').strip()
  if tail:parts.append(tail)
  return ' '.join(x for x in parts if x).strip()

def spoken_text(text):
 from .native_voice import naturalize_spoken_text
 return naturalize_spoken_text(text,max_chars=3600)


def conversation_prompt(settings):
 from .aura_api import effort_instruction
 return 'Eres AURA, asistente local en español. En Conversación no ejecutas comandos ni modificas archivos. '+effort_instruction(settings)
