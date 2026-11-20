import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication
from native_launcher import Window
import native_launcher

def setup_window(tmp_path,monkeypatch):
 app=QApplication.instance() or QApplication([])
 assets=tmp_path/'assets';assets.mkdir();(assets/'aura-inicio.mp4').write_bytes(b'test')
 monkeypatch.setattr(native_launcher,'ASSETS',assets)
 events=[]
 class Splash:
  def __init__(self,owner,path):self.released=False;self.started=False
  def begin(self):self.started=True;events.append('video')
  def release(self):self.released=True;events.append('released')
 monkeypatch.setattr(native_launcher,'StartupSplash',Splash)
 w=Window(tmp_path/'data');w.save_pref('floating',False);w.prepare_model=lambda:events.append('model')
 return app,w,events

def test_video_precedes_model_and_chat_waits_for_ready(tmp_path,monkeypatch):
 app,w,events=setup_window(tmp_path,monkeypatch);w.start();splash=w.startup
 assert events==['video'];assert not w.isVisible()
 app.processEvents();assert events==['video','model'];assert not w.isVisible()
 w.handle_event('warmed',None);assert w.isVisible();assert splash.released;assert w.startup is None
 w.close();w.store.close();w.memory.close()

def test_skipping_video_does_not_cancel_preparation(tmp_path,monkeypatch):
 app,w,events=setup_window(tmp_path,monkeypatch);cancel=[];monkeypatch.setattr(w.client,'stop',lambda:cancel.append(True));w.start();splash=w.startup;w.finish_startup();app.processEvents()
 assert w.isVisible() and splash.released;assert 'model' in events;assert not cancel
 w.handle_event('warmed',None);w.close();w.store.close();w.memory.close()


def test_startup_contains_only_video_without_controls(tmp_path):
 from native_launcher import StartupSplash
 from PySide6.QtWidgets import QPushButton,QLabel
 from PySide6.QtMultimediaWidgets import QVideoWidget
 app=QApplication.instance() or QApplication([])
 splash=StartupSplash(None,tmp_path/'intro.mp4')
 assert not splash.findChildren(QPushButton)
 assert not splash.findChildren(QLabel)
 assert len(splash.findChildren(QVideoWidget))==1
 assert splash.layout().contentsMargins().left()==0
 splash.release();app.processEvents()
