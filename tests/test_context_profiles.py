from pathlib import Path
import pytest
from agente_ia.config import AppSettings
from agente_ia.model_library import context_profile,limits,programming_settings

def model(tmp_path,monkeypatch,gib,trained=32768):
 p=tmp_path/'model.gguf'
 p.write_bytes(b'GGUF')
 import os
 original=Path.stat
 def stat(path,*args,**kwargs):
  result=original(path,*args,**kwargs)
  if path==p:
   values=list(result);values[6]=int(gib*1024**3);return os.stat_result(values)
  return result
 monkeypatch.setattr(Path,'stat',stat)
 monkeypatch.setattr('agente_ia.model_library.model_info',lambda path:{'general.architecture':'gpt-oss','gpt-oss.context_length':trained})
 return p

def test_gpt_manual_16k_is_honored_but_auto_stays_4k(tmp_path,monkeypatch):
 p=model(tmp_path,monkeypatch,11.3);hw={'ram_gib':16,'cores':4}
 profile=context_profile(p,hw)
 assert profile=={'recommended':4096,'maximum':16384,'automatic':4096}
 assert limits(p,AppSettings(num_ctx=16384),hw).num_ctx==16384
 assert limits(p,AppSettings(num_ctx=32768),hw).num_ctx==16384

def test_more_ram_and_model_training_limits(tmp_path,monkeypatch):
 p=model(tmp_path,monkeypatch,11.3)
 assert context_profile(p,{'ram_gib':32,'cores':8})['maximum']==32768
 p=model(tmp_path,monkeypatch,1,trained=4096)
 assert context_profile(p,{'ram_gib':32,'cores':8})['maximum']==4096

def test_legacy_recommendation_and_programming_temperature(tmp_path,monkeypatch):
 p=model(tmp_path,monkeypatch,1)
 assert context_profile(p,{'ram_gib':16,'cores':2})['recommended']==2048
 settings=AppSettings(temperature=1.5)
 assert programming_settings(settings).temperature==.2
 assert settings.temperature==1.5
 assert programming_settings(settings,False).temperature==1.5
