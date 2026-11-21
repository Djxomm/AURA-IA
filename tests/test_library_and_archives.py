import json
import zipfile
from pathlib import Path
import pytest
from agente_ia.archive_tools import extract,create_zip
from agente_ia.model_library import discover


def test_verified_library_excludes_partial_and_external_files(tmp_path):
    (tmp_path/'ok.gguf').write_bytes(b'GGUF')
    items=[{'filename':'ok.gguf','status':'ready','size':4},
           {'filename':'incomplete.gguf','status':'downloading','size':4},
           {'filename':'../outside.gguf','status':'ready','size':4}]
    (tmp_path/'catalog.json').write_text(json.dumps({'models':items}))
    assert discover([tmp_path])==[tmp_path/'ok.gguf']


def test_archive_paths_and_existing_destination_are_rejected(tmp_path):
    bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(bad,'w') as archive:archive.writestr('../escape.txt','no')
    with pytest.raises(ValueError):extract(bad,tmp_path/'out')
    assert not (tmp_path/'escape.txt').exists() and not (tmp_path/'out').exists()
    good=tmp_path/'good.zip'
    with zipfile.ZipFile(good,'w') as archive:archive.writestr('src/main.py','print(42)')
    assert extract(good,tmp_path/'out')==1
    assert (tmp_path/'out/src/main.py').read_text()=='print(42)'
    with pytest.raises(ValueError):extract(good,tmp_path/'out')


def test_source_zip_omits_common_private_files(tmp_path):
    project=tmp_path/'project';project.mkdir()
    for name in ('main.py','.env','secret.key','data.db'):(project/name).write_text('data')
    target=tmp_path/'source.zip';assert create_zip(project,target)==1
    with zipfile.ZipFile(target) as archive:assert archive.namelist()==['main.py']
