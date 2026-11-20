"""Prepare AURA's CPU runtime from public, pinned upstream artifacts."""
import argparse,hashlib,json,shutil,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def download(url,target,digest):
 target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():
  with target.open('rb') as stream:
   if hashlib.file_digest(stream,'sha256').hexdigest()==digest:return target
 partial=target.with_suffix(target.suffix+'.part');sha=hashlib.sha256();count=0;next_notice=0
 print('Descargando',target.name,flush=True)
 req=urllib.request.Request(url,headers={'User-Agent':'AURA-runtime/3.0'})
 with urllib.request.urlopen(req,timeout=60) as response,partial.open('wb') as output:
  while block:=response.read(4*1024*1024):
   output.write(block);sha.update(block);count+=len(block)
   if count>=next_notice:print(f'  {count/1024**2:.0f} MiB',flush=True);next_notice=count+50*1024**2
 if sha.hexdigest()!=digest:
  partial.unlink(missing_ok=True);raise RuntimeError('La descarga no coincide con SHA-256: '+target.name)
 partial.replace(target);return target

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.parse_args();manifest=json.loads((ROOT/'runtime-manifest.json').read_text('utf-8'));runtime=ROOT/'runtime';downloads=ROOT/'build/downloads'
 model=manifest['model'];download(model['url'],runtime/'modelos/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf',model['sha256'])
 engine=manifest['engine'];archive=download(engine['url'],downloads/'llama-cpu.zip',engine['sha256']);allowed={'llama-completion.exe','llama-completion-impl.dll','llama-common.dll','llama.dll','ggml.dll','ggml-base.dll','ggml-cpu-sse42.dll','ggml-cpu-x64.dll','ggml-rpc.dll','libomp.dll'};motor=runtime/'motor';motor.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(archive) as package:
  for entry in package.infolist():
   name=Path(entry.filename).name
   if name in allowed:
    with package.open(entry) as source,(motor/name).open('wb') as output:shutil.copyfileobj(source,output)
 if not (motor/'llama-completion.exe').exists():raise RuntimeError('Falta llama-completion.exe en el paquete oficial.')
 speech=manifest['vosk'];archive=download(speech['url'],downloads/'vosk-es.zip',speech['sha256']);voice=runtime/'voz';voice.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(archive) as package:
  for entry in package.infolist():
   path=(voice/entry.filename).resolve()
   if not path.is_relative_to(voice.resolve()):raise RuntimeError('Ruta de archivo ZIP inválida.')
  package.extractall(voice)
 shutil.copytree(ROOT/'licenses',runtime/'licencias',dirs_exist_ok=True)
 print('Runtime listo. Ejecuta: python native_launcher.py',flush=True)
if __name__=='__main__':main()
