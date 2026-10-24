/*
 * ark12.h -- Ark Pixel Font, 12px, as deduplicated 4x6 tiles, stored as
 * the places where a tile differs from the previous glyph's.
 *
 * GENERATED FILE. Do not edit. Regenerate with:
 *     ./tools/gen_ark12.py
 * from ark-pixel-font @ a local checkout.
 *
 * Ark Pixel Font
 * https://github.com/TakWolf/ark-pixel-font
 * Copyright (c) 2021, TakWolf (https://takwolf.com).
 * Licensed under the SIL Open Font License, Version 1.1.
 *
 * Hangul (U+3131-318E, U+AC00-D7A3): Galmuri11 2.40.3
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
 * Every glyph is 12 rows tall and either 6px (Latin and its
 * relatives -- one cell) or 12px (CJK-adjacent scripts and fullwidth forms -- two cells, the
 * same shape a CJK terminal font calls fullwidth) wide. ark12_glyph()
 * hands back a glyph as 12 rows, each one value with bit 0 leftmost --
 * the shape gfx.c draws from.
 *
 * STORED AS 4x6 TILES, ONE RULE FOR EVERY SCRIPT. Every glyph, half-width
 * or full, is cut into the same 6 tiles of 4 columns by 6 rows: three
 * across and two down, position p = 3 * row + column. A half-width glyph
 * is 6 pixels wide, so its third column is blank and costs almost
 * nothing. The 192192 tiles of the font are only 23711 distinct -- blank
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
 * new tiles themselves are ark12_lit, 15 bits each (ARK12_IBITS), indexes
 * into ark12_tiles. The tile of glyph g at p is the last literal at or
 * before g, which is a count of flags: ark12_ckpt holds the running count
 * at every 128th glyph, and the rest is popcount() of at most four words.
 * ark12_litbase[p] is where p's literals start in ark12_lit. A glyph's
 * number is its run's `g` plus its place in the run.
 *
 * 382580 bytes, where one uint16_t row per scanline and a codepoint and
 * a width per glyph took 864864.
 *
 * SPDX-License-Identifier: OFL-1.1
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#define ARK12_H       12
#define ARK12_HALF_W  6
#define ARK12_FULL_W  12
#define ARK12_COUNT   32032
#define ARK12_TILES   23711
#define ARK12_RUNS    3295

#define ARK12_NPOS         6    /* tiles a glyph: 3 across, 2 down */
#define ARK12_IBITS        15   /* bits a literal: ceil(log2(ARK12_TILES)) */
#define ARK12_BLOCK_SHIFT  7    /* one checkpoint every 1 << this glyphs */
#define ARK12_FLAG_WORDS   1001  /* uint32_t a position's flags take */
#define ARK12_CKPTS        251   /* checkpoints a position has */

/* 6 bytes a run: the width is the top bit of `count`, since a run is
 * never 32768 long. A run is consecutive codepoints of one width, and
 * there are 3295 of them (the CJK blocks are not drawn whole). */
#define ARK12_RUN_FULL  0x8000u
typedef struct {
    uint16_t first;     /* the run's first codepoint */
    uint16_t count;     /* how many consecutive codepoints | ARK12_RUN_FULL */
    uint16_t g;         /* the number of the run's first glyph */
} ark12_run_t;

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
{
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
}

/* A tile's 24 bits: row r is (bits >> (4 * r)) & 0xF. */
static inline uint32_t ark12_tile_bits(uint32_t t)
{
    const uint8_t *q = ark12_tiles + t * 3u;
    return (uint32_t)q[0] | ((uint32_t)q[1] << 8) | ((uint32_t)q[2] << 16);
}

/*
 * Fills rows[] with the glyph for `cp` and returns true, with *w_out its
 * width. False for a codepoint outside the subset -- callers decide what
 * that means; gfx.c draws a notdef box sized from the codepoint's own
 * expected width. On false neither rows[] nor *w_out is written.
 */
static inline bool ark12_glyph(uint32_t cp, int *w_out, uint16_t rows[ARK12_H])
{
    if (cp > 0xFFFFu) return false;
    int lo = 0, hi = ARK12_RUNS - 1;
    while (lo <= hi) {
        const int mid = (lo + hi) / 2;
        const ark12_run_t *r = &ark12_runs[mid];
        if (cp < r->first) { hi = mid - 1; continue; }
        if (cp >= (uint32_t)r->first + (r->count & ~ARK12_RUN_FULL)) { lo = mid + 1; continue; }
        const uint32_t g = (uint32_t)r->g + (cp - r->first);
        uint32_t t[ARK12_NPOS];
        for (int p = 0; p < ARK12_NPOS; p++)
            t[p] = ark12_tile_bits(ark12_tile_at(p, g));
        for (int y = 0; y < ARK12_H; y++) {
            const uint32_t *s = t + (y / 6) * 3;
            const int sh = 4 * (y % 6);
            rows[y] = (uint16_t)(((s[0] >> sh) & 0xFu) |
                                 (((s[1] >> sh) & 0xFu) << 4) |
                                 (((s[2] >> sh) & 0xFu) << 8));
        }
        *w_out = (r->count & ARK12_RUN_FULL) ? ARK12_FULL_W : ARK12_HALF_W;
        return true;
    }
    return false;
}
