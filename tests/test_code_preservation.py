import pytest
from agente_ia.code_preservation import validate_agent_change

def test_whole_file_cannot_drop_original_functions_or_methods():
 original='def original():\n return 7\n\nclass Screen:\n def save(self): pass\n'
 with pytest.raises(ValueError,match='original'):validate_agent_change('screen.py',original,'def added(): pass',True)
 with pytest.raises(ValueError,match='Screen.save'):validate_agent_change('screen.py',original,'def original(): return 7\nclass Screen: pass',True)
 validate_agent_change('screen.py',original,original+'\ndef added(): return 8',True)

def test_precise_edits_can_remove_an_authorized_block_but_cannot_write_invalid_python():
 validate_agent_change('screen.py','def old(): pass','def new(): pass',False)
 with pytest.raises(ValueError,match='sintaxis'):validate_agent_change('screen.py','def old(): pass','def new(:',False)

def test_javascript_preserves_named_components_on_full_replacement():
 with pytest.raises(ValueError,match='save'):validate_agent_change('screen.mjs','export function save() {}','export function load() {}',True)
