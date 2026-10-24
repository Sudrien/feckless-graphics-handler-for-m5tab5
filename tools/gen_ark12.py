#!/usr/bin/env python3
"""
gen_ark12.py -- turn Ark Pixel Font's 12px glyph PNGs into the C table in
fonts/ark12/ark12.h.

Why this exists at all, and why its output is committed while font8x8's is
not: Ark Pixel does not ship a single header, or even a single font file
in its source tree. It ships one PNG per glyph -- tens of thousands of
them -- and builds the .otf/.bdf at release time. cmake/vendored.cmake's
model of "fetch one pinned file and check its SHA256" does not survive
that, and fetching a 17 MB repository archive on every fresh configure to
extract twenty thousand files from it is worse than committing the output.

So: this script is run by hand, rarely (only when bumping ARK_COMMIT), and
its output goes into git. The pin below is what makes that honest -- the
header records the commit it came from, so it can be regenerated and
diffed byte for byte by anyone who doubts it.

Usage:
    ./tools/gen_ark12.py                     # downloads the pinned archive
    ./tools/gen_ark12.py --src path/to/repo  # uses a checkout you have

Requires only the standard library. The PNGs are tiny RGBA images, so the
decoder here is a complete but deliberately unclever implementation of the
five PNG filter types rather than a Pillow dependency.

SPDX-License-Identifier: MIT
"""

import argparse
import hashlib
import io
import os
import re
import struct
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
import zlib

# Pinned the same way cmake/vendored.cmake pins minimp3 and pngle: to a
# commit, never a branch. Two people regenerating this header a month
# apart must get the same bytes out.
ARK_COMMIT = "d8bd8345fd80f8cf48527aac7718ee1e280870aa"
ARK_URL = f"https://codeload.github.com/TakWolf/ark-pixel-font/zip/{ARK_COMMIT}"

# Korean, from Galmuri (https://github.com/quiple/galmuri), because Ark
# has no Hangul Syllables at this size -- see "Hangul is still out"
# below, which is still true of Ark. Galmuri11 is a 12px pixel font with
# every one of the 11,172 syllables and the 94 Compatibility Jamo, each
# 12px wide, standing 10-11 rows on its baseline: the same cell, and the
# same rows (1-11), that Ark's CJK uses. OFL-1.1 with no Reserved Font
# Name, Copyright (c) 2019-2025 Lee Minseo; fonts/ark12/LICENSE-OFL-galmuri
# is its licence and ships as Ark's does. Pinned to a release and its
# npm tarball's sha256, read from the BDF in it -- a bitmap format, so
# the pixels are the drawn ones, not a rasterisation.
GALMURI_VERSION = "2.40.3"
GALMURI_URL = f"https://registry.npmjs.org/galmuri/-/galmuri-{GALMURI_VERSION}.tgz"
GALMURI_SHA256 = "7d6b2b8534d157dd5e4eb8e01145f7388c0383bed8a96f5ec719eaacf1f86816"
GALMURI_BDF = "package/dist/Galmuri11.bdf"
GALMURI_RANGES = [
    (0x3131, 0x318E),  # Hangul Compatibility Jamo (the letters)
    (0xAC00, 0xD7A3),  # Hangul Syllables
]

