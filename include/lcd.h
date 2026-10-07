/*
 * lcd.h -- the M5Stack Tab5's panel and its backlight.
 *
 * The rev 2 Tab5's ST7121 over MIPI-DSI, 720 x 1280 RGB565, portrait as
 * the glass is mounted; and the backlight's PWM on GPIO22. The rev 1
 * board's ILI9881C is not handled: the player this came from has only
 * ever run on rev 2 hardware.
 *
 * WHAT MUST HAPPEN FIRST
 *
 * The panel's reset line is not a GPIO. It is LCD_RST, P4 of the
 * PI4IOE5V6416 at 0x43, and lcd_init() does not touch the expanders: the
 * application releases it (the player's io_expanders_init() writes
 * 0x76 to that expander's output register) and waits ~100 ms before
 * calling this. Without that the panel stays in reset and every DSI
 * command goes unanswered.
 *
 * WHAT THE APPLICATION PROBABLY ALSO WANTS
 *
 * The player vendors a copy of IDF's esp_lcd whose DSI underrun ISR
 * counts into g_tab5_dpi_underruns instead of printing (its
 * cmake/dpi_instrument.cmake). That has to be in place before
 * project.cmake scans components, so it cannot come with this one. Not
 * required: without it, an underrun logs from the ISR as stock IDF does.
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once

#include <stdint.h>

#include "esp_err.h"
#include "esp_lcd_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* The glass, in pixels, as the panel scans it. gfx.h's rotation is on
 * top of this. */
#define LCD_H_RES               (720)
#define LCD_V_RES               (1280)

/* The backlight's full scale in lcd_backlight_set_counts() units. */
#define LCD_LEDC_DUTY_MAX       (4095)

/*
 * The backlight's PWM (dark), then the DSI PHY's LDO, the bus, the panel
 * and its DPI, and display on. The backlight stays at zero: call
 * lcd_backlight_set() once there is a picture worth seeing.
 *
 * `out`, if not NULL, gets the panel handle -- what gfx_init() takes.
 */
esp_err_t lcd_init(esp_lcd_panel_handle_t *out);

/* The same handle, for anything that needs it after init. NULL before. */
esp_lcd_panel_handle_t lcd_panel(void);

/* Backlight, 0-100, clamped. */
esp_err_t lcd_backlight_set(int percent);

/* Backlight in counts, 0..LCD_LEDC_DUTY_MAX, clamped -- for a fade, which
 * needs finer steps than whole percent. */
esp_err_t lcd_backlight_set_counts(uint32_t duty);

#ifdef __cplusplus
}
#endif
