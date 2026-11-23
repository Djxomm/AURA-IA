"""Bounded GGUF metadata inspection and explicit native model profiles."""
from pathlib import Path
import struct

SCALARS={0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}

def metadata(path):
    result={}
    with Path(path).open('rb') as stream:
        size=Path(path).stat().st_size
        def read(n):
            value=stream.read(n)
            if len(value)!=n:raise ValueError('GGUF truncado.')
            return value
        def number(fmt):return struct.unpack('<'+fmt,read(struct.calcsize(fmt)))[0]
        def string(keep=True):
            length=number('Q')
            if length>16*1024*1024 or stream.tell()+length>size:raise ValueError('Metadatos GGUF inválidos.')
            if keep:return read(length).decode('utf-8',errors='strict')
            stream.seek(length,1)
        def value(kind,keep=False):
            if kind==8:return string(keep)
            if kind==9:
                element,count=number('I'),number('Q')
                if count>2_000_000 or element==9:raise ValueError('Lista GGUF inválida.')
                if element in SCALARS:
                    length=struct.calcsize(SCALARS[element])*count
                    if stream.tell()+length>size:raise ValueError('GGUF truncado.')
                    stream.seek(length,1)
                else:
                    for _ in range(count):value(element,False)
                return None
            if kind not in SCALARS:raise ValueError('Tipo GGUF desconocido.')
            item=number(SCALARS[kind]);return item if keep else None
        if read(4)!=b'GGUF':raise ValueError('GGUF inválido.')
        if number('I') not in (2,3):raise ValueError('Versión GGUF no admitida.')
        number('Q');count=number('Q')
        if count>16384:raise ValueError('Demasiados metadatos GGUF.')
        for _ in range(count):
            key=string();kind=number('I')
            keep=key in {'general.architecture','general.name','tokenizer.chat_template'}
            item=value(kind,keep)
            if keep:result[key]=item
    return result


def profile(path):
    info=metadata(path);architecture=info.get('general.architecture','')
    if architecture=='gemma4':return 'nemotron',info
    if architecture in {'qwen2','qwen3'}:
        return ('qwen' if info.get('tokenizer.chat_template') or 'instruct' in Path(path).name.lower() else 'qwen_base'),info
    if architecture in {'llama','mistral','phi3','deepseek2','gpt-oss'}:
        return architecture,info
    raise ValueError('Arquitectura no admitida: '+architecture)
