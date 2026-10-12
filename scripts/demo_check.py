#!/usr/bin/env python3
"""demo_check.py - verify generated demo: every relative img src / href resolves; markdown image links resolve; privacy scan.
Usage: demo_check.py [--lab DIR] [--out DIR]   (exit 1 on any problem)"""
import argparse, glob, hashlib, os, re, sys
from html.parser import HTMLParser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evidence_privacy import scan_text

class P(HTMLParser):
    def __init__(s): super().__init__(); s.refs = []
    def handle_starttag(s, t, a):
        for k, v in a:
            if k in ("src", "href") and v: s.refs.append(v)

ap = argparse.ArgumentParser()
ap.add_argument("--lab", default=os.environ.get("LAB", os.path.expanduser("~/ai-chip-lab")))
ap.add_argument("--out", default=None)
a = ap.parse_args(); out = a.out or a.lab
bad = 0
def ok(rel, base):
    rel = rel.split("#")[0]
    if not rel: return True
    return any(os.path.exists(os.path.normpath(os.path.join(r, base, rel))) for r in (out, a.lab))
html = open(os.path.join(out, "demo/index.html"), encoding="utf-8").read()
p = P(); p.feed(html)
n = 0
for r in p.refs:
    if re.match(r"^(https?:|#|mailto:)", r): continue
    n += 1
    if not ok(r, "demo"): print("BROKEN html ref:", r); bad += 1
for f, base in (("README.md", ""), ("demo/README.md", "demo")):
    t = open(os.path.join(out, f), encoding="utf-8").read()
    for m in re.finditer(r"!?\[[^\]]*\]\(([^)#]+)\)", t):
        r = m.group(1)
        if re.match(r"^https?:", r): continue
        n += 1
        if not ok(r, base): print("BROKEN md ref in %s: %s" % (f, r)); bad += 1
    for ln, k in scan_text(t): print("PRIVACY %s:%d %s" % (f, ln, k)); bad += 1
for ln, k in scan_text(html): print("PRIVACY index.html:%d %s" % (ln, k)); bad += 1
# evidence PNGs must be rendered from the current text (content hash stored in the PNG, robust on a fresh clone)
try:
    from PIL import Image
except ImportError:
    Image = None
for t in sorted(glob.glob(os.path.join(a.lab, "results/evidence/*.txt"))):
    name = os.path.splitext(os.path.basename(t))[0]
    png = os.path.join(out, "demo/assets/evidence", name + ".png")
    if not os.path.exists(png):
        print("MISSING evidence PNG:", name); bad += 1; continue
    if Image is None:
        continue
    want = hashlib.sha256(open(t, "rb").read()).hexdigest()
    have = Image.open(png).text.get("src_sha256")
    if have != want:
        print("STALE evidence PNG (rendered from different text):", name); bad += 1
print("checked %d refs, %d problem(s)" % (n, bad)); sys.exit(1 if bad else 0)
