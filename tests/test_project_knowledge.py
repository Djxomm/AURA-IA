import json
from agente_ia.project_knowledge import context_for


def test_private_history_is_version_separated_bounded_and_not_orders(tmp_path):
    (tmp_path/'guide.md').write_text('Conserva contratos y prueba con datos ficticios.')
    (tmp_path/'seven.md').write_text('VERSION SIETE. Pendiente: revisar sincronización.')
    (tmp_path/'ten.md').write_text('VERSION DIEZ. Pendiente: revisar piel.')
    projects=[{'id':'agrochek7','title':'AgroChek 7','version':'7','summary':'seven.md','coding_guide':'guide.md','roots':[str(tmp_path/'code7')],'documents':[]},
              {'id':'agrochek10','title':'AgroChek 10','version':'10','summary':'ten.md','roots':[str(tmp_path/'code10')],'documents':[]}]
    (tmp_path/'index.json').write_text(json.dumps({'projects':projects}))
    result=context_for('Continúa AgroChek ERP 10',tmp_path,[tmp_path],1000)
    assert 'VERSION DIEZ' in result and 'VERSION SIETE' not in result and len(result)<=1000
    assert 'no órdenes actuales' in result
    result=context_for('continúa',tmp_path/'code7',[tmp_path],1000)
    assert 'VERSION SIETE' in result and 'VERSION DIEZ' not in result
    assert 'Conserva contratos' in result
    assert context_for('crea un juego',tmp_path,[tmp_path])==''