# The subset. Two widths coexist here, not one: Ark ships glyphs at this
# pixel size in three cuts -- "monospaced" (6x12, one cell), "common"
# (12x12, one cell doubled -- CJK-shaped scripts and the fullwidth forms
# of a few Latin-1 symbols) and "proportional" (variable width AND
# variable height, which is a different rendering model than this file
# has and is not what RANGES below draws from). A range only belongs here
# if every codepoint in it resolves to one of the first two.
#
# Cyrillic is in RANGES now and was not at 10px. The reason is entirely
# about which cuts exist at which size: at 10px Cyrillic is shipped only
# in the "proportional" cut -- 16 rows tall with per-glyph ascenders and
# descenders, spanning rows 2..13, which no 10-row window can crop without
# clipping real letters (measured: the best-placed window still clips 25
# of 153 glyphs). At 12px there is a genuine monospaced Cyrillic cut at
# the same 6x12 cell as Latin, so it drops in with no special handling at
# all. Nothing clever happened here; the data simply exists at this size
# and did not at the last one.
#
# Hangul is still out OF ARK, and for an unchanged reason (it comes from
# Galmuri instead -- GALMURI_* above): the Compatibility Jamo
# block (individual letters) exists, but Hangul Syllables -- the composed
# characters real Korean text is written in -- has no glyphs at this size
# either. Jamo alone cannot render a Korean title; Unicode's algorithmic
# Hangul composition would have to run on top of glyphs this font does not
# have, so Korean stays out rather than shipping half of it.
#
# What *is* available clean, checked against the archive: Hiragana and
# Katakana (93 + 96 codepoints, both entirely 12x12 in the "common" cut),
# CJK Symbols and Punctuation (the fullwidth quote marks and brackets
# Japanese and Chinese titles actually use), and -- the reason this size
# was worth the move -- 18,299 unique CJK Unified Ideograph codepoints,
# against 1,076 at 10px. That is effectively the whole block rather than a
# subset, so a Chinese or Japanese title is no longer a coin flip on
# whether its particular characters happen to be drawn.
#
# "Effectively" and not "entirely": Ark is hand-drawn and crowd-
# contributed, and a few codepoints simply have no glyph at any size --
# U+8B77 and U+90CE among them, both ordinary characters in Japanese
# names. They come out of glyph_for() as a notdef box, which is the
# correct outcome and not a bug in this script; there is nothing to
# generate. Expect a small number of boxes in CJK text rather than none.
#
# Halfwidth and Fullwidth Forms (FF00-FFEF) is in RANGES because gfx.c's
# cp_is_wide() already treats that block as fullwidth, and a block the
# renderer reserves double-width space for but the table has no glyphs
# for is the worst of both: a double-wide notdef box where a fullwidth
# parenthesis belongs. Japanese and Chinese taggers use these constantly
# -- a title with (2017) in fullwidth parens is completely ordinary --
# so the block was a real omission rather than a nicety, caught by
# rendering a sampler sheet and seeing the boxes.
#
# That coverage is not free: see the size report emit() prints. The table
# is roughly 545 KB against a 3 MB app partition. It is affordable, it is
# the single largest thing in the binary, and it is the first thing to
# trim if that ever stops being true -- dropping (0x4E00, 0x9FFF) alone
# takes it to about 62 KB while keeping every Latin, Cyrillic, kana and
# fullwidth-punctuation glyph. Note that 62 and not something nearer 20:
# Extension A is 1,480 codepoints of its own and stays behind, so cutting
# the main block is most but not all of the saving.
#
# Latin Extended-B and Latin Extended Additional (Vietnamese) are still
# excluded on the original grounds -- a long tail this player is unlikely
# to meet on an SD card. Add the range here and rerun if that turns out to
# be wrong.
RANGES = [
    (0x0020, 0x007E),  # Basic Latin, minus the control codes and DEL
    (0x00A0, 0x00FF),  # Latin-1 Supplement
    (0x0100, 0x017F),  # Latin Extended-A
    (0x0400, 0x04FF),  # Cyrillic (halfwidth; monospaced cut, 12px only)
    (0x2000, 0x206F),  # General Punctuation (mixed: … ‘’“” halfwidth, — • fullwidth)
    (0x2150, 0x218F),  # Number Forms: ⅓ ⅔ and the other vulgar fractions, Ⅰ-Ⅻ
    (0x3000, 0x303F),  # CJK Symbols and Punctuation (fullwidth)
    (0x3040, 0x309F),  # Hiragana (fullwidth)
    (0x30A0, 0x30FF),  # Katakana (fullwidth)
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A (fullwidth)
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs (fullwidth)
    (0xFF00, 0xFFEF),  # Halfwidth and Fullwidth Forms
]

# 12px, not the 10px this started at. Ark ships three sizes -- 10, 12 and
# 16 -- and they are not the same font at three scales; they are three
# separately drawn sets with very different coverage, because this is a
# hand-drawn crowd-contributed font and contributors did not spread evenly
# across sizes. Counted from the archive rather than assumed:
#
#                        10px        12px        16px
#   CJK Unified          1076       18299          97
#   Cyrillic (mono)         0         151         151
#   Hiragana/Katakana   93/96       93/96       93/96
#
# 12px is simply where this font is finished. It is the only size with a
# monospaced Cyrillic cut at the same fixed cell as Latin (10px has only
# a variable-height "proportional" cut, which is a different rendering
# model and was why Cyrillic was excluded before), and its CJK coverage is
# effectively the whole block rather than a curated subset. 16px regresses
# hard on CJK -- 97 codepoints -- so it buys resolution and loses the
# script that motivated the exercise.
#
# There is a display argument on top of the coverage one. The panel is
# 720x1280 on 5", about 294 PPI, and CLAUDE.md's "Sizes are set for 294
# PPI" section scales everything up to compensate. Scaling up a 10px glyph
# by 4 gives 40px of very blocky letterform; a 12px glyph by 3 gives 36px
# with more drawn detail underneath and a smaller scale multiplier, so the
# blocks are 3x3 rather than 4x4. Same physical size, more fidelity --
# which is the whole point of having pixels this small.
GLYPH_H = 12
HALF_W = 6    # one cell -- Latin, Latin-1, Latin Extended-A, Cyrillic
FULL_W = 12   # two cells -- CJK-adjacent scripts and fullwidth forms

# Anything drawn at least this opaque is on. Ark's glyphs are hard-edged
# 1-bit art stored in an 8-bit alpha channel, so every pixel is 0 or 255
# and the threshold never actually has to decide anything. It is here so
# that a future antialiased source degrades to something legible instead
# of to noise.
ALPHA_ON = 128


