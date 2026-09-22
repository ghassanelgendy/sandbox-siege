#!/usr/bin/env python3
"""Inline assets/Cube.glb into the title slide of every deck copy.

The deck ships as a single self-contained HTML file — it already base64-embeds
its images — and the two copies live at different directory depths, so a
relative asset path would resolve in one and 404 in the other. Run this
whenever Cube.glb changes:

    python3 scripts/inline_cube.py        # or: make deck-cube
"""
from __future__ import annotations

import base64
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GLB = ROOT / "assets" / "Cube.glb"
DECKS = [
    ROOT / "presentation" / "siege-deck-final.html",
    ROOT / "backend" / "siege" / "presentation.html",
]
HOLDER = re.compile(
    r'(<script id="cube-glb" type="application/octet-stream;base64">)(.*?)(</script>)',
    re.S,
)

def main() -> int:
    if not GLB.exists():
        print(f"missing {GLB.relative_to(ROOT)} — the decks keep their wireframe fallback")
        return 1

    payload = base64.b64encode(GLB.read_bytes()).decode("ascii")
    print(f"{GLB.name}: {GLB.stat().st_size / 1024:.0f} KB → {len(payload) / 1024:.0f} KB base64")

    for deck in DECKS:
        if not deck.exists():
            print(f"  skip {deck.relative_to(ROOT)} (not found)")
            continue
        html = deck.read_text()
        if not HOLDER.search(html):
            print(f"  skip {deck.relative_to(ROOT)} (no cube-glb holder)")
            continue
        deck.write_text(HOLDER.sub(lambda m: m.group(1) + payload + m.group(3), html, count=1))
        print(f"  inlined into {deck.relative_to(ROOT)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
