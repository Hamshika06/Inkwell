"""One-off: turn my read-through decisions (indices into the triage lists) into label_corrections.csv."""
import csv, json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
U = [json.loads(l) for l in open(ROOT/"data/interim/c3pa_v2/c3pa.jsonl", encoding="utf-8")]
PC, AD = "Policy Change", "User Access, Edit and Deletion"
UC = "User Choice/Control"
strictPC = re.compile(r"(chang|updat|revis|modif|amend)\w*.{0,80}(polic|notice|statement|terms|practices)|(polic|notice|statement|terms|practices).{0,80}(chang|updat|revis|modif|amend)|last (updated|modified|revised|reviewed)|effective (date|as of)|date of (this|the) (last|latest)|reserve the right|material (change|revision)", re.I)
pcnot = [u for u in U if PC in u["labels"] and not strictPC.search(u["text"])]
strict = re.compile(r"delet|eras|rectif|correct|right to (know|access|be informed|request|obtain)|access|request|know|copy|portab|remov", re.I)
legit = re.compile(r"categories of|business or commercial purpose|commercial purposes?|purposes? (for which|of the processing)|specific pieces|(you|consumers?|residents?) (have|has) the right|the right to|right to be informed|you (may|can) (ask|review|obtain|update|change|edit|view)|inform you about|sources? (of|from which)|recipients|personal (data|information) (we have|that we)|retention period", re.I)
adnot = [u for u in U if AD in u["labels"] and not strict.search(u["text"]) and not legit.search(u["text"])]
assert len(pcnot) == 45 and len(adnot) == 277

rows = []
# ---- Policy Change (45 rows read)
pc_keep = {2, 7, 15, 19, 26, 28, 37, 38, 44}
pc_set = {13: [UC], 25: [UC], 27: [AD], 40: [UC], 42: [UC]}
for i, u in enumerate(pcnot):
    if i in pc_keep: continue
    if i in pc_set:
        rows.append((u["unit_id"], "SET", "|".join(pc_set[i]), "Policy Change label wrong; text is about " + pc_set[i][0]))
    else:
        rows.append((u["unit_id"], "DROP", "", "Policy Change on intro/scope/unrelated text, not a policy-change notice"))
# ---- Access/Deletion (277 rows read)
ad_keep = set("""3 6 11 13 15 16 30 33 34 54 56 66 67 75 78 88 89 92 103 104 159 161 169 208 210 211 212 213 214 216 218 219 220 223
227 229 230 235 241 231 232 240 246 248 251 253 255 256 257 258 259 262 263 264 265 267 268 269 270 271 272 273 274 275 276 2 261 266""".split())
ad_keep = {int(x) for x in ad_keep}
drop_all = {14, 50, 51, 52, 55, 57, 65, 217, 224, 243, 244, 245, 247}
for i, u in enumerate(adnot):
    if i in ad_keep: continue
    rest = [l for l in u["labels"] if l != AD]
    if i in drop_all or not rest:
        rows.append((u["unit_id"], "DROP", "", "Access/Deletion label wrong (collection/sharing/ads/cookie/junk text); no valid label left"))
    else:
        rows.append((u["unit_id"], "SET", "|".join(rest), "Access/Deletion label wrong; other label(s) kept"))
out = ROOT/"data/interim/c3pa_v2/label_corrections.csv"
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f); w.writerow(["unit_id", "action", "labels_after", "reason", "reviewed_by"])
    for r in rows: w.writerow([*r, "Claude read-through (not human annotators)"])
from collections import Counter
print(Counter((r[1], r[3][:40]) for r in rows)); print(len(rows), "corrections ->", out)