def png_alpha(data: bytes) -> tuple[int, int, list[list[int]]]:
    """Decode an 8-bit RGBA PNG, returning (w, h, alpha rows)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")

    idat = bytearray()
    w = h = depth = color = 0
    off = 8
    while off < len(data):
        (length,) = struct.unpack(">I", data[off:off + 4])
        kind = data[off + 4:off + 8]
        body = data[off + 8:off + 8 + length]
        if kind == b"IHDR":
            w, h, depth, color, _, interlace, _ = struct.unpack(">IIBBBBB", body)
            if depth != 8 or color != 6 or interlace != 0:
                raise ValueError(f"unsupported PNG: depth={depth} color={color}")
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        off += 12 + length

    raw = zlib.decompress(bytes(idat))
    stride = w * 4
    out = []
    prev = bytearray(stride)
    pos = 0
    for _ in range(h):
        ftype = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        for i in range(stride):
            a = line[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            if ftype == 0:
                pass
            elif ftype == 1:
                line[i] = (line[i] + a) & 0xFF
            elif ftype == 2:
                line[i] = (line[i] + b) & 0xFF
            elif ftype == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
            else:
                raise ValueError(f"bad filter {ftype}")
        out.append([line[x * 4 + 3] for x in range(w)])
        prev = line
    return w, h, out


def collect(src: str) -> dict[int, tuple[int, list[int]]]:
    """codepoint -> (width, 10 rows of bitmap, one uint per row, bit 0 = leftmost).

    width is HALF_W or FULL_W, read from the PNG rather than assumed --
    see the RANGES comment above for why that distinction cannot be made
    from the codepoint alone at the RANGES-selection stage and has to be
    settled per glyph, here, against the actual pixel data.
    """
    root = os.path.join(src, "assets", "glyphs", "12")
    if not os.path.isdir(root):
        sys.exit(f"no glyph directory under {src}")

    wanted = {cp for lo, hi in RANGES for cp in range(lo, hi + 1)}

    # monospaced first, common second -- in PRIORITY, which is the
    # opposite of iteration order below: iterating common first and
    # monospaced second means a codepoint present in both ends up with
    # the monospaced path, because the second loop's assignment wins.
    # 'common' holds glyphs shared with the proportional cut, and for
    # CJK-adjacent blocks those are fullwidth -- 10 px, not 5. Nothing in
    # the new ranges has a monospaced entry to prefer, so this only
    # matters for the original three Latin ranges, unchanged from before.
    found: dict[int, str] = {}
    for flavour in ("common", "monospaced"):
        base = os.path.join(root, flavour)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            # CJK Unified Ideographs is itself split into per-prefix
            # subdirectories (4E-/, 4F-/, ...) rather than one flat
            # directory of 1244 files -- os.walk() rather than a single
            # os.listdir() is what makes that transparent here.
            for name in filenames:
                m = re.fullmatch(r"([0-9A-F]{4,6})\.png", name)
                if not m:
                    continue
                cp = int(m.group(1), 16)
                if cp in wanted:
                    found[cp] = os.path.join(dirpath, name)

    glyphs: dict[int, tuple[int, list[int]]] = {}
    skipped_width = []
    for cp in sorted(found):
        w, h, alpha = png_alpha(open(found[cp], "rb").read())
        if h != GLYPH_H or w not in (HALF_W, FULL_W):
            skipped_width.append((cp, w, h))
            continue
        rows = []
        for y in range(GLYPH_H):
            bits = 0
            for x in range(w):
                if alpha[y][x] >= ALPHA_ON:
                    bits |= 1 << x
            rows.append(bits)
        glyphs[cp] = (w, rows)

    if skipped_width:
        print(f"skipped {len(skipped_width)} glyphs of neither {HALF_W}x{GLYPH_H} "
              f"nor {FULL_W}x{GLYPH_H}: "
              + ", ".join(f"U+{c:04X}({w}x{h})" for c, w, h in skipped_width[:8])
              + (" ..." if len(skipped_width) > 8 else ""), file=sys.stderr)

    # Not a warning. RANGES names whole Unicode blocks, and Ark draws
    # those blocks sparsely -- CJK Unified is 20,992 codepoints of which
    # 18,299 are drawn, and the rest were never expected. Reported as a
    # count, and only as a count, because the previous phrasing ("N
    # codepoints absent from the source") read as breakage on every run
    # and trained the eye to skip it. The per-range table emit() prints
    # is where a genuinely empty range shows up.
    missing = wanted - set(glyphs)
    if missing:
        print(f"{len(glyphs)} of {len(wanted)} requested codepoints drawn at "
              f"this size; {len(missing)} are not in the font (expected -- "
              f"RANGES names whole blocks)", file=sys.stderr)
    return glyphs


HEADER = """/*
 * ark12.h -- Ark Pixel Font, 12px, as deduplicated 4x6 tiles, stored as
 * the places where a tile differs from the previous glyph's.
 *
 * GENERATED FILE. Do not edit. Regenerate with:
 *     ./tools/gen_ark12.py
 * from ark-pixel-font @ {commit}.
 *
 * Ark Pixel Font
 * https://github.com/TakWolf/ark-pixel-font
 * Copyright (c) 2021, TakWolf (https://takwolf.com).
 * Licensed under the SIL Open Font License, Version 1.1.
 *
 * Hangul (U+3131-318E, U+AC00-D7A3): Galmuri11 {galmuri}
 * https://github.com/quiple/galmuri
 * Copyright (c) 2019-2025 Lee Minseo (quiple@quiple.dev).
 * Licensed under the SIL Open Font License, Version 1.1; its text is
 * fonts/ark12/LICENSE-OFL-galmuri, and ships as LICENSE-OFL does.
 *
 * NOTE ON LICENSING: the rest of this project is MIT. This file is not,
 * and cannot be. It is a format conversion of OFL-licensed Font Software,
 * which makes it a Modified Version under the OFL, and OFL section 5
 * requires Modified Versions to stay under the OFL. The full text is in
 * fonts/ark12/LICENSE-OFL and must ship with any redistribution of
 * this file or of a binary containing it. Ark Pixel declares no Reserved
 * Font Name, so this derivative does not have to be renamed -- but it
 * also must not be sold on its own, and this header must stay attached.
 *
 * Every glyph is {h} rows tall and either {half}px (Latin and its
 * relatives -- one cell) or {full}px ({full_desc} -- two cells, the
 * same shape a CJK terminal font calls fullwidth) wide. ark12_glyph()
 * hands back a glyph as {h} rows, each one value with bit 0 leftmost --
 * the shape gfx.c draws from.
 *
 * STORED AS 4x6 TILES, ONE RULE FOR EVERY SCRIPT. Every glyph, half-width
 * or full, is cut into the same {npos} tiles of 4 columns by 6 rows: three
 * across and two down, position p = 3 * row + column. A half-width glyph
 * is 6 pixels wide, so its third column is blank and costs almost
 * nothing. The {tiles_total} tiles of the font are only {tiles} distinct -- blank
 * corners, shared radicals, the same jamo -- so each distinct tile is
 * stored once in ark12_tiles, 24 bits (3 bytes), row 0 in the low 4 bits,
 * bit 0 of a row leftmost.
 *
 * What a glyph stores is smaller than a list of its tiles' numbers.
 * Glyphs are numbered in codepoint order, and neighbours share most of
 * their tiles (Hangul syllables with the same initial and vowel; kana;
 * the blank half of a stroke). So for each position p the glyphs are
 * walked in order and a tile is stored only where it differs from the
 * glyph before it: a bit in ark12_flags says "new tile here", and the
 * new tiles themselves are ark12_lit, {ibits} bits each (ARK12_IBITS), indexes
 * into ark12_tiles. The tile of glyph g at p is the last literal at or
 * before g, which is a count of flags: ark12_ckpt holds the running count
 * at every 128th glyph, and the rest is popcount() of at most four words.
 * ark12_litbase[p] is where p's literals start in ark12_lit. A glyph's
 * number is its run's `g` plus its place in the run.
 *
 * {bytes} bytes, where one uint16_t row per scanline and a codepoint and
 * a width per glyph took {old_bytes}.
 *
 * SPDX-License-Identifier: OFL-1.1
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#define ARK12_H       {h}
#define ARK12_HALF_W  {half}
#define ARK12_FULL_W  {full}
#define ARK12_COUNT   {count}
#define ARK12_TILES   {tiles}
#define ARK12_RUNS    {runs}

#define ARK12_NPOS         {npos}    /* tiles a glyph: 3 across, 2 down */
#define ARK12_IBITS        {ibits}   /* bits a literal: ceil(log2(ARK12_TILES)) */
#define ARK12_BLOCK_SHIFT  {bshift}    /* one checkpoint every 1 << this glyphs */
#define ARK12_FLAG_WORDS   {nwords}  /* uint32_t a position's flags take */
#define ARK12_CKPTS        {nck}   /* checkpoints a position has */

