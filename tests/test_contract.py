import unittest
import numpy as np
import torch
from inkwell.common import CATEGORIES,full_metrics,positive_recall,read_rows,ROOT,key
from inkwell.loss import masked_loss
from inkwell.stage1 import segment,analyze
from collections import defaultdict

class ContractTests(unittest.TestCase):
    def test_positive_only_rejects_f1(self):
        row={'label_vec':[1]+[0]*9,'label_mask':[1]+[0]*9}
        with self.assertRaises(ValueError):full_metrics([row],np.ones((1,10)),np.zeros(10))
        self.assertEqual(positive_recall([row],np.ones((1,10)),np.zeros(10))['per_category'][CATEGORIES[0]]['recall'],1)
    def test_masked_gradient_and_row_weights(self):
        z=torch.zeros((2,2),requires_grad=True);y=torch.tensor([[1.,0.],[0.,1.]])
        loss=masked_loss(z,y,torch.tensor([[1.,0.],[1.,1.]]),torch.tensor([2.,1.]),torch.tensor([3.,1.]))
        loss.backward();self.assertEqual(z.grad[0,1].item(),0)
        self.assertAlmostEqual(z.grad[0,0].item(),-.75)
        self.assertAlmostEqual(z.grad[1,0].item(),.125)
    def test_source_evidence(self):
        text='  🔒 First paragraph.\n\n  Second <script> paragraph.  '
        segments=segment(text);self.assertEqual(len(segments),2)
        for s in segments:self.assertEqual(s['text'],text[s['start']:s['end']])
        class Fake:
            thresholds=np.zeros(10)
            def scores(self,texts):return -np.ones((len(texts),10))
        self.assertTrue(all(not ids for ids in analyze(text,Fake())['coverage'].values()))
    def test_baseline_evidence_and_label_order(self):
        from inkwell.predict import Predictor
        predictor=Predictor(ROOT/'runs/svm-opp115-seed42')
        text='We collect your email address to provide services.\n\nYou can request deletion of your personal information.'
        result=analyze(text,predictor)
        self.assertEqual(set(result['coverage']),set(CATEGORIES))
        self.assertTrue(any(result['coverage'].values()))
        for segment in result['segments']:
            self.assertEqual(segment['text'],text[segment['start']:segment['end']])
    def test_full_metrics_count_false_positives(self):
        rows=[{'label_vec':[1]+[0]*9,'label_mask':[1]*10},
              {'label_vec':[0]*10,'label_mask':[1]*10}]
        result=full_metrics(rows,np.ones((2,10)),np.zeros(10))
        self.assertEqual(result['per_category'][CATEGORIES[0]]['precision'],0.5)
        self.assertLess(result['micro_f1'],1)
    def test_frozen_benchmark(self):
        rows=read_rows(ROOT/'data/versions/v1/classifier.jsonl');texts=defaultdict(set);groups=defaultdict(set)
        for r in rows:texts[key(r['text'])].add(r['split']);groups[r['group_id']].add(r['split'])
        self.assertTrue(all(len(s)==1 for s in texts.values()))
        self.assertTrue(all(len(s)==1 for s in groups.values()))

if __name__=='__main__':unittest.main()
