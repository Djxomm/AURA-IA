"""Read-only PE inspection. This does not execute or decompile the target."""
import hashlib
from pathlib import Path
import re
import pefile

def inspect_binary(workspace, relative):
    path=workspace.resolve_safe_path(relative,allow_write=False)
    if not path.is_file() or path.stat().st_size>128*1024*1024:
        raise ValueError('Selecciona un archivo de hasta 128 MB dentro del proyecto.')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        sample=stream.read(1024*1024);digest.update(sample)
        while block:=stream.read(1024*1024): digest.update(block)
    data=sample
    result={'file':str(relative),'size':path.stat().st_size,'sha256':digest.hexdigest(),'executed':False,'strings_coverage':'Primer MiB, hasta 25 cadenas'}
    strings=[]
    for match in re.finditer(rb'[ -~]{6,160}',data):
        strings.append(match.group().decode('ascii'))
        if len(strings)>=25: break
    result['strings_sample']=strings
    if data[:2] != b'MZ':
        result['format']='No es un ejecutable PE de Windows';return result
    try: pe=pefile.PE(str(path),fast_load=True)
    except pefile.PEFormatError as exc: raise ValueError("Archivo PE inválido: "+str(exc)) from exc
    try:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
        result['format']='PE';result['machine']=hex(pe.FILE_HEADER.Machine)
        result['entry_point_rva']=hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint)
        result['sections']=[{'name':s.Name.rstrip(b'\0').decode('ascii',errors='replace'),'bytes':s.SizeOfRawData} for s in pe.sections[:20]]
        result['imports']=[entry.dll.decode('ascii',errors='replace') for entry in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[])[:40]]
    finally: pe.close()
    return result