/* 6 bytes a run: the width is the top bit of `count`, since a run is
 * never 32768 long. A run is consecutive codepoints of one width, and
 * there are {runs} of them (the CJK blocks are not drawn whole). */
#define ARK12_RUN_FULL  0x8000u
typedef struct {{
    uint16_t first;     /* the run's first codepoint */
    uint16_t count;     /* how many consecutive codepoints | ARK12_RUN_FULL */
    uint16_t g;         /* the number of the run's first glyph */
}} ark12_run_t;

extern const ark12_run_t ark12_runs[ARK12_RUNS];
/* Position p's flags are ark12_flags[p * ARK12_FLAG_WORDS ...]: bit (g & 31)
 * of word g >> 5 is set where glyph g's tile at p is not glyph g-1's. Glyph
 * 0 always sets it. */
extern const uint32_t    ark12_flags[ARK12_NPOS * ARK12_FLAG_WORDS];
/* Flags set at p before glyph (block << ARK12_BLOCK_SHIFT). */
extern const uint16_t    ark12_ckpt[ARK12_NPOS * ARK12_CKPTS];
/* Where position p's literals start, counted in literals. */
extern const uint32_t    ark12_litbase[ARK12_NPOS];
/* The literals, ARK12_IBITS bits each, packed end to end, low bit first;
 * then 3 bytes of padding so a literal can be read as 3. */
extern const uint8_t     ark12_lit[];
/* ARK12_TILES tiles of 24 bits: row 0 in the low 4 bits, bit 0 of a row
 * leftmost. */
extern const uint8_t     ark12_tiles[];

/* Glyph g's tile at position p, as an index into ark12_tiles. */
static inline uint32_t ark12_tile_at(int p, uint32_t g)
{{
    const uint32_t *f = ark12_flags + (uint32_t)p * ARK12_FLAG_WORDS;
    const uint32_t blk = g >> ARK12_BLOCK_SHIFT;
    const uint32_t last = g >> 5;
    uint32_t n = ark12_ckpt[(uint32_t)p * ARK12_CKPTS + blk];
    for (uint32_t w = blk << (ARK12_BLOCK_SHIFT - 5); w < last; w++)
        n += (uint32_t)__builtin_popcount(f[w]);
    const uint32_t keep = (g & 31u) == 31u ? 0xFFFFFFFFu : ((2u << (g & 31u)) - 1u);
    n += (uint32_t)__builtin_popcount(f[last] & keep);
    /* n >= 1: glyph 0 starts every position's first literal. */
    const uint32_t bit = (ark12_litbase[p] + n - 1u) * ARK12_IBITS;
    const uint8_t *q = ark12_lit + (bit >> 3);
    const uint32_t v = ((uint32_t)q[0] | ((uint32_t)q[1] << 8) | ((uint32_t)q[2] << 16)) >> (bit & 7u);
    return v & ((1u << ARK12_IBITS) - 1u);
}}

