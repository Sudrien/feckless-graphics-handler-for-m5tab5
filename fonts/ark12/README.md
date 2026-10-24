# ark12

Ark Pixel Font, 12px, converted to a C bitmap table.

Upstream: https://github.com/TakWolf/ark-pixel-font
Copyright (c) 2021, TakWolf. SIL Open Font License, Version 1.1.

## Licence

**This component is OFL-1.1. The rest of this project is MIT.**

`ark12.c` and `ark12.h` are a format conversion of OFL-licensed Font
Software — PNG glyphs to C arrays — which makes them a Modified Version
under OFL section 5, and section 5 requires Modified Versions to remain
under the OFL. That is not a problem for this project: the OFL explicitly
permits bundling with software under any licence, and only the font files
themselves are bound by it. But it does mean three things:

- `LICENSE-OFL` must ship with any redistribution of these files, and
  with any binary built from them. Firmware images count.
- The tables cannot be relicensed MIT, and no amount of "we typed it out
  as C" changes that.
- They must not be sold on their own, only as part of something.

Ark Pixel declares **no Reserved Font Name**, so this derivative does not
have to be renamed. The name `ark12` is used anyway, because it is not
the Original Version and should not be mistaken for it.

This is the difference from the `font8x8` component it replaces: that
font was public domain, so nothing had to travel with it.

## Hangul: Galmuri11

Ark has no Hangul Syllables at 12px, so the table's Korean --
Compatibility Jamo U+3131-318E (94) and Hangul Syllables U+AC00-D7A3
(all 11,172) -- is **Galmuri11 2.40.3** by Lee Minseo,
https://github.com/quiple/galmuri, Copyright (c) 2019-2025, also
OFL-1.1 with no Reserved Font Name. Its licence is `LICENSE-OFL-galmuri`
and ships with the table as `LICENSE-OFL` does. `tools/gen_ark12.py`
reads it from the BDF in the release's npm tarball, pinned by sha256,
and places each glyph on Ark's CJK rows (1-11): every syllable is 12px
wide and stands 10-11 rows on its baseline, so nothing is cut. The
11,266 glyphs cost about 96 KB as tiles -- 1,903 new distinct tiles,
syllables being made of the same letters -- the table going from
342,720 to 441,427 bytes.

## Coverage

**20,705 glyphs, about 334 KB of flash** -- stored since 5247 as shared
6×6 tiles (81,712 tiles, 33,775 distinct), where one 16-bit value per
row took about 545 KB. Two cell sizes, and the table records which each
glyph is rather than inferring it from the codepoint:

- **6×12 halfwidth** (554 glyphs) — Basic Latin (U+0020–U+007E),
  Latin-1 Supplement, Latin Extended-A, Cyrillic, and General
  Punctuation's quotes, en dash and ellipsis (… ‘ ’ “ ” –).
- **12×12 fullwidth** (20,151 glyphs) — the rest of General
  Punctuation drawn (— ― • † ‡ ‰ ※ among them), CJK Symbols and Punctuation,
  Hiragana, Katakana, CJK Unified Ideographs and Extension A, and
  Halfwidth and Fullwidth Forms.

CJK Unified is the bulk of that: 18,299 codepoints, effectively the whole
block. It is also the obvious thing to cut if the app partition ever gets
tight — dropping `(0x4E00, 0x9FFF)` from `RANGES` took the row-per-scanline
table to about 62 KB (less as tiles; the generator prints the figure) while keeping every Latin, Cyrillic, kana and fullwidth-punctuation
glyph. (62 and not nearer 20: Extension A is 1,480 codepoints of its own
and stays behind.)

The five Latin-1 characters that were missing at 10px — © ® ¼ ½ ¾ — are
present now. They are drawn fullwidth by Ark, which the old
halfwidth-only table could not store and this one can. U+00A0 is drawn as
a space and U+00AD is skipped, both handled in `gfx.c`.

A small number of CJK codepoints have no glyph in Ark at **any** pixel
size — U+8B77 護 and U+90CE 郎 among them, both ordinary characters in
Japanese names. They render as the notdef box. That is a gap upstream,
not one this table can close by regenerating.

Cyrillic is present at this pixel size and was not at 10px, where Ark
ships it only in a variable-height proportional cut. Hangul is still
absent: the Compatibility Jamo block exists, but Hangul Syllables — what
Korean is actually written in — has no glyphs at this size, and jamo alone
cannot compose a title.

Latin Extended-B and Latin Extended Additional (Vietnamese) are
available upstream and excluded here. Add the range to `RANGES` in
`tools/gen_ark12.py` and rerun.

## Notes: glyphs drawn here, not by Ark

One glyph in the table is not Ark's, and it sits in the Private Use
Area so it can never be mistaken for a character Ark (or Unicode) means
something by:

| Codepoint | Glyph | For | Drawn from |
|---|---|---|---|
| U+E000 | 3/2, stacked like ½ and ⅔ | the player's Fx sheet, its 1.5 gain step (6097) | ⅔ (U+2154) with its small 3 moved up to where the 2 was and ½'s small 2 set where the 3 was; the slash is ⅔'s |

Why not a real codepoint: Unicode encodes ⅓ ⅔ ½ ¼ and a few others as
single characters and leaves every other fraction to U+2044 FRACTION
SLASH between ordinary digits -- three full-size glyphs, and Ark draws
no U+2044 at this size anyway. A stacked 3/2 has no codepoint to have.

`tools/gen_ark12.py` builds it (`add_hand()`) from the glyphs it already
has, on every path -- `--reencode`, `--src` and the download -- so a
regeneration keeps it and an ARK_COMMIT bump that redraws ⅔ redraws it
to match. It added no tiles (every 6×6 corner of it already existed
elsewhere) and 16 bytes of runs and tile numbers. It is under the
OFL like the rest of these files: made from Ark's strokes, it is a
Modified Version of them.

Text that uses it writes `"\uE000"`; anything that logs such a label
should print something else, since a terminal has no glyph for it.

## Regenerating

    ./tools/gen_ark12.py

Standard library only. Do not hand-edit the generated files.

The generator prints a per-range glyph count, which is worth reading: a
range that contributes zero glyphs still produces a clean build, and that
silent failure is the one this script actually has.
