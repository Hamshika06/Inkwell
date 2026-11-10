import re
from inkwell.common import CATEGORIES
from inkwell.report import build_report

# One common question per class of the five-class model (configs/five_class_mapping.json).
FAQS={"What do they collect about me?":"Data Collection & Use",
      "Do they share or sell my data?":"Data Sharing",
      "Can I delete my data or opt out?":"User Rights & Choices",
      "How long do they keep it, and how is it protected?":"Data Security & Retention",
      "Will they tell me when the policy changes?":"Policy Scope & Changes"}

def segment(text):
    # Blank lines delimit paragraphs; trim boundaries without altering evidence text.
    boundaries=[0]+[m.end() for m in re.finditer(r"\n[ \t]*\n",text)]+[len(text)]
    result=[]
    for a,b in zip(boundaries,boundaries[1:]):
        while a<b and text[a].isspace(): a+=1
        while b>a and text[b-1].isspace(): b-=1
        if a<b: result.append({"id":len(result),"start":a,"end":b,"text":text[a:b]})
    return result

def analyze(text,predictor):
    """Label each paragraph with the predictor's classes and build the report card."""
    labels=getattr(predictor,"labels",CATEGORIES)  # Research predictors without labels use the ten OPP-115 categories.
    segments=segment(text)
    coverage={c:[] for c in labels}
    if segments:
        for s,scores in zip(segments,predictor.scores([s["text"] for s in segments])):
            s["labels"]=[c for i,c in enumerate(labels) if scores[i]>=predictor.thresholds[i]]
            for c in s["labels"]: coverage[c].append(s["id"])
    faqs={q:c for q,c in FAQS.items() if c in coverage}
    return {"text":text,"segments":segments,"coverage":coverage,"faqs":faqs,
            "empty_message":"No matching clause detected","report":build_report(segments)}
