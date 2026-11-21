import ctypes,json,sqlite3
from pathlib import Path
import pytest
from agente_ia.native_core import Memory,spoken_text
from agente_ia.native_voice import VoiceKey

def test_memory_reopen_scope_edit_forget(tmp_path):
 p=tmp_path/'memory.db';m=Memory(p);a=m.save('Usar tema azul en el almacén','almacen');m.save('Preferir español');m.save('Usar tema rojo','otro');m.close();m=Memory(p)
 assert [x['id'] for x in m.search('azul','almacen')]==[a]
 assert not m.search('rojo','almacen')
 m.save('Usar tema verde','almacen',ident=a);assert not m.search('azul','almacen');assert m.search('verde','almacen');m.delete(a);assert not m.search('verde','almacen');m.close()

def test_memory_does_not_store_credentials(tmp_path):
 m=Memory(tmp_path/'m.db')
 with pytest.raises(ValueError):m.save('password=secreto')
 assert not m.list();m.close()

def test_windows_key_roundtrip(tmp_path):
 v=VoiceKey(tmp_path);v.save('solo-prueba-no-es-una-clave-real');assert b'solo-prueba' not in v.path.read_bytes();assert v.get()=='solo-prueba-no-es-una-clave-real';v.delete();assert v.get()==''

def test_spoken_text_omits_code():
 assert 'print(' not in spoken_text('Hola\n```python\nprint(1)\n```')

def test_native_entry_has_no_server_or_browser():
 s=(Path(__file__).parents[1]/'native_launcher.py').read_text('utf-8');assert 'webbrowser' not in s;assert 'uvicorn' not in s;assert 'QWebEngine' not in s


def test_native_filter_hides_cache_diagnostics():
 from agente_ia.native_core import NativeOutputFilter
 f=NativeOutputFilter();text='Hola, puedo ayudarte.\n\nllama_completion: saving final output to session file secret.bin\n';out=''.join(f.feed(x) for x in text)+f.finish();assert 'Hola, puedo ayudarte.' in out;assert 'secret.bin' not in out;assert 'llama_completion' not in out


def test_native_context_auto_expands_and_manual_limit_is_respected(tmp_path,monkeypatch):
 import io
 from agente_ia.native_core import NativeClient
 from agente_ia.config import AppSettings
 from agente_ia.providers import ProviderError
 model=tmp_path/'qwen.gguf';model.write_bytes(b'GGUF');calls=[]
 class Process:
  def __init__(self,args,**kwargs):calls.append(args);self.stdout=io.BytesIO(b'Listo')
  def poll(self):return 0
  def wait(self,**kwargs):return 0
 monkeypatch.setattr('agente_ia.native_core.subprocess.Popen',Process)
 c=NativeClient(tmp_path,tmp_path/'state',model);s=AppSettings(num_ctx=4096,max_predict_tokens=128)
 messages=[{'role':'user','content':'a'*10000}]
 assert c.generate(s,messages,lambda x:None)[0]=='Listo'
 assert calls[0][calls[0].index('-c')+1]=='8192'
 c.auto_context=False
 with pytest.raises(ProviderError):c.generate(s,messages,lambda x:None)

def test_native_tool_history_is_adapted(tmp_path):
 import asyncio
 from agente_ia.native_core import NativeClient
 from agente_ia.config import AppSettings
 c=NativeClient(tmp_path,tmp_path/'state');captured=[]
 def fake(settings,messages,callback):captured.extend(messages);return 'Listo',.1
 c.generate=fake
 messages=[{'role':'system','content':'Ayuda con programación.'},{'role':'assistant','content':'','tool_calls':[{'function':{'name':'read_file','arguments':{'path':'app.py'}}}]},{'role':'tool','name':'read_file','content':'print(1)'}]
 asyncio.run(c.stream_chat(AppSettings(),messages,[],None))
 assert '<tool_call>' in captured[1]['content']
 assert captured[2]['role']=='user' and 'print(1)' in captured[2]['content']

def test_native_prompt_bytes_preserve_generation_prefix_and_literal_code(tmp_path,monkeypatch):
 import io
 from agente_ia.native_core import NativeClient
 from agente_ia.config import AppSettings
 model=tmp_path/'qwen.gguf';model.write_bytes(b'GGUF');seen=[]
 class Process:
  def __init__(self,args,**kwargs):
   assert '-bf' in args and '--no-escape' in args and '-f' not in args
   assert __import__('pathlib').Path(args[args.index('-m')+1]).is_absolute()
   seen.append(__import__('pathlib').Path(args[args.index('-bf')+1]).read_bytes())
   self.stdout=io.BytesIO(b'Listo')
  def poll(self):return 0
  def wait(self,**kwargs):return 0
 monkeypatch.setattr('agente_ia.native_core.subprocess.Popen',Process)
 c=NativeClient(tmp_path,tmp_path/'state',model)
 c.generate(AppSettings(),[{'role':'user','content':r"print('a\nb')"}],lambda x:None)
 assert seen[0].endswith(b'<|im_start|>assistant\n')
 assert b'\r' not in seen[0]
 assert br"print('a\nb')" in seen[0]


def test_native_cache_changes_when_cpu_engine_changes(tmp_path,monkeypatch):
 import io
 from agente_ia.native_core import NativeClient
 from agente_ia.config import AppSettings
 model=tmp_path/'qwen.gguf';model.write_bytes(b'GGUF');(tmp_path/'motor').mkdir();seen=[]
 class Process:
  def __init__(self,args,**kwargs):seen.append(args[args.index('--prompt-cache')+1]);self.stdout=io.BytesIO(b'Listo')
  def poll(self):return 0
  def wait(self,**kwargs):return 0
 monkeypatch.setattr('agente_ia.native_core.subprocess.Popen',Process)
 c=NativeClient(tmp_path,tmp_path/'state',model)
 for changed in [False,True]:
  if changed:(tmp_path/'motor/ggml-cpu-haswell.dll').write_bytes(b'new-engine')
  c.generate(AppSettings(),[{'role':'user','content':'Hola'}],lambda x:None)
 assert seen[0]!=seen[1]
