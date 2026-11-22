"""Reproducible local-only pilot LoRA. Never publishes or replaces a base model."""
import argparse,json,os,time
from pathlib import Path
os.environ.update({'HF_HUB_DISABLE_TELEMETRY':'1','HF_HUB_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false'})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base',type=Path,required=True);parser.add_argument('--data',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--steps',type=int,default=32);parser.add_argument('--threads',type=int,default=4);parser.add_argument('--check-only',action='store_true');args=parser.parse_args()
    if not 1<=args.steps<=10000 or not 1<=args.threads<=64:parser.error('steps debe estar entre 1–10000 y threads entre 1–64.')
    if not args.base.is_dir():parser.error('base debe ser una carpeta local del modelo.')
    if args.output.exists() and not args.check_only:parser.error('Elige una carpeta de salida nueva para conservar los candidatos anteriores.')
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer
    torch.set_num_threads(args.threads);torch.manual_seed(22)
    tokenizer=AutoTokenizer.from_pretrained(args.base,local_files_only=True,trust_remote_code=False)
    def ids(value):return list(value['input_ids']) if hasattr(value,'keys') else list(value)
    def dataset(name):
        result=[]
        for line in (args.data/name).read_text(encoding='utf-8-sig').splitlines():
            row=json.loads(line);messages=row['messages'];prefix=ids(tokenizer.apply_chat_template(messages[:-1],tokenize=True,add_generation_prompt=True));tokens=ids(tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=False))
            if len(tokens)>512 or tokens[:len(prefix)]!=prefix or len(tokens)<=len(prefix):raise ValueError('Ejemplo demasiado largo o prefijo incompatible: '+row['id'])
            result.append((row['id'],torch.tensor([tokens]),torch.tensor([[-100]*len(prefix)+tokens[len(prefix):]])))
        return result
    train=dataset('train.jsonl');validation=dataset('validation.jsonl')
    if not train or not validation or {x[0] for x in train}&{x[0] for x in validation}:raise ValueError('Conjuntos vacíos o solapados.')
    if args.check_only:print(json.dumps({'valid':True,'train':len(train),'validation':len(validation),'weights_loaded':False}));return
    from peft import LoraConfig,get_peft_model
    model=AutoModelForCausalLM.from_pretrained(args.base,local_files_only=True,trust_remote_code=False,torch_dtype=torch.float32,low_cpu_mem_usage=True);model.config.use_cache=False
    def evaluate():
        model.eval()
        with torch.no_grad():return sum(float(model(input_ids=ids_,labels=labels).loss) for _,ids_,labels in validation)/len(validation)
    baseline=evaluate();model=get_peft_model(model,LoraConfig(r=8,lora_alpha=16,lora_dropout=.05,target_modules=['q_proj','v_proj'],bias='none',task_type='CAUSAL_LM'));model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False});model.enable_input_require_grads()
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=1e-4);model.train();start=time.monotonic()
    for step in range(args.steps):
        _,input_ids,labels=train[step%len(train)];optimizer.zero_grad(set_to_none=True);loss=model(input_ids=input_ids,labels=labels).loss
        if not torch.isfinite(loss):raise RuntimeError('Pérdida no finita; se detuvo el piloto.')
        loss.backward();torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],1.0);optimizer.step();print(json.dumps({'step':step+1,'steps':args.steps,'loss':float(loss.detach())}),flush=True)
    after=evaluate();args.output.mkdir(parents=True);model.save_pretrained(args.output/'adapter',safe_serialization=True);tokenizer.save_pretrained(args.output/'adapter')
    report={'name':'AURA-Ligero-public-pilot','base':str(args.base.resolve()),'steps':args.steps,'baseline_validation_loss':baseline,'candidate_validation_loss':after,'seconds':time.monotonic()-start,'published':False,'promoted':False,'note':'Loss is not task accuracy; functional held-out tests are still required.'}
    (args.output/'evaluation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':main()