/* A tile's 24 bits: row r is (bits >> (4 * r)) & 0xF. */
static inline uint32_t ark12_tile_bits(uint32_t t)
{{
    const uint8_t *q = ark12_tiles + t * 3u;
    return (uint32_t)q[0] | ((uint32_t)q[1] << 8) | ((uint32_t)q[2] << 16);
}}

/*
 * Fills rows[] with the glyph for `cp` and returns true, with *w_out its
 * width. False for a codepoint outside the subset -- callers decide what
 * that means; gfx.c draws a notdef box sized from the codepoint's own
 * expected width. On false neither rows[] nor *w_out is written.
 */
static inline bool ark12_glyph(uint32_t cp, int *w_out, uint16_t rows[ARK12_H])
{{
    if (cp > 0xFFFFu) return false;
    int lo = 0, hi = ARK12_RUNS - 1;
    while (lo <= hi) {{
        const int mid = (lo + hi) / 2;
        const ark12_run_t *r = &ark12_runs[mid];
        if (cp < r->first) {{ hi = mid - 1; continue; }}
        if (cp >= (uint32_t)r->first + (r->count & ~ARK12_RUN_FULL)) {{ lo = mid + 1; continue; }}
        const uint32_t g = (uint32_t)r->g + (cp - r->first);
        uint32_t t[ARK12_NPOS];
        for (int p = 0; p < ARK12_NPOS; p++)
            t[p] = ark12_tile_bits(ark12_tile_at(p, g));
        for (int y = 0; y < ARK12_H; y++) {{
            const uint32_t *s = t + (y / 6) * 3;
            const int sh = 4 * (y % 6);
            rows[y] = (uint16_t)(((s[0] >> sh) & 0xFu) |
                                 (((s[1] >> sh) & 0xFu) << 4) |
                                 (((s[2] >> sh) & 0xFu) << 8));
        }}
        *w_out = (r->count & ARK12_RUN_FULL) ? ARK12_FULL_W : ARK12_HALF_W;
        return true;
    }}
    return false;
}}
"""

SOURCE = """/*
 * ark12.c -- the tables declared by ark12.h.
 *
 * GENERATED FILE. Do not edit. Regenerate with ./tools/gen_ark12.py
 * from ark-pixel-font @ {commit}.
 *
 * Ark Pixel Font, Copyright (c) 2021, TakWolf. Hangul from Galmuri11
 * {galmuri}, Copyright (c) 2019-2025 Lee Minseo. See ark12.h, LICENSE-OFL
 * and LICENSE-OFL-galmuri. This file is OFL-1.1, not MIT.
 *
 * SPDX-License-Identifier: OFL-1.1
 */

#include "ark12.h"

const ark12_run_t ark12_runs[ARK12_RUNS] = {{
{runs}}};

const uint32_t ark12_flags[ARK12_NPOS * ARK12_FLAG_WORDS] = {{
{flags}}};

const uint16_t ark12_ckpt[ARK12_NPOS * ARK12_CKPTS] = {{
{ckpt}}};

const uint32_t ark12_litbase[ARK12_NPOS] = {{
{litbase}}};

const uint8_t ark12_lit[{nlit}] = {{
{lit}}};

