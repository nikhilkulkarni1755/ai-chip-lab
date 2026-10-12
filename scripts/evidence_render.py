#!/usr/bin/env python3
"""Render results/evidence/*.txt (real, scrubbed terminal output) into terminal-styled PNGs.

Not an OS screenshot: the text is drawn with Pillow, so nothing but the file's content can appear.
Each file is privacy-checked first (same patterns as the pre-commit hook); failing files are refused.

Usage (needs Pillow; use the lab-local venv):  .venv-demo/bin/python scripts/evidence_render.py [--lab DIR] [--out DIR]
Writes <out>/demo/assets/evidence/<name>.png and prints one line per file. Exit 1 if any file was refused.
"""
import argparse
import glob
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evidence_privacy import scan_text  # noqa: E402

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin  # noqa: E402

FONTS = [("/System/Library/Fonts/Menlo.ttc", 0), ("/System/Library/Fonts/Monaco.ttf", 0),
         ("/System/Library/Fonts/Supplemental/Courier New.ttf", 0)]
MAX_LINES, MAX_COLS, SIZE = 60, 118, 15
BG, FG, BAR, DIM = (22, 24, 29), (214, 222, 235), (46, 50, 60), (130, 140, 155)


def load_font(size):
    for p, i in FONTS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size, index=i)
            except Exception:
                pass
    return ImageFont.load_default()


def colour(line):
    u = line.upper()
    if "FAIL" in u or "ERROR" in u or "MISMATCH" in u and "0 MISMATCH" not in u:
        return (255, 123, 114)
    if "PASS" in u or " OK" in u or "PROVED" in u or "SUCCESS" in u:
        return (126, 231, 135)
    if line.startswith("$"):
        return (121, 192, 255)
    return FG


def render(txt_path, out_path):
    text = open(txt_path, encoding="utf-8", errors="replace").read()
    bad = scan_text(text)
    if bad:
        return "REFUSED privacy check: %s" % ", ".join("line %d (%s)" % b for b in bad[:5])
    lines = text.expandtabs(4).rstrip("\n").splitlines()
    note = None
    if len(lines) > MAX_LINES:
        note = "[... %d more lines not shown; full text in results/evidence/%s ...]" % (
            len(lines) - MAX_LINES, os.path.basename(txt_path))
        lines = lines[:MAX_LINES]
    lines = [l if len(l) <= MAX_COLS else l[:MAX_COLS - 1] + "…" for l in lines]
    if note:
        lines.append(note)
    font, tfont = load_font(SIZE), load_font(13)
    cw = font.getlength("M")
    lh = SIZE + 5
    pad, bar = 16, 34
    w = int(max(cw * max([len(l) for l in lines] + [60]) + 2 * pad, 640))
    h = bar + 2 * pad + lh * max(len(lines), 1)
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, bar], fill=BAR)
    for k, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([14 + 22 * k, 11, 26 + 22 * k, 23], fill=c)
    title = os.path.splitext(os.path.basename(txt_path))[0]
    d.text((w / 2 - tfont.getlength(title) / 2, 9), title, font=tfont, fill=DIM)
    y = bar + pad
    for l in lines:
        d.text((pad, y), l, font=font, fill=DIM if l.startswith("[...") else colour(l))
        y += lh
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    meta = PngImagePlugin.PngInfo()
    meta.add_text("src_sha256", hashlib.sha256(open(txt_path, "rb").read()).hexdigest())  # lets demo_check prove the PNG is current
    im.save(out_path, optimize=True, pnginfo=meta)
    return "ok %dx%d" % (w, h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", default=os.environ.get("LAB", os.path.expanduser("~/ai-chip-lab")))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or a.lab
    refused = 0
    for t in sorted(glob.glob(os.path.join(a.lab, "results/evidence/*.txt"))):
        name = os.path.splitext(os.path.basename(t))[0]
        dst = os.path.join(out, "demo/assets/evidence", name + ".png")
        r = render(t, dst)
        refused += r.startswith("REFUSED")
        print("%-45s %s" % (name, r))
    sys.exit(1 if refused else 0)


if __name__ == "__main__":
    main()
