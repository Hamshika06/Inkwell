## Try it

**Live demo:** https://inkwell-846713605562.us-east1.run.app/


Paste a privacy policy, with blank lines between paragraphs, or click **Load a sample policy**. Then choose a model:

| Model | Test macro / micro F1 (OPP-115 v1) | Speed on CPU |
| --- | --- | --- |
| TF-IDF + SVM | 0.700 / 0.746 | under 1 ms per paragraph |
| DistilBERT | 0.703 / 0.769 | ~110 ms per paragraph |
| RoBERTa-base | 0.740 / 0.800 | ~250 ms per paragraph |

Pick **All three** to compare them side by side. The results show:
- every category, with a **SILENT** stamp where no paragraph matched;
- the common questions answered with exact quotes from the policy;
- each paragraph's labels and how close it came to each category's cutoff.

The first visit after a quiet period can take about a minute while the server starts.

Research baseline for coursework, not legal advice. Your text is classified on the server and is not logged or stored.

