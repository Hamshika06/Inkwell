"""Freeze v1: quarantine every copy of normalized text crossing source splits."""
import json
from collections import defaultdict, Counter
from pathlib import Path
from inkwell.common import ROOT, CATEGORIES, read_rows, key, digest

def main():
    src = ROOT / "data/processed/combined_classifier.jsonl"
    out = ROOT / "data/versions/v1"
    if out.exists():
        raise SystemExit("v1 already exists; create a new version rather than overwrite a benchmark")
    rows = read_rows(src); splits = defaultdict(set)
    for r in rows: splits[key(r["text"])].add(r["split"])
    overlap = {k for k,v in splits.items() if len(v)>1}
    dropped = [r for r in rows if key(r["text"]) in overlap]
    kept = [r for r in rows if key(r["text"]) not in overlap]
    ids = {r["id"] for r in kept}
    ext = [r for r in read_rows(ROOT / "data/processed/combined_extraction.jsonl") if r["id"] in ids]
    groups = defaultdict(set)
    for r in kept:
        groups[r["group_id"]].add(r["split"])
        if r["source"] == "c3pa" and r["label_mask"] != r["label_vec"]:
            raise ValueError("C3PA must retain positive-only supervision")
    assert all(len(s)==1 for s in groups.values())
    out.mkdir(parents=True)
    for name, data in [("classifier.jsonl",kept),("extraction.jsonl",ext),("quarantine.jsonl",dropped)]:
        (out/name).write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in data))
    manifest = {"version":"v1", "categories":CATEGORIES, "source_sha256":digest(src),
                "classifier_sha256":digest(out/"classifier.jsonl"), "extraction_sha256":digest(out/"extraction.jsonl"),
                "schema_sha256":digest(ROOT/"configs/label_schema.json"), "mapping_sha256":digest(ROOT/"configs/label_mapping.json"),
                "duplicate_policy":"quarantine all copies of normalized texts crossing splits; original policy/company splits preserved",
                "quarantined_texts":len(overlap), "quarantined_rows":len(dropped),
                "counts":dict(Counter(r["source"]+"/"+r["split"] for r in kept)),
                "splits":{g:next(iter(s)) for g,s in sorted(groups.items())},
                "evaluation":{"opp115":"full-label precision/recall/F1", "c3pa":"positive-label recall only", "selection":"validation only; test once after configuration frozen"}}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps({k:v for k,v in manifest.items() if k!='splits'},indent=2))

if __name__ == "__main__": main()
