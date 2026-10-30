#!/usr/bin/python3
"""Find text on screen with OCR (tesseract) and return where it is, in logical desktop px.

  lcu ocr "Save as" --window class:org.kde.kate      # phrase in one window (raised first)
  lcu ocr Medium --area 0 0 1536 960                 # in an area
  lcu ocr --dump --window class:codium               # every recognised line with its box

Prints JSON matches: text, confidence, box and centre; click the centre with `lcu input`.
For apps the accessibility tree does not cover (all of COSMIC's own apps, Electron and
GTK4 apps whose a11y boxes are offset, anything started before accessibility was on).
OCR can misread small or stylised text, and the same words may be in another window:
never use it alone to confirm that a dialog opened. Matching is case-insensitive over
consecutive words on one line. --window/--area/--screen as in `lcu capture shot`.
"""
import argparse
import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

from lcu_env import tool  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", nargs="?")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--window")
    g.add_argument("--area", nargs=4, type=float)
    g.add_argument("--screen")
    ap.add_argument("--no-raise", action="store_true")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--min-conf", type=float, default=50)
    args = ap.parse_args()
    if not args.text and not args.dump:
        sys.exit("give TEXT or --dump")

    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "ocr.png"
        cmd = tool("capture", "shot", png)
        if args.window:
            cmd += ["--window", args.window] + (["--no-raise"] if args.no_raise else [])
        elif args.area:
            cmd += ["--area", *map(str, args.area)]
        else:
            cmd += ["--screen", args.screen]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stdout.strip() or r.stderr.strip() or "lcu capture shot failed")
        shot = json.loads(r.stdout)
        if not shutil.which("tesseract"):
            sys.exit("OCR needs tesseract with English data (Fedora: tesseract tesseract-langpack-eng; "
                     "Arch: tesseract tesseract-data-eng; Debian/Ubuntu: tesseract-ocr)")
        # Two passes: tesseract misses some light-on-dark or ringed text in colour (a focused
        # "No" button with a red ring in a dark theme) that it reads in greyscale, and the
        # reverse happens for coloured text, so read both and merge the results below.
        grey = Path(td) / "grey.png"
        im = GdkPixbuf.Pixbuf.new_from_file(str(png))
        im.saturate_and_pixelate(im, 0.0, False)
        im.savev(str(grey), "png", [], [])
        lines = {}
        for n, src in enumerate((grey, png)):
            tsv = subprocess.run(["tesseract", str(src), "-", "--psm", "11", "tsv"],
                                 capture_output=True, text=True, check=True).stdout
            for w in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
                if w["level"] == "5" and w["text"].strip() and float(w["conf"]) >= args.min_conf:
                    lines.setdefault((n, w["block_num"], w["par_num"], w["line_num"]), []).append(w)
    ox, oy = shot["logical_region"][:2] if shot["logical_region"] else (0, 0)
    f = shot["pixels_per_logical"]

    def box(ws):
        x0 = min(int(w["left"]) for w in ws); y0 = min(int(w["top"]) for w in ws)
        x1 = max(int(w["left"]) + int(w["width"]) for w in ws); y1 = max(int(w["top"]) + int(w["height"]) for w in ws)
        X, Y, W, H = ox + x0 / f, oy + y0 / f, (x1 - x0) / f, (y1 - y0) / f
        return {"x": round(X, 1), "y": round(Y, 1), "width": round(W, 1), "height": round(H, 1),
                "center": [round(X + W / 2), round(Y + H / 2)]}

    out = []
    if args.dump:
        for ws in lines.values():
            out.append({"text": " ".join(w["text"] for w in ws), "box": box(ws)})
    else:
        want = args.text.lower().split()

        def segments(ws):
            # OCR joins neighbouring controls into one line ("Yes © No" when a button is
            # hovered); split where the gap between words is wider than ~1.5 text heights.
            segs, cur = [], []
            for w in sorted(ws, key=lambda w: int(w["left"])):
                if cur:
                    gap = int(w["left"]) - (int(cur[-1]["left"]) + int(cur[-1]["width"]))
                    if gap > 1.5 * max(int(w["height"]), int(cur[-1]["height"])):
                        segs.append(cur); cur = []
                cur.append(w)
            return segs + ([cur] if cur else [])

        for line in lines.values():
            # icons are often read as stray symbols ("© No", "| File"): drop tokens with no letters/digits
            line = [w for w in line if any(ch.isalnum() for ch in w["text"])]
            for ws in segments(line):
                toks = ["".join(ch for ch in w["text"].lower() if ch.isalnum() or ch in "-_./+") for w in ws]
                for i in range(len(toks) - len(want) + 1):
                    if toks[i:i + len(want)] == want:
                        seg = ws[i:i + len(want)]
                        out.append({"text": " ".join(w["text"] for w in seg), "alone": len(toks) == len(want),
                                    "conf": round(min(float(w["conf"]) for w in seg)), "box": box(seg)})
        # text standing alone (a button or menu entry) before the same words inside a sentence
        out.sort(key=lambda m: (not m["alone"], -m["conf"]))
    # the two passes mostly read the same things: keep the first of each text at one place
    kept = []
    for m in out:
        if not any(k["text"].lower() == m["text"].lower() and abs(k["box"]["center"][0] - m["box"]["center"][0]) <= 6
                   and abs(k["box"]["center"][1] - m["box"]["center"][1]) <= 6 for k in kept):
            kept.append(m)
    out = kept
    print(json.dumps({"matches": out, "screenshot_scale": f}, indent=1))
    sys.exit(0 if out else 1)


if __name__ == "__main__":
    main()