const uint8_t ark12_tiles[{ntilebytes}] = {{
{tilebytes}}};
"""


# 4x6 tiles: three across, two down. A tile is 24 bits, row 0 in the low
# 4, bit 0 of a row leftmost; position p is 3 * row + column.
TILE_W, TILE_H = 4, 6
COLS, ROWS = FULL_W // TILE_W, GLYPH_H // TILE_H
NPOS = COLS * ROWS
# A running count of flags is kept every 1 << BLOCK_SHIFT glyphs; ark12.h's
# lookup adds popcount() of at most (1 << BLOCK_SHIFT) / 32 words to it.
BLOCK_SHIFT = 7


def tile_of(rows: list[int], p: int) -> int:
    """The 4x6 tile at position p of a glyph, as 24 bits: row 0 low."""
    col, row = p % COLS, p // COLS
    v = 0
    for r in range(TILE_H):
        v |= ((rows[row * TILE_H + r] >> (col * TILE_W)) & 0xF) << (4 * r)
    return v


def rows_of(tiles6: list[int]) -> list[int]:
    """The twelve rows of a glyph from its six tiles -- ark12_glyph()."""
    rows = []
    for y in range(GLYPH_H):
        row, ty = divmod(y, TILE_H)
        v = 0
        for col in range(COLS):
            v |= ((tiles6[row * COLS + col] >> (4 * ty)) & 0xF) << (TILE_W * col)
        rows.append(v)
    return rows


class Enc:
    """Everything encode() makes: what is written, and what size it is."""
    def table_bytes(self) -> int:
        return (len(self.runs) * 6 + len(self.flags) * len(self.flags[0]) * 4
                + len(self.ckpt) * len(self.ckpt[0]) * 2 + NPOS * 4
                + len(self.lit) + len(self.tilebytes))


def tile_at(flags, ckpt, litbase, lit, tilebytes, ibits, p: int, g: int) -> int:
    """ark12_tile_at() and ark12_tile_bits(), as the C does them."""
    f = flags[p]
    blk = g >> BLOCK_SHIFT
    n = ckpt[p][blk]
    for w in range(blk << (BLOCK_SHIFT - 5), g >> 5):
        n += bin(f[w]).count("1")
    keep = 0xFFFFFFFF if (g & 31) == 31 else (2 << (g & 31)) - 1
    n += bin(f[g >> 5] & keep).count("1")
    assert n >= 1
    bit = (litbase[p] + n - 1) * ibits
    v = int.from_bytes(lit[bit >> 3:(bit >> 3) + 3], "little") >> (bit & 7)
    t = v & ((1 << ibits) - 1)
    return int.from_bytes(tilebytes[t * 3:t * 3 + 3], "little")


def encode(glyphs: dict[int, tuple[int, list[int]]]) -> Enc:
    """Runs, flags, checkpoints, literals and distinct tiles -- and a check,
    before anything is written, that every glyph decodes back to its rows
    the way ark12_glyph() decodes it."""
    e = Enc()
    order = sorted(glyphs)
    n = len(order)
    assert n < 0x10000, "glyph numbers no longer fit in 16 bits"
    e.order = order

    runs = []
    for g, cp in enumerate(order):
        w = glyphs[cp][0]
        if runs and runs[-1][0] + runs[-1][1] == cp and runs[-1][3] == w and runs[-1][1] < 0x7FFF:
            runs[-1][1] += 1
        else:
            runs.append([cp, 1, g, w])
    e.runs = runs

    seq = [[tile_of(glyphs[cp][1], p) for p in range(NPOS)] for cp in order]
    nwords = (n + 31) // 32
    nck = (n + (1 << BLOCK_SHIFT) - 1) >> BLOCK_SHIFT
    flags = [[0] * nwords for _ in range(NPOS)]
    ckpt = [[0] * nck for _ in range(NPOS)]
    lits = []
    for p in range(NPOS):
        prev, count, lp = None, 0, []
        for g in range(n):
            if g & ((1 << BLOCK_SHIFT) - 1) == 0:
                ckpt[p][g >> BLOCK_SHIFT] = count
            t = seq[g][p]
            if t != prev:
                flags[p][g >> 5] |= 1 << (g & 31)
                lp.append(t)
                count += 1
                prev = t
        assert count <= 0xFFFF, "a running count no longer fits in 16 bits"
        lits.append(lp)

    index, tiles = {}, []
    for lp in lits:
        for t in lp:
            if t not in index:
                index[t] = len(tiles)
                tiles.append(t)
    ibits = max(1, (len(tiles) - 1).bit_length())
    litbase, total, idx = [], 0, []
    for lp in lits:
        litbase.append(total)
        total += len(lp)
        idx += [index[t] for t in lp]
    packed, acc, nacc = bytearray(), 0, 0
    for v in idx:
        acc |= v << nacc
        nacc += ibits
        while nacc >= 8:
            packed.append(acc & 0xFF)
            acc >>= 8
            nacc -= 8
    if nacc:
        packed.append(acc & 0xFF)
    packed += b"\0\0\0"
    tilebytes = b"".join(t.to_bytes(3, "little") for t in tiles)

    e.flags, e.ckpt, e.litbase, e.lit, e.tilebytes = flags, ckpt, litbase, bytes(packed), tilebytes
    e.tiles, e.ibits, e.nwords, e.nck = tiles, ibits, nwords, nck
    e.tiles_total, e.literals = n * NPOS, total

    # The check: decode as ark12_glyph() does, compare with the source.
    for g, cp in enumerate(order):
        got = rows_of([tile_at(flags, ckpt, litbase, e.lit, tilebytes, ibits, p, g)
                       for p in range(NPOS)])
        assert got == glyphs[cp][1], f"U+{cp:04X}: {got} != {glyphs[cp][1]}"
    return e


def emit(glyphs: dict[int, tuple[int, list[int]]], outdir: str, commit: str) -> None:
    e = encode(glyphs)
    order, runs = e.order, e.runs

    runs_c = "".join(f"    {{ 0x{f:04X}, 0x{c | (0x8000 if w == FULL_W else 0):04X}, {g:5d} }},\n"
                     for f, c, g, w in runs)
    flat = [w for fp in e.flags for w in fp]
    flags_c = ""
    for i in range(0, len(flat), 6):
        flags_c += "    " + " ".join(f"0x{w:08X}," for w in flat[i:i + 6]) + "\n"
    flat = [c for cp in e.ckpt for c in cp]
    ckpt_c = ""
    for i in range(0, len(flat), 16):
        ckpt_c += "    " + " ".join(f"{c:5d}," for c in flat[i:i + 16]) + "\n"
    litbase_c = "    " + " ".join(f"{b}," for b in e.litbase) + "\n"
    lit_c = ""
    for i in range(0, len(e.lit), 16):
        lit_c += "    " + " ".join(f"0x{b:02X}," for b in e.lit[i:i + 16]) + "\n"
    tb_c = ""
    for i in range(0, len(e.tilebytes), 15):
        tb_c += "    " + " ".join(f"0x{b:02X}," for b in e.tilebytes[i:i + 15]) + "\n"

    n_half = sum(1 for c in order if glyphs[c][0] == HALF_W)
    n_full = len(order) - n_half
    total = e.table_bytes()
    old = len(order) * (GLYPH_H * 2 + 3)

    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "ark12.h"), "w") as f:
        f.write(HEADER.format(commit=commit, galmuri=GALMURI_VERSION, h=GLYPH_H, half=HALF_W, full=FULL_W,
                              full_desc="CJK-adjacent scripts and fullwidth forms",
                              count=len(order), tiles=len(e.tiles), runs=len(runs),
                              tiles_total=e.tiles_total, bytes=total, old_bytes=old,
                              npos=NPOS, ibits=e.ibits, bshift=BLOCK_SHIFT,
                              nwords=e.nwords, nck=e.nck))
    with open(os.path.join(outdir, "ark12.c"), "w") as f:
        f.write(SOURCE.format(commit=commit, galmuri=GALMURI_VERSION, runs=runs_c,
                              flags=flags_c, ckpt=ckpt_c, litbase=litbase_c,
                              nlit=len(e.lit), lit=lit_c,
                              ntilebytes=len(e.tilebytes), tilebytes=tb_c))

    print(f"{len(order)} glyphs ({n_half} halfwidth, {n_full} fullwidth) in "
          f"{len(runs)} runs; {e.tiles_total} tiles, {e.literals} stored, "
          f"{len(e.tiles)} distinct ({e.ibits} bits each); "
          f"{total} bytes (was {old} as one row per scanline)", file=sys.stderr)

    # Per-range, because a range silently contributing nothing is the
    # failure mode this script actually has -- adding a block to RANGES
    # that the font does not draw at this size produces a working build
    # and no glyphs, and nothing else here would say so.
    print("  per range:", file=sys.stderr)
    for lo, hi in RANGES + GALMURI_RANGES:
        n = sum(1 for cp in order if lo <= cp <= hi)
        flag = "   <-- EMPTY, is this range drawn at this size?" if n == 0 else ""
        print(f"    U+{lo:04X}..U+{hi:04X}  {n:6d}{flag}", file=sys.stderr)

    # The number fonts/ark12/README.md quotes for trimming. Printed
    # rather than left as a claim nobody re-checks after changing RANGES;
    # measured as the tables, the way they would be stored.
    kept = {cp: glyphs[cp] for cp in order if not (0x4E00 <= cp <= 0x9FFF)}
    print(f"  without U+4E00..U+9FFF: {len(kept)} glyphs, "
          f"{encode(kept).table_bytes()} bytes", file=sys.stderr)


def reencode(cfile: str) -> dict[int, tuple[int, list[int]]]:
    """5247: the glyphs of an ark12.c this script wrote before -- any
    format, the 4x6 tiles with flags among them -- so the tables can be
    re-encoded without the font's source. The last regeneration was from a
    local checkout; this keeps the glyphs exactly those."""
    src = open(cfile).read()
    def block(name):
        i = src.index(name)
        return src[src.index("{", i) + 1: src.index("};", i)]
    if "ark12_bits[" in src:
        cps = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)", block("ark12_cp["))]
        ws = [int(x) for x in re.findall(r"\b(\d+)\b", block("ark12_w["))]
        rows = [[int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)", m)]
                for m in re.findall(r"\{([^{}]*)\}", block("ark12_bits["))]
        return {c: (w, r) for c, w, r in zip(cps, ws, rows)}
    runs = []
    for m in re.findall(r"\{\s*([^{}]*?)\s*\}", block("ark12_runs[")):
        first, count, start = (int(v, 0) for v in m.split(","))
        runs.append((first, count & 0x7FFF, start, FULL_W if count & 0x8000 else HALF_W))
    out = {}
    if "ark12_flags[" in src:
        hdr = open(os.path.join(os.path.dirname(os.path.abspath(cfile)), "ark12.h")).read()
        ibits = int(re.search(r"#define ARK12_IBITS\s+(\d+)", hdr).group(1))
        n = sum(c for _, c, _, _ in runs)
        nwords, nck = (n + 31) // 32, (n + (1 << BLOCK_SHIFT) - 1) >> BLOCK_SHIFT
        fl = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{8})", block("ark12_flags["))]
        flags = [fl[p * nwords:(p + 1) * nwords] for p in range(NPOS)]
        ck = [int(x) for x in re.findall(r"\b(\d+)\b", block("ark12_ckpt["))]
        ckpt = [ck[p * nck:(p + 1) * nck] for p in range(NPOS)]
        litbase = [int(x) for x in re.findall(r"\b(\d+)\b", block("ark12_litbase["))]
        lit = bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)", block("ark12_lit[")))
        tb = bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)", block("ark12_tiles[")))
        for first, count, start, w in runs:
            for k in range(count):
                out[first + k] = (w, rows_of([tile_at(flags, ckpt, litbase, lit, tb, ibits, p, start + k)
                                              for p in range(NPOS)]))
        return out
    tix = [int(x) for x in re.findall(r"\b(\d+)\b", block("ark12_tix["))]
    tb = bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)", block("ark12_tiles[")))
    bits = int.from_bytes(tb, "little")
    tile = lambda i: (bits >> (36 * i)) & ((1 << 36) - 1)
    for first, count, start, w in runs:
        n = 4 if w == FULL_W else 2
        for k in range(count):
            t = tix[start + k * n: start + k * n + n]
            rows = []
            for y in range(GLYPH_H):
                half, ty = divmod(y, 6)
                v = (tile(t[half * 2 if n == 4 else half]) >> (6 * ty)) & 0x3F
                if n == 4:
                    v |= ((tile(t[half * 2 + 1]) >> (6 * ty)) & 0x3F) << 6
                rows.append(v)
            out[first + k] = (w, rows)
    return out


# Glyphs Ark does not have and the player needs, drawn here from Ark's
# own strokes so they sit with the rest. Private Use Area, because what
# they are has no codepoint: Unicode encodes ⅓ ⅔ ½ as characters and
# leaves every other fraction to U+2044 FRACTION SLASH between ordinary
# digits, which is three full-size glyphs, not one.
#
#   U+E000  3/2 -- the Fx sheet's 1.5 gain (the player's 6097), in the
#           form of its neighbours ½ and ⅔. Built from ⅔ (U+2154): its
#           small 3 moved up to where the 2 was, and ½'s small 2 (the
#           same strokes as ⅔'s) set where the 3 was; the slash is ⅔'s.
#
# Taken from the glyphs already in hand, so --reencode and --src give
# the same result, and a bump of ARK_COMMIT that redraws ⅔ redraws this.
PUA_THREE_HALVES = 0xE000


def galmuri_bdf(path: str | None) -> str:
    """Galmuri11's BDF as text: from `path`, or the pinned npm tarball."""
    if path:
        return open(path, encoding="utf-8").read()
    print(f"fetching {GALMURI_URL}", file=sys.stderr)
    blob = urllib.request.urlopen(GALMURI_URL).read()
    got = hashlib.sha256(blob).hexdigest()
    if got != GALMURI_SHA256:
        sys.exit(f"galmuri {GALMURI_VERSION}: sha256 {got}, expected {GALMURI_SHA256}")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as t:
        return t.extractfile(GALMURI_BDF).read().decode("utf-8")


