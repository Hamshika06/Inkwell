"""One-seed encoder pipeline; selection and thresholds use OPP-115 validation only."""
import argparse
import json
import random
import resource
import time
from pathlib import Path
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from inkwell.common import verified_dataset, ROOT, CATEGORIES, read_rows, digest, full_metrics
from inkwell.loss import masked_loss
from inkwell.predict import Predictor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='distilbert-base-uncased')
    ap.add_argument('--source', choices=['opp115', 'combined'], default='opp115')
    ap.add_argument('--c3pa-weight', type=float, default=0.1)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--epochs', type=int, default=10)
    ap.add_argument('--batch-size', type=int, default=16)
    ap.add_argument('--lr', type=float, default=5e-5)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    if args.c3pa_weight <= 0 or args.epochs < 1: raise ValueError('Weights and epochs must be positive')
    out = Path(args.out)
    if out.exists(): raise SystemExit('Run exists; use a new directory')
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    data = verified_dataset(); rows = read_rows(data)
    train = [r for r in rows if r['split']=='train' and (args.source=='combined' or r['source']=='opp115')]
    val = [r for r in rows if r['split']=='validation' and r['source']=='opp115']
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(args.model, num_labels=len(CATEGORIES),
            id2label=dict(enumerate(CATEGORIES)), label2id={c:i for i,c in enumerate(CATEGORIES)}).to(device)
    # Expand long segments into windows; preserve total row weight across windows.
    examples = []
    for row in train:
        windows = tokenizer(row['text'], max_length=512, truncation=True, stride=128, return_overflowing_tokens=True)
        n = len(windows['input_ids'])
        for i in range(n):
            examples.append(( {k:v[i] for k,v in windows.items() if k!='overflow_to_sample_mapping'}, row,
                row['weight']*(args.c3pa_weight if row['source']=='c3pa' else 1)/n ))
    y = np.array([r['label_vec'] for r in train]); mask = np.array([r['label_mask'] for r in train])
    pos = (y*mask).sum(0); neg = ((1-y)*mask).sum(0)
    pos_weight = torch.tensor(np.clip(neg/np.maximum(pos,1),1,10),dtype=torch.float,device=device)
    optimizer = torch.optim.AdamW(model.parameters(),lr=args.lr,weight_decay=0.01)
    from transformers import get_linear_schedule_with_warmup
    steps = ((len(examples)+args.batch_size-1)//args.batch_size)*args.epochs
    scheduler = get_linear_schedule_with_warmup(optimizer,int(steps*.1),steps)
    best = -1; best_state = None; patience=0; history=[]; start=time.perf_counter()
    for epoch in range(args.epochs):
        model.train(); random.shuffle(examples); losses=[]
        for at in range(0,len(examples),args.batch_size):
            batch=examples[at:at+args.batch_size]
            inputs=tokenizer.pad([e[0] for e in batch],return_tensors='pt').to(device)
            targets=torch.tensor([e[1]['label_vec'] for e in batch],dtype=torch.float,device=device)
            masks=torch.tensor([e[1]['label_mask'] for e in batch],dtype=torch.float,device=device)
            weights=torch.tensor([e[2] for e in batch],dtype=torch.float,device=device)
            optimizer.zero_grad(); loss=masked_loss(model(**inputs).logits,targets,masks,weights,pos_weight)
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1);optimizer.step();scheduler.step()
            losses.append(loss.item())
            if (at//args.batch_size)%50==0: print(f'epoch={epoch+1} batch={at//args.batch_size+1}/{(len(examples)+args.batch_size-1)//args.batch_size} loss={loss.item():.4f}',flush=True)
        model.eval(); scores=[]
        with torch.no_grad():
            for row in val:
                encoded=tokenizer(row['text'],max_length=512,truncation=True,stride=128,return_overflowing_tokens=True,padding=True,return_tensors='pt')
                encoded.pop('overflow_to_sample_mapping',None)
                scores.append(model(**encoded.to(device)).logits.max(0).values.cpu().numpy())
        metric=full_metrics(val,np.array(scores),np.zeros(len(CATEGORIES)))['macro_f1']
        history.append({'epoch':epoch+1,'mean_loss':float(np.mean(losses)),'validation_macro_f1_at_0_5':metric})
        print(history[-1],flush=True)
        if metric>best:
            best=metric;best_state={k:v.detach().cpu().clone() for k,v in model.state_dict().items()};patience=0
        else:
            patience+=1
            if patience>=2: break
    training=time.perf_counter()-start;model.load_state_dict(best_state);model.to('cpu').eval()
    out.mkdir(parents=True);model.save_pretrained(out/'model');tokenizer.save_pretrained(out/'tokenizer')
    manifest={'kind':'encoder','model':args.model,'seed':args.seed,'dataset_version':'v1','dataset_sha256':digest(data),
              'manifest_sha256':digest(data.parent/'manifest.json'),'selection_split':'validation','training_seconds':training,
              'peak_process_rss_platform_units':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, 'peak_cuda_bytes':torch.cuda.max_memory_allocated() if device.type=='cuda' else None, 'training_device':str(device),'torch':torch.__version__,'config':vars(args),'positive_class_weights':pos_weight.cpu().tolist(),
              'score_type':'logit; sigmoid gives probability','history':history}
    (out/'run.json').write_text(json.dumps(manifest,indent=2));(out/'labels.json').write_text(json.dumps(CATEGORIES))
    (out/'thresholds.json').write_text(json.dumps(dict.fromkeys(CATEGORIES,0)))
    predictor=Predictor(out);start=time.perf_counter();scores=predictor.scores([r['text'] for r in val])
    manifest['cpu_ms_per_segment']=(time.perf_counter()-start)*1000/len(val)
    from inkwell.common import tune_thresholds
    thresholds=tune_thresholds(np.array([r['label_vec'] for r in val]),scores)
    (out/'thresholds.json').write_text(json.dumps(dict(zip(CATEGORIES,thresholds.tolist())),indent=2))
    (out/'validation_metrics.json').write_text(json.dumps(full_metrics(val,scores,thresholds),indent=2))
    manifest['model_bytes']=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    (out/'run.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__': main()
