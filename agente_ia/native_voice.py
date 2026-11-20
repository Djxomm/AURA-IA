"""ElevenLabs optional speech; secrets encrypted for the current Windows user."""
import ctypes,json,os,re,urllib.request
from ctypes import wintypes
from pathlib import Path
class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
def protect(data,decrypt=False):
 if os.name!='nt':raise RuntimeError('La clave protegida requiere Windows.')
 buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));out=Blob();api=ctypes.windll.crypt32;kernel=ctypes.windll.kernel32
 if decrypt:ok=api.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(out))
 else:ok=api.CryptProtectData(ctypes.byref(source),'AURA ElevenLabs',None,None,None,1,ctypes.byref(out))
 if not ok:raise ctypes.WinError()
 try:return ctypes.string_at(out.data,out.size)
 finally:kernel.LocalFree(out.data)
class VoiceKey:
 def __init__(self,data):self.path=Path(data)/'elevenlabs.dpapi'
 def save(self,key):
  if not key.strip():return
  encrypted=protect(key.strip().encode());temporary=self.path.with_suffix('.tmp');temporary.write_bytes(encrypted);temporary.replace(self.path)
 def get(self):return protect(self.path.read_bytes(),True).decode() if self.path.exists() else ''
 def delete(self):self.path.unlink(missing_ok=True)
def voices(key):
 if not key:raise ValueError('Introduce la clave de ElevenLabs dentro de AURA.')
 req=urllib.request.Request('https://api.elevenlabs.io/v2/voices?search=Kate&page_size=100',headers={'xi-api-key':key})
 with urllib.request.urlopen(req,timeout=20) as response:return json.load(response).get('voices',[])
def synthesize(text,voice_id,key,path):
 if not re.fullmatch(r'[A-Za-z0-9_-]{5,100}',voice_id):raise ValueError('Selecciona o introduce el identificador de la voz Kate.')
 if not key:raise ValueError('Falta configurar la clave de ElevenLabs.')
 body=json.dumps({'text':text,'model_id':'eleven_multilingual_v2','voice_settings':{'stability':0.5,'similarity_boost':0.75}}).encode()
 req=urllib.request.Request('https://api.elevenlabs.io/v1/text-to-speech/'+voice_id+'?output_format=mp3_44100_128',data=body,headers={'xi-api-key':key,'Content-Type':'application/json','Accept':'audio/mpeg'})
 with urllib.request.urlopen(req,timeout=60) as response:
  audio=response.read(20_000_001)
  if len(audio)>20_000_000:raise ValueError('El audio supera el tamaño permitido.')
  if not audio:raise ValueError('ElevenLabs no devolvió audio.')
 Path(path).write_bytes(audio);return Path(path)