def add_galmuri(glyphs: dict[int, tuple[int, list[int]]], bdf: str) -> None:
    """Galmuri11's Hangul into `glyphs`, fullwidth, in Ark's CJK rows.

    BDF rows run top to bottom, MSB leftmost, from a box BBX w h xoff yoff
    over a baseline at y = 0. Galmuri's baseline goes on row 11 -- where
    Ark's CJK feet are -- so font row y is cell row 11 - y. Every glyph in
    GALMURI_RANGES must fit the 12x12 cell whole; one that does not stops
    the run rather than being cut.
    """
    wanted = {cp for lo, hi in GALMURI_RANGES for cp in range(lo, hi + 1)}
    taken = 0
    for m in re.finditer(r"ENCODING (-?\d+)\n.*?BBX (-?\d+) (-?\d+) (-?\d+) (-?\d+)\n"
                         r"BITMAP\n(.*?)ENDCHAR", bdf, re.S):
        cp = int(m.group(1))
        if cp not in wanted:
            continue
        w, h, xo, yo = (int(m.group(i)) for i in range(2, 6))
        lines = m.group(6).split()
        rows = [0] * GLYPH_H
        for k, line in enumerate(lines[:h]):
            y = yo + h - 1 - k
            r = (GLYPH_H - 1) - y
            bits = int(line, 16)
            nbits = len(line) * 4
            for x in range(w):
                if bits >> (nbits - 1 - x) & 1:
                    cx = xo + x
                    if not (0 <= r < GLYPH_H and 0 <= cx < FULL_W):
                        sys.exit(f"galmuri U+{cp:04X}: pixel ({cx},{r}) is outside the "
                                 f"{FULL_W}x{GLYPH_H} cell")
                    rows[r] |= 1 << cx
        glyphs[cp] = (FULL_W, rows)
        taken += 1
    missing = len(wanted) - taken
    print(f"galmuri {GALMURI_VERSION}: {taken} Hangul glyphs"
          + (f", {missing} of the requested not in it" if missing else ""), file=sys.stderr)


