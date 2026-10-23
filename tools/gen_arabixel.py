#!/usr/bin/env python3
"""
gen_arabixel.py -- turn Arabixel Basic's Arabic glyphs into the C table in
fonts/arabixel/arabixel_tab.c.

Arabixel Basic (https://arabiandev.itch.io/arabixel-basic-font) is an 11px
pixel font drawn as outlines on a 2048/11 unit grid, so each glyph is
recovered exactly by testing the centre of every pixel cell against the
outline. The font file is committed beside the table
(fonts/arabixel/Arabixel_Basic.ttf), and this script is run by hand
when it changes, like gen_ark12.py.

Kept: the Arabic block (U+0600..06FF) and the two Presentation Forms
blocks, which hold the joined shapes -- initial, medial, final, isolated
and the lam-alef ligatures. The font has no GSUB, so choosing among those
is arabixel_shape()'s job, not the font's. Left out: the combining marks
(U+064B..065F, U+0670), which arabixel_shape() drops because gfx.c has no
way to draw one over the letter before it, and the font's ASCII, which
ark12 draws.

Rows. ark12 is 12 rows with its baseline under row 9. Arabixel letters
stand on font row y=1, so they are mapped row = 9 - y: a letter's foot
on ark12's last row above the baseline, rows y=9..-2 kept. Eight glyphs
reach y=-3 (hamza below, the jeem family's final tails) and two y=10
(lam-alef with madda or hamza above). Each loses one row so it fits:
an empty row nearest the overflow when there is one -- the gap between
a letter and its hamza, or between lam-alef and its madda -- else the
row named in SQUEEZE, a repeated stroke of a tail. Nothing is clipped.

Advance. The glyph's width is the font's own advance, and gfx.c steps by
exactly that for these glyphs, with no extra column: the joins only meet
if nothing is put between them, and the advance already carries the
font's spacing on a side that does not join.

Usage:
    ./tools/gen_arabixel.py

Requires fontTools (pip install fonttools) -- only to run this, never to
build the firmware.

SPDX-License-Identifier: MIT
"""

import hashlib
import os
import sys

from fontTools.pens.pointInsidePen import PointInsidePen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
COMP = os.path.join(HERE, "..", "fonts", "arabixel")
TTF = os.path.join(COMP, "Arabixel_Basic.ttf")
OUT = os.path.join(COMP, "arabixel_tab.c")

