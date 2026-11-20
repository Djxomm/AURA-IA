import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QUrl
from agente_ia.native_browser import decide_certificate, navigation_url
import pytest


class Certificate:
    def __init__(self, overridable=True):
        self.overridable = overridable
        self.result = None
    def isOverridable(self): return self.overridable
    def url(self): return QUrl('https://localhost:8443/')
    def description(self): return 'Certificado autofirmado'
    def acceptCertificate(self): self.result = 'accepted'
    def rejectCertificate(self): self.result = 'rejected'


def test_certificate_requires_explicit_acceptance():
    error = Certificate()
    assert not decide_certificate(error, lambda host, reason: False)
    assert error.result == 'rejected'
    assert decide_certificate(error, lambda host, reason: host == 'localhost')
    assert error.result == 'accepted'


def test_non_overridable_never_prompts_or_accepts():
    error = Certificate(False)
    assert not decide_certificate(error, lambda *args: pytest.fail('Must not prompt'))
    assert error.result == 'rejected'


@pytest.mark.parametrize('value', ['file:///C:/Windows/win.ini', 'javascript://alert(1)', 'https://user:secret@example.com'])
def test_disallowed_addresses(value):
    with pytest.raises(ValueError): navigation_url(value)


def test_address_and_search():
    assert navigation_url('example.com').toString() == 'https://example.com'
    assert navigation_url('http://localhost:8000').scheme() == 'http'
    assert 'search?q=' in navigation_url('cómo programar').toString()