def add_hand(glyphs: dict[int, tuple[int, list[int]]]) -> None:
    w, two_thirds = glyphs[0x2154]
    rows = list(two_thirds)
    top = [(rows[y] >> 0) & 0xF for y in range(1, 7)]      # small 2, cols 0-3
    bot = [(rows[y] >> 7) & 0xF for y in range(6, 12)]     # small 3, cols 7-10
    for i, y in enumerate(range(1, 7)):
        rows[y] = (rows[y] & ~0xF) | bot[i]
    for i, y in enumerate(range(6, 12)):
        rows[y] = (rows[y] & ~(0xF << 7)) | (top[i] << 7)
    glyphs[PUA_THREE_HALVES] = (w, rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", help="an ark-pixel-font checkout; downloads if absent")
    ap.add_argument("--reencode", metavar="ARK12_C",
                    help="take the glyphs from an ark12.c written before (5247)")
    ap.add_argument("--galmuri", metavar="BDF",
                    help="Galmuri11.bdf; fetches the pinned release if absent")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "fonts", "ark12"))
    args = ap.parse_args()

    if args.reencode:
        g = reencode(args.reencode)
        g.pop(PUA_THREE_HALVES, None)       # rebuilt, not carried over
        add_galmuri(g, galmuri_bdf(args.galmuri))
        add_hand(g)
        emit(g, args.out, "a local checkout")
        return
    if args.src:
        g = collect(args.src)
        add_galmuri(g, galmuri_bdf(args.galmuri))
        add_hand(g)
        emit(g, args.out, "a local checkout")
        return

    print(f"fetching {ARK_URL}", file=sys.stderr)
    blob = urllib.request.urlopen(ARK_URL).read()
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            z.extractall(tmp)
        root = os.path.join(tmp, os.listdir(tmp)[0])
        g = collect(root)
        add_galmuri(g, galmuri_bdf(args.galmuri))
        add_hand(g)
        emit(g, args.out, ARK_COMMIT)


if __name__ == "__main__":
    main()
