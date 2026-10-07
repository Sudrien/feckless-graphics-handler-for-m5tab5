# Feckless Graphics Handler for Tab5

The M5Stack Tab5's display, as an ESP-IDF component: the panel and its
backlight, and `gfx`, the framebuffer and drawing layer on top. Pulled
out of
[Defeatist Music Player for M5Tab5](https://github.com/Sudrien/defeatist-music-player-for-m5tab5),
where it was written and where it runs; the long comments in the source
are that project's record of why each thing is the way it is, and they
came along unchanged.

| Header | What it is |
|---|---|
| `lcd.h` | The ST7121 over MIPI-DSI (720 x 1280, RGB565) and the PWM backlight |
| `gfx.h` | One framebuffer in PSRAM, blitted to the panel by DMA2D; rotation in quarter turns; rectangles, circles, polygons, digits; text in Ark Pixel 12px with CJK, Arabic shaping and right-to-left lines; a brightness filter applied at blit time |
| `brightness.h` | A brightness setting mapped onto backlight duty plus that filter, so the low end does not fall off a cliff. Header-only |
| `bidiline.h` | Right-to-left line order, brackets and mirroring. Header-only |
| `logcut.h` | Shortening a UTF-8 string for a log line without splitting a letter. Header-only |
| `ark12.h`, `arabixel.h` | The two font tables gfx draws from |

Rev 2 Tabs only: the rev 1 board's ILI9881C has never been brought up
here.

## Using it

```yaml
# main/idf_component.yml
dependencies:
  feckless_graphics_handler:
    git: https://github.com/Sudrien/feckless-graphics-handler-for-tab5.git
    version: "v0.1.0"
```

and `feckless_graphics_handler` in `main`'s `REQUIRES`.

```c
/* LCD_RST (P4 of the expander at 0x43) released, ~100 ms ago. */
esp_lcd_panel_handle_t panel;
lcd_init(&panel);
gfx_init(panel, LCD_H_RES, LCD_V_RES);
gfx_fill_rect(0, 0, gfx_w(), gfx_h(), 0x0000);
gfx_draw_text(16, 16, "hello", 2, gfx_w() - 32, 0xFFFF);
gfx_blit(0, gfx_h());
lcd_backlight_set(80);
```

## What the application must do

**Release the panel from reset.** LCD_RST is on the PI4IOE5V6416 at
0x43, not a GPIO, and this component does not drive the expanders. See
`lcd.h`.

**Optionally, vendor the instrumented esp_lcd.** The player replaces the
DSI underrun ISR's log call with a counter (its
`cmake/dpi_instrument.cmake`). That has to run before `project.cmake`,
so it is the application's; without it underruns log as stock IDF does.

**Ship the font licences.** Ark Pixel is OFL-1.1: `fonts/ark12/LICENSE-OFL`
goes with any redistribution of firmware built with it. Arabixel Basic's
table is CC BY 4.0 (`fonts/arabixel/LICENSE.txt`). Everything else here
is MIT.

## The fonts

Both tables are generated and committed. `tools/gen_ark12.py` cuts Ark
Pixel's glyph PNGs at a pinned commit (`ARK_COMMIT`) into
`fonts/ark12/`; `tools/gen_arabixel.py` turns `Arabixel_Basic.ttf` into
`fonts/arabixel/arabixel_tab.c`. Each script says why it exists.

## Tests

```
make -C test
```

`texttest` is the real `src/gfx.c` text path on the host, against
`shim.h`'s stand-in for ESP-IDF; the other three are header-only.

## Licence

MIT, except the fonts as above. See `LICENSE`.
