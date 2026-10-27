import re
from inkwell.common import CATEGORIES

FAQS={"Can I delete or access my data?":"User Access, Edit and Deletion",
      "Do they share my data?":"Third Party Sharing/Collection",
      "How long do they keep my data?":"Data Retention",
      "How do they protect my data?":"Data Security",
      "What choices do I have?":"User Choice/Control"}

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
    segments=segment(text)
    coverage={c:[] for c in CATEGORIES}
    if segments:
        for s,scores in zip(segments,predictor.scores([s["text"] for s in segments])):
            s["labels"]=[c for i,c in enumerate(CATEGORIES) if scores[i]>=predictor.thresholds[i]]
            for c in s["labels"]: coverage[c].append(s["id"])
    return {"text":text,"segments":segments,"coverage":coverage,"faqs":FAQS,
            "empty_message":"No matching clause detected"}
