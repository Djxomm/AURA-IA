"""Native-only inference, explicit local memory and offline dictation."""
from __future__ import annotations
import asyncio, codecs, hashlib, json, os, re, sqlite3, subprocess, threading, time, uuid
from pathlib import Path
from .providers import ProviderResponse, ProviderError, ToolCall, _adapt_messages_for_xml
from .tools import parse_xml_tool_calls

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
  self.model=Path(model or self.runtime/'modelos/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf');self.process=None;self.cancelled=threading.Event();self.first_text=None;self.lock=threading.Lock();self.auto_context=True;self.effective_context=None
 def stop(self):
  self.cancelled.set();p=self.process
  if p is not None and p.poll() is None:
   p.terminate()
 def generate(self,settings,messages,callback,use_cache=True):
  with self.lock:return self._generate(settings,messages,callback,use_cache)
 def _generate(self,settings,messages,callback,use_cache):
  self.cancelled.clear();self.first_text=None
  if not self.model.is_file():raise ProviderError('No se encontró el modelo GGUF.')
  # This lightweight transport supports the Qwen ChatML family explicitly.
  prompt=''.join('<|im_start|>'+str(x['role'])+'\n'+str(x.get('content','')).replace('\r','')+'<|im_end|>\n' for x in messages)+'<|im_start|>assistant\n'
  budget=settings.max_predict_tokens or {'rapido':256,'equilibrado':512,'profundo':1024}[settings.thinking_effort]
  effective=settings.num_ctx
  if self.auto_context and len(prompt)//2+128+min(budget,512)>effective and effective<8192:effective=8192
  self.effective_context=effective
  if len(prompt)//2+96>=effective:raise ProviderError('Este texto supera el contexto disponible ('+str(effective)+' tokens). Conservé el historial: divide la especificación o usa un archivo con las partes necesarias. Puedes ajustar la barra de contexto; no es una cuota de uso.')
  budget=min(budget,max(32,effective-len(prompt)//2-64))
  path=self.data/'turno.txt';path.write_text(prompt,'utf-8');log=(self.data/'motor-nativo.log').open('a',encoding='utf-8');start=time.monotonic();answer=''
  args=[str(self.runtime/'motor/llama-completion.exe'),'-m',str(self.model),'-c',str(effective),'-t',str(settings.num_thread),'-tb',str(settings.num_thread),'-b','128','-ub','128','-ngl','0','--poll','0','--no-warmup','-no-cnv','--simple-io','--no-display-prompt','--color','off','--no-perf','--temp',str(settings.temperature),'-n',str(budget),'-f',str(path)]
  cache_dir=self.data/'cache';cache_dir.mkdir(exist_ok=True);cache_key=hashlib.sha256((str(self.model.resolve())+str(self.model.stat().st_mtime_ns)+str(effective)).encode()).hexdigest()[:20];cache=cache_dir/(cache_key+'.bin')
  if use_cache:args+=['--prompt-cache',str(cache),'--prompt-cache-all']
  decoder=codecs.getincrementaldecoder('utf-8')('replace');output_filter=NativeOutputFilter()
  try:
   self.process=subprocess.Popen(args,cwd=self.runtime/'motor',stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
   while True:
    b=self.process.stdout.read(1)
    if not b:break
    text=output_filter.feed(decoder.decode(b))
    if text:
     if self.first_text is None and text.strip():self.first_text=time.monotonic()-start
     answer+=text;callback(text)
   tail=output_filter.finish()
   if tail:answer+=tail;callback(tail)
   code=self.process.wait()
   if self.cancelled.is_set():raise ProviderError('Respuesta detenida por el usuario.')
   if code:raise ProviderError('El motor terminó con error '+str(code)+'. Consulta motor-nativo.log.')
   answer=answer.replace('[end of text]','').strip()
   if not answer:raise ProviderError('El modelo no produjo texto.')
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
 def __init__(self,runtime):self.runtime=Path(runtime);self.stop_event=threading.Event()
 def stop(self):self.stop_event.set()
 def listen(self,device=None):
  import vosk,sounddevice as sd,queue
  self.stop_event.clear();vosk.SetLogLevel(-1);model=vosk.Model(str(self.runtime/'voz/vosk-model-small-es-0.42'));rec=vosk.KaldiRecognizer(model,16000);chunks=queue.Queue(maxsize=80);parts=[]
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

def spoken_text(text):
 text=re.sub(r'```.*?```','Bloque de código disponible en pantalla.',text,flags=re.S)
 return re.sub(r'[*#`]','',text)[:6000]


def conversation_prompt(settings):
 effort={'rapido':'Sé breve y directo.','equilibrado':'Responde con claridad.','profundo':'Revisa con cuidado y explica las decisiones.'}[settings.thinking_effort]
 return 'Eres AURA, asistente local en español. En Conversación no ejecutas comandos ni modificas archivos. '+effort
