"""AURA desktop startup: UI first, background CPU model and isolated local data."""
from __future__ import annotations
import argparse, json, os, queue, socket, sys, threading, time, urllib.request, webbrowser
from pathlib import Path
import uvicorn
from agente_ia.storage import Storage
from agente_ia.providers import LocalLLMClient
from agente_ia.web_server import create_app
from agente_ia.model_manager import ModelManager

BASE=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent/'runtime'
ASSETS=Path(__file__).resolve().parent/'agente_ia'/'static'/'assets'

def free_port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]
def request_json(url,data=None,timeout=10):
    req=urllib.request.Request(url,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as result:return json.load(result)

class Desktop:
    def __init__(self,data_dir):
        self.data=Path(data_dir).resolve();self.data.mkdir(parents=True,exist_ok=True)
        self.db=Storage(self.data/'aura.db');self.messages=queue.Queue();self.closed=threading.Event();self.server=None;self.url=''
        settings=self.db.get_settings();projects=self.data/'Proyectos';projects.mkdir(exist_ok=True)
        if not (self.data/'configured').exists():
            self.db.save_settings(settings.model_copy(update={'workspace_path':str(projects),'num_ctx':4096,'num_thread':2,'num_gpu':0,'tool_mode':'xml','max_predict_tokens':0}))
            (self.data/'configured').touch()
        self.manager=ModelManager(BASE,self.data,self.db)
    def start(self):
        client=LocalLLMClient(auth_provider=self.manager.auth_for)
        app=create_app(storage=self.db,llm_client=client,bundled_skills_dir=BASE/'skills',model_manager=self.manager)
        app.state.engine.skills_store.install_defaults(BASE/'skills')
        app.state.shutdown_request=lambda:self.messages.put('__EXIT__')
        @app.post('/api/aura/shutdown')
        async def shutdown():
            threading.Timer(.8,app.state.shutdown_request).start();return {'ok':True}
        port=free_port();self.url=f'http://127.0.0.1:{port}'
        self.server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_config=None,access_log=False))
        threading.Thread(target=self.server.run,daemon=True).start()
        for _ in range(100):
            try:request_json(self.url+'/api/health');break
            except Exception:time.sleep(.1)
        else:raise RuntimeError('No pudo abrirse la interfaz local.')
        def load():
            try:self.manager.start_initial();self.messages.put('AURA está lista para responder.')
            except Exception as exc:self.messages.put('No se pudo cargar el modelo: '+str(exc))
        threading.Thread(target=load,daemon=True).start()
    def stop(self):
        if self.closed.is_set():return
        self.closed.set();self.manager.close()
        if self.server:self.server.should_exit=True

def self_test(desktop):
    desktop.start()
    try:
        for _ in range(600):
            status=request_json(desktop.url+'/api/aura/status')
            if status['engine']['phase']=='ready':break
            if status['engine']['phase']=='error':raise RuntimeError(status['engine']['error'])
            time.sleep(.5)
        else:raise RuntimeError('Carga del modelo agotada')
        started=time.monotonic();first=None;answer='';events=[]
        req=urllib.request.Request(desktop.url+'/api/chat/stream',data=json.dumps({'message':'Hola AURA. Escribe una función Python sumar(a,b), solo el código.','mode':'chat'}).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=180) as response:
            for raw in response:
                line=raw.decode().strip()
                if not line.startswith('data:'):continue
                ev=json.loads(line[5:]);events.append(ev['type'])
                if ev['type']=='error':raise RuntimeError(ev['message'])
                if ev['type']=='token':
                    if first is None:first=time.monotonic()-started
                    answer+=ev.get('delta','')
                if ev['type']=='done':answer=ev.get('content',answer)
        if not answer.strip() or 'done' not in events:raise RuntimeError('No se recibió una respuesta completa')
        result={'brand':'AURA Inteligencia Artificial','real_spanish_answer':answer,'first_token_seconds':round(first,2),'total_seconds':round(time.monotonic()-started,2),'events':events,'model':request_json(desktop.url+'/api/local-models')['state'],'skills':[s['name'] for s in request_json(desktop.url+'/api/skills')['skills']]}
        (desktop.data/'verificacion.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    finally:desktop.stop()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true');parser.add_argument('--data-dir');args=parser.parse_args()
    data=args.data_dir or str(Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'AURA_IA')
    app=Desktop(data)
    if args.self_test:self_test(app);return 0
    import tkinter as tk
    root=tk.Tk();root.title('AURA · Inteligencia Artificial');root.geometry('540x240');root.configure(bg='#050A14')
    try:
        icon=tk.PhotoImage(file=str(ASSETS/'aura-icono.png'));root.iconphoto(True,icon)
    except Exception:pass
    tk.Label(root,text='AURA',fg='#00F0FF',bg='#050A14',font=('Segoe UI',28,'bold')).pack(pady=(20,6))
    label=tk.Label(root,text='Preparando la interfaz…',wraplength=490,fg='#E2E8F0',bg='#050A14',font=('Segoe UI',11));label.pack(pady=10)
    tk.Button(root,text='Abrir AURA',command=lambda:webbrowser.open(app.url) if app.url else None).pack(pady=5)
    def stop():
        label.config(text='Cerrando AURA…');root.update_idletasks();app.stop();root.destroy()
    tk.Button(root,text='Cerrar AURA y liberar el modelo',command=stop).pack(pady=4);root.protocol('WM_DELETE_WINDOW',stop)
    opened=False
    def start():
        try:app.start()
        except Exception as exc:app.messages.put(str(exc))
    def tick():
        nonlocal opened
        while not app.messages.empty():
            message=app.messages.get()
            if message=='__EXIT__':stop();return
            label.config(text=message)
        if app.url and app.server and app.server.started and not opened:
            webbrowser.open(app.url);opened=True;root.iconify()
        root.after(750,tick)
    threading.Thread(target=start,daemon=True).start();tick();root.mainloop();return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        if '--data-dir' in sys.argv:
            p=Path(sys.argv[sys.argv.index('--data-dir')+1]);p.mkdir(parents=True,exist_ok=True);(p/'error.txt').write_text(str(exc),'utf-8')
        raise
