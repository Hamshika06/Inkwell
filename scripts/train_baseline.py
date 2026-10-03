"""Fit TF-IDF + one-vs-rest LinearSVC using OPP-115 train and validation only."""
import argparse
import json
import platform
import resource
import time
from pathlib import Path
import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.multiclass import OneVsRestClassifier
from sklearn.svm import LinearSVC
from inkwell.common import verified_dataset, ROOT, CATEGORIES, read_rows, digest, tune_thresholds, full_metrics

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--seed",type=int,default=42)
    ap.add_argument("--out",default="runs/svm-opp115-seed42"); args=ap.parse_args()
    out=Path(args.out)
    if out.exists(): raise SystemExit("Run exists; choose a new output directory")
    data=verified_dataset(); rows=read_rows(data)
    train=[r for r in rows if r["source"]=="opp115" and r["split"]=="train"]
    val=[r for r in rows if r["source"]=="opp115" and r["split"]=="validation"]
    vectorizer=TfidfVectorizer(ngram_range=(1,2),min_df=2,max_features=50000,sublinear_tf=True)
    start=time.perf_counter(); x=vectorizer.fit_transform([r["text"] for r in train])
    model=OneVsRestClassifier(LinearSVC(C=1.0,class_weight="balanced",random_state=args.seed))
    model.fit(x,np.array([r["label_vec"] for r in train])); training=time.perf_counter()-start
    start=time.perf_counter(); scores=model.decision_function(vectorizer.transform([r["text"] for r in val])); latency=(time.perf_counter()-start)*1000/len(val)
    thresholds=tune_thresholds(np.array([r["label_vec"] for r in val]),scores)
    out.mkdir(parents=True); joblib.dump({"vectorizer":vectorizer,"model":model},out/"model.joblib")
    (out/"thresholds.json").write_text(json.dumps(dict(zip(CATEGORIES,thresholds.tolist())),indent=2))
    (out/"labels.json").write_text(json.dumps(CATEGORIES,indent=2))
    (out/"validation_metrics.json").write_text(json.dumps(full_metrics(val,scores,thresholds),indent=2))
    manifest={"kind":"svm", "seed":args.seed,"dataset_version":"v1", "dataset_sha256":digest(data),
              "manifest_sha256":digest(data.parent/"manifest.json"),"train_source":"opp115", "selection_split":"validation",
              "score_type":"SVM decision margin, not probability", "peak_process_rss_platform_units":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,"training_seconds":training,"cpu_ms_per_segment":latency,
              "model_bytes":(out/"model.joblib").stat().st_size,"python":platform.python_version(),"sklearn":sklearn.__version__}
    (out/"run.json").write_text(json.dumps(manifest,indent=2)); print(json.dumps(manifest,indent=2))

if __name__=="__main__": main()
