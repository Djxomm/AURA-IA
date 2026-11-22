import importlib.util,json
from pathlib import Path

def test_public_training_examples_are_synthetic_disjoint_and_use_real_tool_names(tmp_path):
    root=Path(__file__).parents[1];spec=importlib.util.spec_from_file_location('aura_public_dataset',root/'training/build_public_dataset.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    manifest=module.build(tmp_path);assert manifest['overlap']==0 and manifest['private_project_files_read'] is False
    from agente_ia.tools import parse_xml_tool_calls
    train=[json.loads(x) for x in (tmp_path/'train.jsonl').read_text(encoding='utf-8').splitlines()];validation=[json.loads(x) for x in (tmp_path/'validation.jsonl').read_text(encoding='utf-8').splitlines()]
    assert not ({x['id'] for x in train}&{x['id'] for x in validation})
    for row in train+validation:
        assert row['origin']=='original-synthetic' and row['license']=='MIT'
        assert 'AURA' in row['messages'][0]['content']
        response=row['messages'][-1]['content']
        if '<tool_call>' in response:
            _,calls=parse_xml_tool_calls(response);assert len(calls)==1 and calls[0]['name'] in {'read_file','edit_file','create_file'}
