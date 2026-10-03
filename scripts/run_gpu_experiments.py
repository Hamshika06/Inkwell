"""Staged GPU experiments. Dataset and metrics remain identical across runs."""
import argparse,json,subprocess,sys
from pathlib import Path
import numpy as np
import torch


def call(module,*args):
    subprocess.run([sys.executable,'-m',module,*map(str,args)],check=True)


def metric(path):
    return json.loads((path/'validation_metrics.json').read_text())['macro_f1']


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default='runs/gpu');ap.add_argument('--epochs',type=int,default=10)
    args=ap.parse_args()
    if not torch.cuda.is_available():raise SystemExit('CUDA GPU required for this experiment matrix')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    def train(name,model,lr,source='opp115',weight=0.1,seed=42):
        path=out/name
        if (path/'validation_metrics.json').exists():return path
        call('scripts.train_encoder','--model',model,'--lr',lr,'--source',source,'--c3pa-weight',weight,
             '--seed',seed,'--epochs',args.epochs,'--out',path)
        return path
    baselines={}
    for seed in (42,13,7):
        path=out/f'svm-seed{seed}'
        if not (path/'validation_metrics.json').exists():call('scripts.train_baseline','--seed',seed,'--out',path)
        baselines[seed]=path
    backbones=[('distilbert-base-uncased',5e-5),('roberta-base',2e-5)]
    first=[train(f'{m}-opp115-seed42',m,lr) for m,lr in backbones]
    index=max(range(2),key=lambda i:metric(first[i]));model,lr=backbones[index]
    supplements=[train(f'{model}-combined-weight{w}-seed42',model,lr,'combined',w) for w in (0.1,1.0)]
    best_weight=(0.1,1.0)[max(range(2),key=lambda i:metric(supplements[i]))]
    shortlisted={'svm':list(baselines.values()), 'encoder_opp115':[first[index]],
                 'encoder_combined':[supplements[(0.1,1.0).index(best_weight)]]}
    for seed in (13,7):
        shortlisted['encoder_opp115'].append(train(f'{model}-opp115-seed{seed}',model,lr,seed=seed))
        shortlisted['encoder_combined'].append(train(f'{model}-combined-weight{best_weight}-seed{seed}',model,lr,'combined',best_weight,seed))
    summary={name:{'runs':[str(p) for p in paths],'validation_macro_f1_mean':float(np.mean([metric(p) for p in paths])),
                   'validation_macro_f1_std':float(np.std([metric(p) for p in paths],ddof=1))}
             for name,paths in shortlisted.items()}
    selected=max(summary,key=lambda name:summary[name]['validation_macro_f1_mean'])
    representative=shortlisted[selected][0]  # seed 42, chosen in advance rather than best seed
    (out/'selection.json').write_text(json.dumps({'criterion':'mean OPP-115 validation macro-F1 across seeds 42,13,7',
                                                'selected_configuration':selected,'selected_seed42_run':str(representative),'summary':summary},indent=2))
    if not (representative/'test_metrics.json').exists():call('scripts.evaluate_test','--run',representative)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
