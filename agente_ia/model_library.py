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


def limits(path,settings):
    """Cap working context/batch for large models; never load a model to inspect it."""
    size=Path(path).stat().st_size/1024**3
    update={}
    if size>30:update={'num_ctx':min(settings.num_ctx,1024),'num_batch':16}
    elif size>14:update={'num_ctx':min(settings.num_ctx,2048),'num_batch':32}
    elif size>7:update={'num_ctx':min(settings.num_ctx,4096),'num_batch':32}
    return settings.model_copy(update=update)
