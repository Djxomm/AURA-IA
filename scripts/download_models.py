"""Pinned GGUF library downloader: resumable, SHA-256 verified, never executes model code."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

LOCK=threading.RLock()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def download(url, target, size, sha, progress, pause=None):
    if target.is_file() and target.stat().st_size==size and digest(target)==sha:
        return
    target.parent.mkdir(parents=True,exist_ok=True)
    partial=target.with_suffix(target.suffix+'.part')
    for attempt in range(8):
        while pause is not None and pause.exists():time.sleep(1)
        offset=partial.stat().st_size if partial.exists() else 0
        try:
            headers={'User-Agent':'AURA-model-library/1.0'}
            if offset:headers['Range']=f'bytes={offset}-'
            request=urllib.request.Request(url+'?download=true&nonce='+str(time.time_ns()),headers=headers)
            with urllib.request.urlopen(request,timeout=60) as response:
                if offset and response.status!=206:offset=0
                if response.status==206 and not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
                    raise ValueError('El servidor devolvió un rango incorrecto.')
                sha_state=hashlib.sha256()
                if offset:
                    with partial.open('rb') as source:
                        while block:=source.read(16*1024**2):sha_state.update(block)
                count=offset;notice=time.monotonic()
                with partial.open('ab' if offset else 'wb') as output:
                    while block:=response.read(8*1024**2):
                        while pause is not None and pause.exists():time.sleep(1)
                        output.write(block);sha_state.update(block);count+=len(block)
                        if time.monotonic()-notice>5:
                            progress(count,size);notice=time.monotonic()
            if count<size:
                raise OSError(f'Conexión terminada antes de completar: {count} de {size} bytes; se conserva el avance.')
            if count!=size or sha_state.hexdigest()!=sha:
                actual=sha_state.hexdigest();partial.unlink(missing_ok=True)
                raise ValueError(f'SHA-256 o tamaño incorrecto: {count}/{size}; {actual} frente a {sha}.')
            partial.replace(target);progress(size,size);return
        except Exception as error:
            print('REINTENTO',target.name,attempt+1,type(error).__name__,str(error)[:160],flush=True)
            if attempt==7:raise
            time.sleep(min(20,2**attempt))


def run(args):
    root=Path(args.root).resolve();root.mkdir(parents=True,exist_ok=True)
    try:previous={m['filename']:m for m in json.loads((root/'catalog.json').read_text('utf-8')).get('models',[])}
    except (OSError,ValueError,KeyError):previous={}
    entries=json.loads(Path(args.manifest).read_text('utf-8'))
    records=[]
    for entry in entries:
        if entry.get('error'):continue
        single=[f for f in entry['files'] if '-of-' not in f['name']]
        files=single[:1] or sorted(entry['files'],key=lambda f:f['name'])
        if not files:continue
        name=files[0]['name'].split('-00001-of-')[0]+'.gguf' if not single else files[0]['name']
        records.append({'repo':entry['repo'],'revision':entry['revision'],'filename':name,'sources':files,'status':'pending','bytes_total':sum(f['size'] for f in files),'bytes_received':0})
    def save():
        with LOCK:
            temp=root/'catalog.json.tmp';temp.write_text(json.dumps({'format':1,'updated':time.time(),'models':records},ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(root/'catalog.json')
    save()
    def worker(record):
        target=root/record['filename'];record['status']='checking';save()
        try:
            prior=previous.get(record['filename'],{})
            if prior.get('status')=='ready' and prior.get('sources')==record['sources'] and target.is_file() and target.stat().st_size==prior.get('size') and digest(target)==prior.get('sha256'):
                record.update({key:prior[key] for key in ('sha256','size','path')});record['status']='ready';record['bytes_received']=record['bytes_total'];save();print('VERIFICADO',target.name,flush=True);return
            # Reuse already verified local models without duplicating gigabytes.
            local=Path(args.existing)/record['filename']
            if len(record['sources'])==1 and not target.exists() and local.is_file():
                source=record['sources'][0]
                if local.stat().st_size==source['size'] and digest(local)==source['sha256']:
                    os.link(local,target)
            parts=[];done=0
            record['status']='downloading';save()
            for source in record['sources']:
                part=target if len(record['sources'])==1 else root/'.downloads'/record['repo'].split('/')[-1]/source['name']
                def progress(count,size):
                    record['bytes_received']=done+count;save()
                url='https://huggingface.co/'+record['repo']+'/resolve/'+record['revision']+'/'+source['name']
                download(url,part,source['size'],source['sha256'],progress,root/'PAUSA')
                done+=source['size'];parts.append(part)
            if len(parts)>1:
                record['status']='merging';save()
                merged=target.with_suffix('.merging.gguf')
                merged.unlink(missing_ok=True)
                log=root/(target.stem+'.merge.log')
                with log.open('w',encoding='utf-8') as output:
                    result=subprocess.run([str(Path(args.merge).resolve()),'--merge',str(parts[0]),str(merged)],stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode:raise RuntimeError('Falló la unión; se conservaron las partes verificadas.')
                with merged.open('rb') as stream:
                    if stream.read(4)!=b'GGUF':raise ValueError('La unión no produjo un GGUF válido.')
                merged.replace(target)
            record['status']='verifying';save();record['sha256']=digest(target);record['size']=target.stat().st_size
            record['path']=str(target);record['status']='ready';record['bytes_received']=record['bytes_total'];save()
            if len(parts)>1:
                # Only temporary shards created by this download, after successful merge.
                for part in parts:
                    if part.resolve().is_relative_to((root/'.downloads').resolve()):part.unlink()
            print('LISTO',target.name,flush=True)
        except Exception as error:
            record['status']='error';record['error']=str(error);save();print('ERROR',record['repo'],str(error),flush=True)
    print('BIBLIOTECA',len(records),'modelos',round(sum(r['bytes_total'] for r in records)/1e9,1),'GB',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(worker,sorted(records,key=lambda x:x['bytes_total'])))
    save()
    if any(record['status']!='ready' for record in records):raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True);parser.add_argument('--manifest',required=True)
    parser.add_argument('--existing',required=True);parser.add_argument('--merge',required=True)
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    Path(args.root).mkdir(parents=True,exist_ok=True)
    with (Path(args.root)/'.download.lock').open('a+b') as lock:
        if os.name=='nt':
            import msvcrt
            if lock.seek(0,2)==0:lock.write(b'0');lock.flush()
            lock.seek(0)
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise SystemExit('Ya existe una descarga activa para esta biblioteca.')
        run(args)
