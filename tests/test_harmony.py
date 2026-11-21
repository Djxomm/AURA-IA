from agente_ia.harmony_transport import HarmonyOutput,prompt
from agente_ia.providers import ProviderError
import pytest

def test_channels_chunked():
    parser=HarmonyOutput();out=''
    for c in '<|channel|>analysis<|message|>PRIVATE<|end|><|start|>assistant<|channel|>final<|message|>391<|return|>':out+=parser.feed(c)
    out+=parser.finish()
    assert out=='391'

def test_no_analysis_fallback():
    p=HarmonyOutput();assert p.feed('<|channel|>analysis<|message|>PRIVATE')==''
    with pytest.raises(ProviderError):p.finish()

def test_native_call():
    p=HarmonyOutput();p.feed(' to=functions.read_file<|channel|>commentary<|message|>{"path":"main.py"}<|call|>')
    assert 'read_file' in p.finish()

def test_prompt():
    text=prompt([{'role':'system','content':'AURA'},{'role':'user','content':'Hola'}],'rapido')
    assert 'Reasoning: low' in text and '<|start|>developer<|message|>AURA' in text
