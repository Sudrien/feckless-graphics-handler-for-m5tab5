/* ---- Display: ST7121 MIPI-DSI, portrait native ---- */
#define LCD_H_RES               (720)
#define LCD_V_RES               (1280)
#define LCD_BITS_PER_PIXEL      (16)
#define DSI_DATA_LANES          (2)
/*
 * Sized to the pixel clock with a margin, not set as high as the PHY
 * will go. See the note below on why that is not the same thing.
 *
 *   720 x 1280 RGB565 at DPI_CLOCK_MHZ = 70 MHz
 *   -> 70 MHz x 16 bits / 2 lanes = 560 Mbps per lane required
 *   -> 700 is 25% over, against Espressif's recommended ~20%
 *
 * Documented floor is 480 and the ceiling on this part is 1500.
 */
#define DSI_LANE_RATE_MBPS      (700)
/*
 * Back to 70 MHz, which is ~57.3 Hz. 29 MHz blanked the panel.
 *
 * The reasoning that got it to 29 still stands as far as it goes. The
 * DPI peripheral reads the framebuffer out of PSRAM continuously and
 * cannot wait; miss a line and the DSI bridge underruns, the panel goes
 * cyan for a frame, and the ISR in esp_lcd/dsi/esp_lcd_panel_dpi.c
 * prints
 *
 *   can't fetch data from external memory fast enough, underrun happens
 *
 * Nothing here can yield to that fetch -- it is a DMA master on the AXI
 * bus rather than a task -- so the only lever is how much it asks for,
 * and at 1.84 MB a frame the refresh rate IS the bandwidth:
 *
 *   total = (720+2+40+40) x (1280+20+24+200) = 802 x 1524 = 1,222,248
 *   70 MHz -> 57.3 Hz -> 105 MB/s
 *   50 MHz -> 40.9 Hz ->  75 MB/s
 *   29 MHz -> 23.7 Hz ->  44 MB/s
 *
 * What that reasoning left out is that the rate is not ours to choose
 * freely. The ST7121 runs its own timing generator locked to the
 * incoming VSYNC, and below its lock range it stops driving the glass
 * rather than degrading: backlight on, esp_lcd_panel_init() returning
 * ESP_OK, the log clean to the last line, and a black screen. There is
 * no error anywhere, because from the SoC's side nothing failed.
 *
 * 24 Hz is under that floor. Where the floor actually is has not been
 * measured -- 70 is the only rate this panel is known to hold, which is
 * why it is what this reverts to rather than something in between.
 *
 * To find it, walk down one step at a time and reflash at each:
 *
 *   60 -> 49.1 Hz -> 90 MB/s
 *   55 -> 45.0 Hz -> 83 MB/s
 *   50 -> 40.9 Hz -> 75 MB/s
 *   45 -> 36.8 Hz -> 68 MB/s
 *
 * and take one step back from wherever it goes dark. Two things to know
 * while doing it:
 *
 *   - The number here is not the number on the wire.
 *     dpi_panel_create() divides the source clock by an INTEGER, via
 *     mipi_dsi_hal_host_dpi_calculate_divider(), so the rate is the
 *     nearest the divider allows and not what is written above. Log the
 *     divider before trusting any of the figures in this comment.
 *   - DSI_LANE_RATE_MBPS is sized to this, and the reasoning that used
 *     to be here -- that the lane rate is the wire, not the memory, so a
 *     bigger margin costs nothing -- is wrong in the way that matters.
 *     Average bandwidth, yes. Burstiness, no: the bridge drains its line
 *     buffer at wire speed and then waits, so the faster the wire the
 *     more the fetch looks like a spike rather than a stream, and a
 *     spike is what a fetch that cannot wait underruns on. Espressif's
 *     LCD FAQ lists a lane rate mismatched to the pixel clock as a cause
 *     of this exact blue-screen symptom and recommends sizing it about
 *     20% above what the clock demands. 965 against a demand of 560 was
 *     72% above.
 *
 *     So the two move together. If the pixel clock comes down, work the
 *     lane rate out again: pixel clock x 16 bits / 2 lanes, plus a
 *     fifth, against a documented floor of 480. If a low rate ever gives
 *     a sheared or misaligned picture rather than a black one, that is
 *     the mismatch to go and look at.
 *
 * And the honest conclusion from the attempt: this is the smaller and
 * riskier of the two levers. The clock buys tens of MB/s and can blank
 * the panel. ui_draw() spends around 160 MB/s repainting the transport
 * bar at 50 Hz under a finger -- a full 560-row clear, a 720-column
 * envelope loop, a 560-row blit, a bubble memcpy and a second blit --
 * and shrinking that carries no risk of anything going dark. Do that
 * first.
 */
