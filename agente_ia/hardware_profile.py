"""Lightweight Windows hardware recommendations; inference stays CPU-only."""
import ctypes,os,platform
from ctypes import wintypes

def hardware_info():
    logical=os.cpu_count() or 1;cores=max(1,logical//2);name=platform.processor() or 'CPU';total=0
    if os.name=='nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:name=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
        except OSError:pass
        class Memory(ctypes.Structure):
            _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(n,ctypes.c_ulonglong) for n in ['total','available','page_total','page_available','virtual_total','virtual_available','extended']]
        state=Memory();state.length=ctypes.sizeof(state)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):total=state.total
        size=wintypes.DWORD(0);kernel=ctypes.windll.kernel32
        kernel.GetLogicalProcessorInformationEx(0,None,ctypes.byref(size))
        if 0<size.value<1024*1024:
            data=ctypes.create_string_buffer(size.value)
            if kernel.GetLogicalProcessorInformationEx(0,data,ctypes.byref(size)):
                import struct
                position=0;count=0
                while position+8<=size.value:
                    relation,length=struct.unpack_from('<II',data,position)
                    if length<8 or position+length>size.value:break
                    if relation==0:count+=1
                    position+=length
                if count:cores=count
    return {'cpu':name,'cores':cores,'logical':logical,'ram_gib':round(total/1024**3,1) if total else None}

def recommended_settings(info):
    memory=info.get('ram_gib') or 8
    return {'num_thread':max(1,min(4,info.get('cores',1))),'num_ctx':4096 if memory>=15 else 2048,'num_batch':64,'max_predict_tokens':0}
