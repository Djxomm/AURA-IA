import importlib.util,json,urllib.request
from pathlib import Path
base=Path(__file__).resolve().parents[1];root=base/'runtime/vision';root.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('downloads',str(base/'scripts/download_models.py'));d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
repo='ggml-org/SmolVLM-500M-Instruct-GGUF';revision='72e986006ef53e37cdd3f6d4241c90b0f01df376'
files=[('SmolVLM-500M-Instruct-Q8_0.gguf',436806912,'9d4612de6a42214499e301494a3ecc2be0abdd9de44e663bda63f1152fad1bf4'),('mmproj-SmolVLM-500M-Instruct-f16.gguf',199468800,'4b2fca922e549e9b9608f4ba56f93565dd5220e935ba5570a2a864a0fcc988a6')]
for name,size,sha in files:
 d.download(f'https://huggingface.co/{repo}/resolve/{revision}/{name}',root/name,size,sha,lambda count,total:print(name,count,total,flush=True))
(root/'provenance.json').write_text(json.dumps({'repo':repo,'revision':revision,'files':[{'name':n,'size':s,'sha256':h} for n,s,h in files]},indent=2),encoding='utf-8');print('VISION_VERIFICADA',flush=True)

import shutil
shutil.copy2(base/'scripts/ocr-windows.ps1',root/'ocr-windows.ps1')
