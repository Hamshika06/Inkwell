"""Export policy-group review batches, then validate fully reviewed modern judgments."""
import argparse,json
from collections import defaultdict
from pathlib import Path
from inkwell.common import ROOT,CATEGORIES,read_rows,digest


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--reviewed')
    ap.add_argument('--groups-per-split',type=int,default=10);args=ap.parse_args();out=Path(args.out)
    if out.exists(): raise SystemExit('Output exists')
    data=ROOT/'data/versions/v1/classifier.jsonl';rows=read_rows(data);byid={r['id']:r for r in rows}
    if args.reviewed:
        reviewed=read_rows(args.reviewed);groups=defaultdict(set)
        if len({r['id'] for r in reviewed})!=len(reviewed): raise ValueError('Repeated IDs')
        for r in reviewed:
            original=byid[r['id']]
            if original['source']!='c3pa' or original['split'] not in ('validation','test'): raise ValueError('Review must be held-out modern data')
            if any(r[k]!=original[k] for k in ('text','group_id','split','doc_id')): raise ValueError('Source metadata changed')
            judgments=r['judgments']
            if set(judgments)!=set(CATEGORIES) or any(type(v)!=bool for v in judgments.values()): raise ValueError('Every category requires explicit true/false judgment')
            if not r.get('reviewer') or not r.get('adjudicator') or r['reviewer']==r['adjudicator']: raise ValueError('Two distinct human reviewers required')
            r['labels']=[c for c in CATEGORIES if judgments[c]];r['label_vec']=[int(judgments[c]) for c in CATEGORIES];r['label_mask']=[1]*len(CATEGORIES)
            groups[r['group_id']].add(r['split'])
        if not reviewed or any(len(v)>1 for v in groups.values()): raise ValueError('Empty review or group leakage')
        out.write_text(''.join(json.dumps(r)+'\n' for r in reviewed))
        out.with_suffix('.manifest.json').write_text(json.dumps({'dataset_sha256':digest(data),'review_sha256':digest(out),'contract':'full human-reviewed judgments on retained C3PA segments'},indent=2))
    else:
        selected=[]
        for split in ('validation','test'):
            groups=sorted({r['group_id'] for r in rows if r['source']=='c3pa' and r['split']==split})[:args.groups_per_split]
            for r in rows:
                if r['source']=='c3pa' and r['split']==split and r['group_id'] in groups:
                    selected.append({k:r[k] for k in ('id','doc_id','group_id','split','text')} | {'judgments':dict.fromkeys(CATEGORIES,None),'reviewer':'','adjudicator':''})
        out.write_text(''.join(json.dumps(r)+'\n' for r in selected));print(f'Exported {len(selected)} segments for review')

if __name__=='__main__': main()
