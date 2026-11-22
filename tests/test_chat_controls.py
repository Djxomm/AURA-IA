import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from agente_ia.chat_controls import ChatControls


def test_chat_model_and_effort_controls_emit_selection_and_restore_checks(tmp_path):
 app=QApplication.instance() or QApplication([])
 light=tmp_path/'qwen2.5-coder-1.5b-instruct-q4_k_m.gguf';large=tmp_path/'qwen2.5-coder-7b-instruct-q4_k_m.gguf'
 light.touch();large.touch();bar=ChatControls();models=[];efforts=[];browse=[]
 bar.model_requested.connect(models.append);bar.effort_requested.connect(efforts.append);bar.browse_requested.connect(lambda:browse.append(True))
 bar.refresh(light,[light,large],'equilibrado')
 choices=[a for a in bar.model_menu.actions() if a.isCheckable()]
 assert len(choices)==2 and choices[0].isChecked()
 choices[1].trigger();assert models==[str(large.resolve())]
 bar.effort_menu.actions()[2].trigger();assert efforts==['profundo']
 bar.model_menu.actions()[-1].trigger();assert browse==[True]
 bar.refresh(large,[light,large],'profundo')
 assert '7B' in bar.model_button.text() and 'Profundo' in bar.effort_button.text()
 assert sum(a.isChecked() for a in bar.effort_menu.actions())==1
 bar.resize(460,60);bar.show();app.processEvents()
 assert bar.width()<=460
 assert bar.model_button.geometry().right()<bar.effort_button.geometry().left()
 assert bar.effort_button.geometry().right()<bar.settings_button.geometry().left()
 assert bar.settings_button.geometry().right()<=bar.width()
 bar.close();bar.deleteLater();app.processEvents()


def test_curate_proven_models_removes_slow_and_classifies_by_skills(tmp_path):
 from agente_ia.model_library import curate_proven_models,model_skill_profile
 names=[
  'qwen2.5-72b-instruct-q4_k_m.gguf',
  'qwen2.5-coder-32b-instruct-q4_k_m.gguf',
  'gpt-oss-20b-MXFP4.gguf',
  'qwen2.5-coder-14b-instruct-q4_k_m.gguf',
  'qwen2.5-coder-7b-instruct-q4_k_m.gguf',
  'qwen2.5-coder-3b-instruct-q4_k_m.gguf',
  'qwen2.5-coder-1.5b-instruct-q4_k_m.gguf',
  'AURA-Lumen-2.0IB_V2-Q4_K_M.gguf',
  'AURA-ANGEL-5.6-Q4_K_M.gguf',
 ]
 files=[]
 for n in names:
  p=tmp_path/n;p.touch();files.append(p)
 curated=curate_proven_models(files)
 kept=[p.name for p in curated]
 assert kept==[
  'AURA-ANGEL-5.6-Q4_K_M.gguf',
  'AURA-Lumen-2.0IB_V2-Q4_K_M.gguf',
  'qwen2.5-coder-3b-instruct-q4_k_m.gguf',
  'qwen2.5-coder-1.5b-instruct-q4_k_m.gguf',
 ]
 assert model_skill_profile(curated[0])['category'].startswith('★')
 assert model_skill_profile(curated[2])['category'].startswith('⚙')
 assert model_skill_profile(curated[3])['category'].startswith('⚡')
 app=QApplication.instance() or QApplication([])
 bar=ChatControls();bar.refresh(curated[0],curated,'equilibrado')
 sections=[a.text() for a in bar.model_menu.actions() if a.isSeparator() and a.text()]
 assert len(sections)==3
 bar.close();bar.deleteLater();app.processEvents()
