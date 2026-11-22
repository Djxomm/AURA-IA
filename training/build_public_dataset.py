"""Generate only original synthetic examples for AURA; never reads a project corpus."""
import argparse,hashlib,json,random
from pathlib import Path

SYSTEM='Eres AURA, asistente local de programación del proyecto abierto AURA. Responde en español con claridad. Conserva el código ajeno a la solicitud, usa herramientas cuando correspondan y no afirmes haber ejecutado pruebas si no las ejecutaste. Reconoce la procedencia del modelo cuando se pregunte.'

def examples():
    rows=[]
    def add(kind,user,assistant):
        messages=[{'role':'system','content':SYSTEM},{'role':'user','content':user},{'role':'assistant','content':assistant}]
        ident=hashlib.sha256(json.dumps(messages,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        rows.append({'id':ident,'kind':kind,'origin':'original-synthetic','license':'MIT','messages':messages})
    for question,answer in [('¿Cómo te llamas?','Me llamo AURA.'),('¿Qué es AURA?','AURA es un proyecto abierto de asistencia y programación local.'),('¿Tu modelo se entrenó desde cero?','Esta línea parte de Qwen Coder y puede adaptarse con ejemplos autorizados. No es un modelo fundacional entrenado desde cero.'),('¿Puedes garantizar que mi programa no tendrá errores?','Puedo ayudar a revisarlo y probarlo, pero no garantizar ausencia de errores.'),('¿Ya compilaste el programa?','Solo puedo afirmarlo después de ejecutar la compilación y comprobar su resultado.'),('¿Conoces los cambios que haré mañana?','Necesitaré consultar el código y la documentación actualizados.')]:add('identity',question,answer)
    for i in range(16):
        name=f'sumar_valores_{i}'
        add('code',f'Define {name}(a, b) para devolver la suma. Solo Python.',f'def {name}(a, b):\n    return a + b\n')
    for i in range(12):
        path=f'src/panel_{i}.py'
        call={'name':'read_file','arguments':{'path':path}}
        add('read_tool',f'Antes de cambiar {path}, lee su contenido actual.','<tool_call>'+json.dumps(call,ensure_ascii=False)+'</tool_call>')
        old=f'def calcular_{i}(a, b):\n    return a - b\n';new=f'def calcular_{i}(a, b):\n    return a + b\n'
        call={'name':'edit_file','arguments':{'path':path,'old_text':old,'new_text':new,'reason':'Corregir la suma conservando nombre y parámetros.'}}
        add('edit_tool',f'En {path}, cambia solo esta función para sumar. Mantén el resto del archivo. Código actual:\n'+old,'<tool_call>'+json.dumps(call,ensure_ascii=False)+'</tool_call>')
    for i in range(8):
        path=f'ejemplos/saludo_{i}.py';code=f'def saludo_{i}():\n    return "Hola desde AURA"\n';call={'name':'create_file','arguments':{'path':path,'content':code,'reason':'Crear el ejemplo solicitado.'}}
        add('create_tool',f'Propón crear {path} con una función saludo_{i} que devuelva Hola desde AURA.','<tool_call>'+json.dumps(call,ensure_ascii=False)+'</tool_call>')
    return rows

def build(output):
    rows=examples();random.Random(20261122).shuffle(rows);validation=rows[:10];train=rows[10:];output=Path(output);output.mkdir(parents=True,exist_ok=True)
    for name,items in [('train.jsonl',train),('validation.jsonl',validation)]:output.joinpath(name).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in items),encoding='utf-8')
    manifest={'name':'AURA-public-demo','origin':'original-synthetic','license':'MIT','private_project_files_read':False,'train_count':len(train),'validation_count':len(validation),'overlap':len({x['id'] for x in train}&{x['id'] for x in validation}),'scope':'Small recipe demonstration, not a general programming benchmark.'}
    output.joinpath('manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();print(json.dumps(build(args.output)))
