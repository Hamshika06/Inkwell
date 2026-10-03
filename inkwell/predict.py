import json
from pathlib import Path
import joblib
import numpy as np
from inkwell.common import CATEGORIES

class Predictor:
    def __init__(self, path):
        self.path=Path(path); self.run=json.loads((self.path/"run.json").read_text())
        assert json.loads((self.path/"labels.json").read_text())==CATEGORIES
        self.thresholds=np.array([json.loads((self.path/"thresholds.json").read_text())[c] for c in CATEGORIES])
        if self.run["kind"]=="svm":
            self.bundle=joblib.load(self.path/"model.joblib")
        else:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            self.torch=torch; self.tokenizer=AutoTokenizer.from_pretrained(self.path/"tokenizer")
            self.model=AutoModelForSequenceClassification.from_pretrained(self.path/"model").eval()

    def scores(self, texts):
        if self.run["kind"]=="svm":
            return self.bundle["model"].decision_function(self.bundle["vectorizer"].transform(texts))
        # Window every long segment; max margin across its windows.
        result=[]
        for text in texts:
            encoded=self.tokenizer(text,truncation=True,max_length=512,stride=128,return_overflowing_tokens=True,padding=True,return_tensors="pt")
            encoded.pop("overflow_to_sample_mapping",None)
            with self.torch.no_grad():
                window_scores=[]
                for start in range(0,len(encoded["input_ids"]),8):
                    window_scores.append(self.model(**{k:v[start:start+8] for k,v in encoded.items()}).logits)
                result.append(self.torch.cat(window_scores).max(dim=0).values.numpy())
        return np.array(result)
