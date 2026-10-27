## Try it

**Live demo:** https://inkwell-846713605562.us-east1.run.app/


Paste a privacy policy, with blank lines between paragraphs, or click **Load a sample policy**. Then choose a model:

| Model | Trained on | Speed on CPU |
| --- | --- | --- |
| TF-IDF + SVM | OPP-115 | under 1 ms per paragraph |
| DistilBERT | OPP-115 | ~110 ms per paragraph |
| RoBERTa (C3PA + OPP-115) | OPP-115 and modern C3PA policies | ~230 ms per paragraph |

Pick **All three** to compare them side by side. The results show:
- every category, with a **SILENT** stamp where no paragraph matched;
- the common questions answered with exact quotes from the policy;
- each paragraph's labels and how close it came to each category's cutoff.

The first visit after a quiet period can take about a minute while the server starts.

Research baseline for coursework, not legal advice. Your text is classified on the server and is not logged or stored.

