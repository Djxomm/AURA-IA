"""QbitX checkpoints: bounded evidence, no second model or background inference."""
import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from .tools import estimate_tokens


class TaskCoordinator:
    def __init__(self, database):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(database), check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS qbitx_tasks(session TEXT PRIMARY KEY, project TEXT, state TEXT, updated REAL)')
        self.db.commit()

    def begin(self, session, project, request):
        with self.lock:
            row = self.db.execute('SELECT project,state FROM qbitx_tasks WHERE session=?', (session,)).fetchone()
            previous = json.loads(row[1]) if row and row[0] == project else {}
            resume = bool(re.match(r'(?i)^\s*(contin[uú]a|sigue|reanuda|ok|dale|corrige|ajusta|compila|ejecuta|prueba|verifica|probamos|probemos)', request))
            state = {'objective': previous.get('objective', request[:2400]) if resume else request[:2400],
                     'request': request[:2400], 'status': 'working',
                     'files': previous.get('files', [])[-24:],
                     'evidence': previous.get('evidence', [])[-6:],
                     'steps': ['Inspeccionar archivos', 'Aplicar cambios revisados', 'Comprobar sintaxis', 'Probar y compilar: requiere ejecución explícita']}
            self.save(session, project, state)
            return state

    def save(self, session, project, state):
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO qbitx_tasks VALUES(?,?,?,?)',
                            (session, project, json.dumps(state, ensure_ascii=False), time.time()))
            self.db.commit()

    def event(self, session, project, state, event, payload):
        if event == 'proposal_resolved' and payload.get('status') == 'applied':
            state['files'] = list(dict.fromkeys(state['files'] + [payload.get('file_path', '')]))[-24:]
        elif event == 'tool_result':
            state['evidence'] = (state['evidence'] + [str(payload.get('summary', ''))[:400]])[-6:]
        elif event == 'error':
            state['status'] = 'attention'
        self.save(session, project, state)

    def execution(self, session, project, action, path, code):
        with self.lock:
            row=self.db.execute('SELECT project,state FROM qbitx_tasks WHERE session=?',(session,)).fetchone()
            if not row or row[0]!=project:
                return
            state=json.loads(row[1])
            note=f'Proceso autorizado: {action} {path}; salida {code}. No demuestra por sí solo corrección funcional.'
            state['evidence']=(state.get('evidence',[])+[note[:400]])[-6:]
            state['status']='review_pending' if code==0 else 'attention'
            self.save(session, project, state)

    @staticmethod
    def context(state):
        summary = {'files': state.get('files', [])[-12:], 'evidence': [x[:180] for x in state.get('evidence', [])[-3:]]}
        if state.get('objective') != state.get('request'):
            summary['objective'] = state['objective'][:1000]
        return ('\nAURAX: conserva el objetivo y divide cambios. QbitX: lee, edita y comprueba. '
                'No inventes pruebas ni compilaciones. Siguiente paso: un cambio completo.\n'
                + json.dumps(summary, ensure_ascii=False))



def bounded_conversation(messages, limit):
    """Keep system + current request + newest complete tool exchanges; never orphan a tool."""
    def cost(items):
        chars=sum(len(str(item.get('content','')))+len(json.dumps(item.get('tool_calls',[]),ensure_ascii=False)) for item in items)
        return max(estimate_tokens(items),chars//2+len(items)*12)
    if cost(messages) <= limit:
        return messages
    first_user = next((i for i in range(len(messages)-1, -1, -1) if messages[i]['role'] == 'user'), None)
    if first_user is None:
        return messages
    head = messages[:1] + [messages[first_user]]
    groups = []
    for item in messages[first_user+1:]:
        if item['role'] == 'tool' and groups:
            groups[-1].append(item)
        else:
            groups.append([item])
    selected = []
    for group in reversed(groups):
        candidate = head + [item for block in [group]+selected for item in block]
        if cost(candidate) > limit:
            break
        selected.insert(0, group)
    return head + [item for group in selected for item in group]
