"""Evaluate a validated review export; validation reports may guide selection, test is final."""
import argparse,json
from pathlib import Path
from inkwell.common import read_rows,digest,full_metrics,ROOT
from inkwell.predict import Predictor

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);ap.add_argument('--reviewed',required=True)
    ap.add_argument('--split',choices=['validation','test'],required=True);args=ap.parse_args()
    path=Path(args.reviewed);manifest=json.loads(path.with_suffix('.manifest.json').read_text())
    predictor=Predictor(args.run)
    if digest(path)!=manifest['review_sha256'] or manifest['dataset_sha256']!=predictor.run['dataset_sha256']:
        raise ValueError('Review or training dataset checksum mismatch')
    rows=[r for r in read_rows(path) if r['split']==args.split]
    out=Path(args.run)/f'modern_{args.split}_metrics.json'
    if out.exists():raise SystemExit('Evaluation already recorded')
    scores=predictor.scores([r['text'] for r in rows]);result=full_metrics(rows,scores,predictor.thresholds)
    result['review_sha256']=digest(path);result['scope']='Reviewed retained C3PA segments; not a complete-policy silence benchmark'
    out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
