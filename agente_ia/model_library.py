"""Discover verified local weights and select conservative per-model resource limits."""
import functools
import json
from pathlib import Path
import struct


@functools.lru_cache(maxsize=64)
def _info(path,size,modified):
    result={};formats={0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
    with Path(path).open('rb') as stream:
        def read(n):
            data=stream.read(n)
            if len(data)!=n:raise ValueError('GGUF incompleto.')
            return data
        def number(kind):return struct.unpack('<'+kind,read(struct.calcsize(kind)))[0]
        def string():
            length=number('Q')
            if length>1024*1024 or stream.tell()+length>size:raise ValueError('Cabecera GGUF inválida.')
            return read(length).decode('utf-8')
        if read(4)!=b'GGUF' or number('I') not in (2,3):raise ValueError('GGUF inválido.')
        result['tensors']=number('Q');count=number('Q')
        if count>16384:raise ValueError('Cabecera GGUF demasiado grande.')
        for _ in range(count):
            key=string();kind=number('I')
            # Architecture and layer count precede the large tokenizer tables.
            if key.startswith('tokenizer.') and 'qwen2.block_count' in result:break
            if kind in formats:value=number(formats[kind])
            elif kind==8:value=string()
            else:break
            result[key]=value
    return result


def model_info(path):
    path=Path(path).resolve();stat=path.stat()
    return dict(_info(str(path),stat.st_size,stat.st_mtime_ns))


def discover(directories):
    result=[]
    for directory in directories:
        root=Path(directory).resolve()
        try:catalog=json.loads((root/'catalog.json').read_text('utf-8'))
        except (OSError,ValueError):continue
        for record in catalog.get('models',[]):
            if not isinstance(record,dict) or record.get('status')!='ready':continue
            path=(root/record.get('filename','')).resolve()
            if path.is_relative_to(root) and path.is_file() and path.stat().st_size==record.get('size'):
                result.append(path)
    return result


def context_profile(path,hardware=None):
    """Conservative recommendations, with a separate explicit experimental ceiling."""
    from .hardware_profile import hardware_info
    hardware=hardware if hardware is not None else hardware_info()
    ram=hardware.get('ram_gib') or 8
    try:size=Path(path).stat().st_size/1024**3;info=model_info(path)
    except (OSError,ValueError):size=0;info={}
    architecture=info.get('general.architecture','qwen2')
    trained=info.get(architecture+'.context_length',32768)
    if not isinstance(trained,int) or trained<512:trained=32768
    maximum=32768 if ram>=15 else 8192
    recommended=4096 if ram>=15 and hardware.get('cores',2)>2 else 2048
    automatic=8192 if ram>=15 and size<7 else recommended
    if size>30:recommended=1024;maximum=2048 if ram>=64 else 1024;automatic=recommended
    elif size>14:recommended=2048;maximum=16384 if ram>=48 else 4096;automatic=recommended
    elif size>7:
        recommended=4096 if ram>=15 else 2048
        maximum=32768 if ram>=32 else 16384 if ram>=15 else 4096
        automatic=recommended
    maximum=max(512,min(maximum,trained,32768))
    return {'recommended':min(recommended,maximum),'maximum':maximum,'automatic':min(automatic,maximum)}


def limits(path,settings,hardware=None):
    """Honor manual context within the displayed model/RAM ceiling."""
    profile=context_profile(path,hardware);size=Path(path).stat().st_size/1024**3
    update={'num_ctx':min(settings.num_ctx,profile['maximum'])}
    if size>30:update['num_batch']=16
    elif size>7:update['num_batch']=32
    return settings.model_copy(update=update)


def programming_settings(settings,enabled=True):
    return settings.model_copy(update={'temperature':min(settings.temperature,.2)}) if enabled else settings


def model_skill_profile(path):
    """Clasifica un modelo GGUF por habilidades verificadas y descarta modelos lentos en CPU."""
    p=Path(path);low=p.stem.lower()
    gname=''
    if p.suffix.lower()=='.gguf' and p.is_file():
        try:gname=str(model_info(p).get('general.name') or '').strip().lower()
        except (OSError,ValueError):gname=''
    combined=f'{low} {gname}'
    if 'aura-angel-5.6' in low or 'angel 5.6' in combined:
        return {'proven':True,'tier':0,'rank':0,'canonical':'aura-angel-5.6','category':'★ Construcción, Razonamiento y Full-Stack','skills':'Constructor autónomo · razonamiento · Full-Stack'}
    if 'aura-lumen-2.0ib_v2' in low or 'lumen 2.0ib_v2' in combined:
        return {'proven':True,'tier':0,'rank':1,'canonical':'aura-lumen-2.0ib_v2','category':'★ Construcción, Razonamiento y Full-Stack','skills':'Código · UI/WCAG · FastAPI · herramientas AURA'}
    if 'aura-lumen-2.0ib_v1' in low or 'lumen 2.0ib_v1' in combined:
        return {'proven':True,'tier':1,'rank':0,'canonical':'aura-lumen-2.0ib_v1','category':'⚙ Edición de Código y Herramientas AURA','skills':'Edición Python · herramientas AURA'}
    if 'qwen2.5-coder-3b-instruct' in low:
        return {'proven':True,'tier':1,'rank':1,'canonical':'qwen2.5-coder-3b','category':'⚙ Edición de Código y Herramientas AURA','skills':'Programación general · refactorización equilibrada'}
    if 'qwen2.5-coder-1.5b-instruct' in low:
        return {'proven':True,'tier':2,'rank':0,'canonical':'qwen2.5-coder-1.5b','category':'⚡ Respuesta Rápida y Consultas','skills':'Consultas rápidas · edición ligera'}
    # Modelos pesados/lentos en CPU o variantes no probadas quedan marcados como proven=False
    if any(tok in combined for tok in ('gpt-oss','72b','32b','20b','14b','7b')):
        return {'proven':False,'tier':3,'rank':9,'canonical':low,'category':'Modelos pesados · lentos en CPU','skills':'Alto consumo de RAM y respuesta lenta'}
    return {'proven':False,'tier':3,'rank':8,'canonical':low,'category':'Otros modelos locales','skills':'Sin verificación de velocidad'}


def curate_proven_models(paths,*,current=None,extra_runs_dirs=()):
    """Conserva únicamente modelos probados y rápidos, deduplicados y ordenados por habilidad."""
    candidates=[]
    for run_root in extra_runs_dirs:
        root=Path(run_root)
        if not root.is_dir():continue
        for pat in ('AURA-ANGEL-5.6*.gguf','AURA-Lumen-2.0IB_V2*.gguf','AURA-Lumen-2.0IB_V1*.gguf'):
            candidates.extend(sorted(root.rglob(pat),key=lambda x:x.stat().st_mtime,reverse=True))
    candidates.extend(Path(p) for p in paths)
    cur_resolved=None
    if current is not None:
        cp=Path(current)
        if cp.is_file():cur_resolved=cp.resolve()
    by_canonical={}
    for raw in candidates:
        p=Path(raw)
        if not p.is_file() or p.suffix.lower()!='.gguf':continue
        rp=p.resolve()
        prof=model_skill_profile(rp)
        is_current=(cur_resolved is not None and rp==cur_resolved)
        if not prof['proven'] and not is_current:continue
        key=prof['canonical']
        prev=by_canonical.get(key)
        if prev is None or is_current:
            by_canonical[key]=(prof['tier'],prof['rank'],rp)
    ordered=sorted(by_canonical.values(),key=lambda item:(item[0],item[1],item[2].name.lower()))
    return [item[2] for item in ordered]
