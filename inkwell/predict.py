import json
from pathlib import Path
import joblib
import numpy as np

class Predictor:
    """Scores paragraphs with a run folder: run.json, labels.json, thresholds.json and the weights.
    labels are the run's own classes (the ten OPP-115 categories, or the five combined classes)."""
    def __init__(self, path):
        self.path=Path(path); self.run=json.loads((self.path/"run.json").read_text())
        self.labels=json.loads((self.path/"labels.json").read_text())
        self.thresholds=np.array([json.loads((self.path/"thresholds.json").read_text())[c] for c in self.labels])
        # "sigmoid": thresholds were tuned on probabilities, so scores are sigmoid(logit) rather than logits.
        self.sigmoid=self.run.get("output")=="sigmoid"
        if self.run["kind"]=="svm":
            self.bundle=joblib.load(self.path/"model.joblib")
        else:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            self.torch=torch; self.tokenizer=AutoTokenizer.from_pretrained(self.path/"tokenizer")
            self.model=AutoModelForSequenceClassification.from_pretrained(self.path/"model").eval()
            assert self.model.config.num_labels==len(self.labels), (self.model.config.num_labels, self.labels)

    def scores(self, texts):
        if self.run["kind"]=="svm":
            return self.bundle["model"].decision_function(self.bundle["vectorizer"].transform(texts))
        # Window every long segment (512 tokens, 128 overlap); a segment's score is its max logit across
        # windows. Windows from all segments are batched by length so short paragraphs carry little padding.
        if not texts: return np.zeros((0,len(self.labels)))
        encoded=self.tokenizer(list(texts),truncation=True,max_length=512,stride=128,return_overflowing_tokens=True)
        owner=encoded["overflow_to_sample_mapping"]; ids=encoded["input_ids"]
        order=sorted(range(len(ids)),key=lambda i:len(ids[i]))
        logits=[None]*len(ids)
        with self.torch.no_grad():
            for start in range(0,len(order),16):
                chunk=order[start:start+16]
                batch=self.tokenizer.pad({"input_ids":[ids[i] for i in chunk]},return_tensors="pt")
                out=self.model(**batch).logits.numpy()
                for i,row in zip(chunk,out): logits[i]=row
        result=np.full((len(texts),len(self.labels)),-np.inf)
        for i,row in enumerate(logits): result[owner[i]]=np.maximum(result[owner[i]],row)
        return 1/(1+np.exp(-result)) if self.sigmoid else result