H = 12
TOP, BOT = 9, -2            # font rows kept, row = TOP - y
RANGES = ((0x0600, 0x06FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
MARKS = set(range(0x064B, 0x0660)) | {0x0670}

# A row to remove from a glyph that has no empty row to give up: the
# second of two rows of the same vertical stroke in a final jeem, hah or
# khah's tail.
SQUEEZE = {0xFE9E: -2, 0xFEA2: -2, 0xFEA6: -2}

# The Persian letters Arabixel Basic does not have -- peh, tcheh, jeh,
# keheh, gaf, farsi yeh -- drawn here from its own glyphs: a copy of the
# nearest Arabic letter's form, with pixels taken away and put in, as
# (row, column) from the top left of the 12-row bitmap. Not ArabianDev's
# drawing; fonts/arabixel/README.md says which forms are whose, and that
# no Persian reader has checked them yet.
#
#   peh    beh with three dots below for one
#   tcheh  jeem with three dots for one (initial, medial, isolated);
#          final is jeem's own -- its dot cannot be told from its tail
#   jeh    zain with three dots above for one
#   keheh  kaf: initial and medial are the same shape; isolated and
#          final lose kaf's inner mark and gain the slant at the top
#   gaf    keheh with a second stroke beside the first (isolated and
#          final: two slants) or above it (initial and medial: two bars)
#   yeh    alef maksura's isolated and final, yeh's initial and medial
def dots_below(r, c):
    return ({(r, c)}, {(r, c - 1), (r, c + 1), (r + 1, c)})

DRAWN = [
    # (cp, from, remove, add); a later entry may copy an earlier one
    (0xFB56, 0xFE8F, *dots_below(10, 3)),               # peh isolated
    (0xFB57, 0xFE90, *dots_below(10, 3)),               # final
    (0xFB58, 0xFE91, {(10, 2)}, {(10, 0), (10, 2), (11, 1)}),   # initial: 3 wide
    (0xFB59, 0xFE92, *dots_below(10, 1)),               # medial
    (0xFB7A, 0xFE9D, {(8, 2)}, {(8, 0), (8, 2), (9, 1)}),       # tcheh isolated
    (0xFB7B, 0xFE9E, set(), set()),                     # final: jeem's
    (0xFB7C, 0xFE9F, *dots_below(10, 3)),               # initial
    (0xFB7D, 0xFEA0, *dots_below(10, 3)),               # medial
    (0xFB8A, 0xFEAF, {(5, 1)}, {(4, 1), (5, 0), (5, 2)}),       # jeh isolated
    (0xFB8B, 0xFEB0, {(5, 1)}, {(4, 1), (5, 0), (5, 2)}),       # final
    (0xFB8E, 0xFED9, {(4, 3), (5, 4), (6, 3), (6, 4)}, {(2, 2), (1, 3)}),  # keheh isolated
    (0xFB8F, 0xFEDA, {(4, 4), (5, 5), (6, 4), (6, 5)}, {(3, 3), (2, 4)}),  # final
    (0xFB90, 0xFEDB, set(), set()),                     # initial: kaf's
    (0xFB91, 0xFEDC, set(), set()),                     # medial: kaf's
    (0xFB92, 0xFB8E, set(), {(2, 4), (1, 5)}),          # gaf isolated: a second slant
    (0xFB93, 0xFB8F, set(), {(3, 5), (2, 6)}),          # final
    (0xFB94, 0xFEDB, set(), {(2, 1), (2, 2), (2, 3)}),  # initial
    (0xFB95, 0xFEDC, set(), {(2, 2), (2, 3), (2, 4)}),  # medial
    (0xFBFC, 0xFEEF, set(), set()),                     # farsi yeh isolated
    (0xFBFD, 0xFEF0, set(), set()),                     # final
    (0xFBFE, 0xFEF3, set(), set()),                     # initial
    (0xFBFF, 0xFEF4, set(), set()),                     # medial
]
# The letters themselves, as their isolated forms.
DRAWN_BASE = {0x067E: 0xFB56, 0x0686: 0xFB7A, 0x0698: 0xFB8A,
              0x06A9: 0xFB8E, 0x06AF: 0xFB92, 0x06CC: 0xFBFC}


def draw(have, cp, src, remove, add):
    w, rows = have[src]
    rows = list(rows)
    for r, c in remove:
        bit = 1 << (w - 1 - c)
        if not rows[r] & bit:
            sys.exit(f"U+{cp:04X}: ({r},{c}) is not set in U+{src:04X}")
        rows[r] &= ~bit
    for r, c in add:
        if not 0 <= c < w or not 0 <= r < H:
            sys.exit(f"U+{cp:04X}: ({r},{c}) is outside U+{src:04X}")
        rows[r] |= 1 << (w - 1 - c)
    return w, rows


def raster(gs, name, w, unit):
    rows = {}
    for y in range(12, -8, -1):
        for x in range(w):
            pen = PointInsidePen(gs, ((x + 0.5) * unit, (y - 0.5) * unit))
            gs[name].draw(pen)
            if pen.getResult():
                rows[y] = rows.get(y, 0) | (1 << x)
    return rows


def fit(cp, rows):
    """Remove rows until the glyph spans TOP..BOT; return {y: bits}."""
    if not rows:
        return rows
    # bits[k] is font row top - k
    top = max(rows)
    bits = [rows.get(y, 0) for y in range(top, min(rows) - 1, -1)]
    y_of = lambda k: top - k

    while top > TOP:
        # the empty row nearest the top: what is above it moves down
        k = next((k for k in range(len(bits)) if bits[k] == 0 and y_of(k) > 0), None)
        if k is None:
            sys.exit(f"U+{cp:04X}: too tall and no empty row to remove")
        del bits[k]
        top -= 1
    while y_of(len(bits) - 1) < BOT:
        # the empty row nearest the bottom: what is below it moves up
        k = next((k for k in range(len(bits) - 1, -1, -1) if bits[k] == 0 and y_of(k) <= 0), None)
        if k is None and cp in SQUEEZE:
            k = top - SQUEEZE.pop(cp)
        if k is None:
            sys.exit(f"U+{cp:04X}: too deep and no row to remove")
        del bits[k]
    return {y_of(k): b for k, b in enumerate(bits) if b}


def main():
    font = TTFont(TTF)
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    unit = font["head"].unitsPerEm / 11

    glyphs = []
    for cp in sorted(cmap):
        if not any(lo <= cp <= hi for lo, hi in RANGES) or cp in MARKS:
            continue
        name = cmap[cp]
        w = round(hmtx[name][0] / unit)
        if w <= 0 or w > 16:
            continue
        rows = fit(cp, raster(gs, name, w, unit))
        out = [rows.get(TOP - r, 0) for r in range(H)]
        glyphs.append((cp, w, out))
    if SQUEEZE:
        sys.exit(f"SQUEEZE entries not used: {SQUEEZE}")

    have = {cp: (w, rows) for cp, w, rows in glyphs}
    for cp, src, remove, add in DRAWN:
        if cp in have:
            sys.exit(f"U+{cp:04X} is in the font now; take it out of DRAWN")
        have[cp] = draw(have, cp, src, remove, add)
    for cp, form in DRAWN_BASE.items():
        if cp in have:
            sys.exit(f"U+{cp:04X} is in the font now; take it out of DRAWN_BASE")
        have[cp] = have[form]
    glyphs = [(cp, w, rows) for cp, (w, rows) in sorted(have.items())]

    digest = hashlib.sha256(open(TTF, "rb").read()).hexdigest()
    o = []
    o.append("/*")
    o.append(" * arabixel_tab.c -- GENERATED by tools/gen_arabixel.py; do not edit.")
    o.append(" *")
    o.append(" * Arabixel Basic (https://arabiandev.itch.io/arabixel-basic-font)")
    o.append(" * (c) 2024 ArabianDev, licensed under CC BY 4.0")
    o.append(" * (https://creativecommons.org/licenses/by/4.0/). Converted to bitmaps;")
    o.append(" * ten glyphs had one row removed to fit 12 rows, and the Persian")
    o.append(" * letters it lacks are drawn from its own (both in the generator).")
    o.append(f" * From Arabixel_Basic.ttf, sha256 {digest}.")
    o.append(" *")
    o.append(" * SPDX-License-Identifier: CC-BY-4.0")
    o.append(" */")
    o.append('#include "arabixel.h"')
    o.append("")
    o.append(f"const unsigned arabixel_count = {len(glyphs)};")
    o.append("")
    o.append("const arabixel_glyph_t arabixel_glyphs[] = {")
    for cp, w, rows in glyphs:
        r = ", ".join(f"0x{v:03X}" for v in rows)
        o.append(f"    {{ 0x{cp:04X}, {w:2d}, {{ {r} }} }},")
    o.append("};")
    open(OUT, "w").write("\n".join(o) + "\n")
    print(f"{len(glyphs)} glyphs -> {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