#define DPI_CLOCK_MHZ           (70)

#define DSI_PHY_LDO_CHAN        (3)
#define DSI_PHY_LDO_VOLTAGE_MV  (2500)

#define LCD_BACKLIGHT_GPIO      (GPIO_NUM_22)
#define LCD_LEDC_CHANNEL        (LEDC_CHANNEL_1)
#define LCD_LEDC_TIMER          (LEDC_TIMER_0)
#define LCD_LEDC_DUTY_RES       (LEDC_TIMER_12_BIT)
#define LCD_LEDC_DUTY_MAX       (4095)
#define LCD_LEDC_FREQ_HZ        (5000)

#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 0, 0)
#define DPI_COLOR_FORMAT        (LCD_COLOR_FMT_RGB565)
#else
#define DPI_COLOR_FORMAT        (LCD_COLOR_PIXEL_FORMAT_RGB565)
#endif

static esp_lcd_panel_handle_t s_panel;

static esp_err_t backlight_init(void)
{
    const ledc_timer_config_t timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LCD_LEDC_DUTY_RES,
        .timer_num = LCD_LEDC_TIMER,
        .freq_hz = LCD_LEDC_FREQ_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_RETURN_ON_ERROR(ledc_timer_config(&timer), TAG, "ledc timer");

    const ledc_channel_config_t ch = {
        .gpio_num = LCD_BACKLIGHT_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LCD_LEDC_CHANNEL,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = LCD_LEDC_TIMER,
        .duty = 0,                      /* dark until the panel is up */
        .hpoint = 0,
    };
    return ledc_channel_config(&ch);
}

static esp_err_t backlight_set(int percent)
{
    percent = percent < 0 ? 0 : (percent > 100 ? 100 : percent);
    const uint32_t duty = (LCD_LEDC_DUTY_MAX * percent) / 100;
    ESP_RETURN_ON_ERROR(ledc_set_duty(LEDC_LOW_SPEED_MODE, LCD_LEDC_CHANNEL, duty),
                        TAG, "duty");
    return ledc_update_duty(LEDC_LOW_SPEED_MODE, LCD_LEDC_CHANNEL);
}

/* The backlight in counts, 0..LCD_LEDC_DUTY_MAX, for the fade, which
 * needs finer steps than whole percent. */
static esp_err_t backlight_set_counts(uint32_t duty)
{
    if (duty > LCD_LEDC_DUTY_MAX) duty = LCD_LEDC_DUTY_MAX;
    ESP_RETURN_ON_ERROR(ledc_set_duty(LEDC_LOW_SPEED_MODE, LCD_LEDC_CHANNEL, duty),
                        TAG, "duty");
    return ledc_update_duty(LEDC_LOW_SPEED_MODE, LCD_LEDC_CHANNEL);
}

/*
 * Give the DPI scanout first claim on the AXI interconnect.
 *
 * Every earlier lever here was on the demand side (pixel clock, blit
 * banding, keeping SDMMC DMA out of PSRAM) or the supply side (PSRAM
 * speed, L2 geometry). None of them touched arbitration, and that is the
 * one that decides who waits when two masters want PSRAM in the same
 * cycle. IDF never programs it: every master's AXI QoS reset value is 0,
 * so the ICM round-robins, and the DPI's DW-GDMA channel -- the one
 * master that cannot wait -- queues behind the cache (CPU PNG decode,
 * memcpy into the shadow buffer), DMA2D (gfx_blit) and the aggregate CPU
 * port (USB host, EMAC, SDMMC/SDIO DMA into PSRAM) on equal terms.
 *
 * The two underruns in the netstream capture landed with nothing on the
 * UI side happening: that is background DMA from USB-ECM and esp_hosted
 * packet buffers, both in PSRAM, colliding with scanout. Bandwidth is
 * nowhere near exhausted (105 MB/s of scanout against a 200 MHz x16 bus);
 * what is missing is priority.
 *
 * Higher QoS wins arbitration. DW-GDMA is raised on both master ports,
 * since which port the DPI channel lands on is the driver's choice, and
 * only on reads -- scanout never writes. Everything else stays at 0, so
 * nothing is starved: the DPI only asks for 1 KB-ish bursts when the
 * bridge FIFO drops under its threshold, and otherwise gets out of the
 * way. Nothing else in this firmware uses DW-GDMA.
 */
