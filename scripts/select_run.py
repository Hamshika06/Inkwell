"""Record a selection based only on validation metrics, before final test evaluation."""
import argparse,json
from pathlib import Path
from inkwell.common import digest


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runs',nargs='+',required=True);ap.add_argument('--out',required=True)
    args=ap.parse_args();out=Path(args.out)
    if out.exists():raise SystemExit('Selection already frozen')
    candidates=[];datasets=set()
    for name in args.runs:
        path=Path(name);run=json.loads((path/'run.json').read_text());datasets.add(run['dataset_sha256'])
        metrics=json.loads((path/'validation_metrics.json').read_text())
        candidates.append({'run':str(path),'validation_macro_f1':metrics['macro_f1'],
                           'run_sha256':digest(path/'run.json'),'thresholds_sha256':digest(path/'thresholds.json')})
    if len(datasets)!=1:raise ValueError('Candidate datasets differ')
    selected=max(candidates,key=lambda r:r['validation_macro_f1'])
    out.write_text(json.dumps({'selection_metric':'OPP-115 validation macro-F1','selected':selected,'candidates':candidates},indent=2))
    print(selected['run'])

if __name__=='__main__':main()
