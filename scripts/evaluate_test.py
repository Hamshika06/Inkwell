"""One final test evaluation after a run is selected on validation."""
import argparse,json
from pathlib import Path
from inkwell.common import ROOT,read_rows,digest,full_metrics,positive_recall
from inkwell.predict import Predictor

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--run",required=True); args=ap.parse_args()
    out=Path(args.run)/"test_metrics.json"
    if out.exists(): raise SystemExit("Test already evaluated for this run")
    predictor=Predictor(args.run); data=ROOT/"data/versions/v1/classifier.jsonl"
    if digest(data)!=predictor.run["dataset_sha256"]: raise ValueError("Dataset changed since training")
    rows=read_rows(data); result={}
    for source in ("opp115","c3pa"):
        part=[r for r in rows if r["source"]==source and r["split"]=="test"]
        scores=predictor.scores([r["text"] for r in part])
        result[source]=(full_metrics if source=="opp115" else positive_recall)(part,scores,predictor.thresholds)
    out.write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))

if __name__=="__main__": main()