#define DPI_AXI_READ_QOS        (15)

static void dpi_axi_priority(void)
{
    axi_icm_ll_set_dw_gdma_qos_arbiter_prio(0, 0, DPI_AXI_READ_QOS);
    axi_icm_ll_set_dw_gdma_qos_arbiter_prio(1, 0, DPI_AXI_READ_QOS);
    ESP_LOGI(TAG, "AXI QoS: DW-GDMA read %d, cache/CPU/DMA2D 0",
             DPI_AXI_READ_QOS);
}

static esp_err_t panel_init(void)
{
    esp_ldo_channel_handle_t phy_ldo = NULL;
    esp_lcd_dsi_bus_handle_t dsi = NULL;
    esp_lcd_panel_io_handle_t io = NULL;

    const esp_ldo_channel_config_t ldo = {
        .chan_id = DSI_PHY_LDO_CHAN,
        .voltage_mv = DSI_PHY_LDO_VOLTAGE_MV,
    };
    ESP_RETURN_ON_ERROR(esp_ldo_acquire_channel(&ldo, &phy_ldo), TAG, "phy ldo");

    const esp_lcd_dsi_bus_config_t bus = {
        .bus_id = 0,
        .num_data_lanes = DSI_DATA_LANES,
        .phy_clk_src = MIPI_DSI_PHY_CLK_SRC_DEFAULT,
        .lane_bit_rate_mbps = DSI_LANE_RATE_MBPS,
    };
    ESP_RETURN_ON_ERROR(esp_lcd_new_dsi_bus(&bus, &dsi), TAG, "dsi bus");

    const esp_lcd_dbi_io_config_t dbi = {
        .virtual_channel = 0, .lcd_cmd_bits = 8, .lcd_param_bits = 8,
    };
    ESP_RETURN_ON_ERROR(esp_lcd_new_panel_io_dbi(dsi, &dbi, &io), TAG, "panel io");

    esp_lcd_dpi_panel_config_t dpi = {
        .virtual_channel = 0,
        .dpi_clk_src = MIPI_DSI_DPI_CLK_SRC_DEFAULT,
        .dpi_clock_freq_mhz = DPI_CLOCK_MHZ,
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 0, 0)
        .in_color_format = DPI_COLOR_FORMAT,
#else
        .pixel_format = DPI_COLOR_FORMAT,
#endif
        .num_fbs = 1,
        .video_timing = {
            .h_size = LCD_H_RES, .v_size = LCD_V_RES,
            .hsync_pulse_width = 2,  .hsync_back_porch = 40, .hsync_front_porch = 40,
            .vsync_pulse_width = 20, .vsync_back_porch = 24, .vsync_front_porch = 200,
        },
#if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(6, 0, 0)
        .flags.use_dma2d = true,
#endif
    };

    st7121_vendor_config_t vendor = {
        .init_cmds = NULL, .init_cmds_size = 0,
        .mipi_config = { .dsi_bus = dsi, .dpi_config = &dpi },
    };
    const esp_lcd_panel_dev_config_t pcfg = {
        .reset_gpio_num = -1,           /* released via expander P4 */
        .rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB,
        .data_endian = LCD_RGB_DATA_ENDIAN_LITTLE,
        .bits_per_pixel = LCD_BITS_PER_PIXEL,
        .vendor_config = &vendor,
    };
    ESP_RETURN_ON_ERROR(esp_lcd_new_panel_st7121(io, &pcfg, &s_panel), TAG, "st7121");
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 0, 0)
    ESP_RETURN_ON_ERROR(esp_lcd_dpi_panel_enable_dma2d(s_panel), TAG, "dma2d");
#endif
    dpi_axi_priority();
    ESP_RETURN_ON_ERROR(esp_lcd_panel_reset(s_panel), TAG, "reset");
    ESP_RETURN_ON_ERROR(esp_lcd_panel_init(s_panel), TAG, "init");
    ESP_RETURN_ON_ERROR(esp_lcd_panel_disp_on_off(s_panel, true), TAG, "disp on");
    ESP_LOGI(TAG, "ST7121 initialised (%dx%d)", LCD_H_RES, LCD_V_RES);
    return ESP_OK;
}
