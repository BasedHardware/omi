/*
 * Standalone low-level T5838 AAD driver. See t5838_aad.h for the pin map and
 * usage constraints. Register-write protocol lifted from the Irnas/Brilliant-Labs
 * t5838 driver (COPYRIGHT (c) 2023 Irnas; modifications (c) 2025 Brilliant Labs),
 * re-implemented on raw GPIOs for nRF5340.
 */

#include "t5838_aad.h"

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(t5838, CONFIG_LOG_DEFAULT_LEVEL);

/* ---- T5838 register map (subset) ---- */
#define T5838_REG_AAD_MODE 0x29
#define T5838_REG_AAD_A_LPF 0x35
#define T5838_REG_AAD_A_THR 0x36

#define T5838_AAD_SELECT_NONE 0x00
#define T5838_AAD_SELECT_A 0x08

/* Mode-A tuning: 2.0 kHz LPF, 75 dB threshold. 60dB (0x00) is the most
 * sensitive and triggers on ambient noise; 75dB wakes on nearby speech while
 * ignoring a quiet room. Raise/lower here if it never wakes / always wakes. */
#define T5838_AAD_A_LPF_2_0kHz 0x02
#define T5838_AAD_A_THR_75dB 0x06

/* ---- FAKE2C bit-bang protocol constants (from datasheet) ---- */
#define FAKE2C_START_PILOT_CLKS 10
#define FAKE2C_ZERO (1 * FAKE2C_START_PILOT_CLKS)
#define FAKE2C_ONE (3 * FAKE2C_START_PILOT_CLKS)
#define FAKE2C_STOP 130 /* >128 clk cycles */
#define FAKE2C_SPACE (1 * FAKE2C_START_PILOT_CLKS)
#define FAKE2C_POST_WRITE_CYCLES 60 /* >50 clk cycles */
#define FAKE2C_PRE_WRITE_CYCLES 60  /* >50 clk cycles */
#define FAKE2C_DEVICE_ADDRESS 0x53
#define FAKE2C_CLK_PERIOD_US 10 /* ~100 kHz */

/* >2 ms of clock required before entering AAD sleep */
#define ENTER_SLEEP_CLOCKING_US 2500
#define ENTER_SLEEP_CLK_PERIOD_US 10

/* PDMCLK lives on P1.01, shared with the nRF PDM peripheral. */
#define PDMCLK_PORT_NODE DT_NODELABEL(gpio1)
#define PDMCLK_PIN 1U

static const struct device *const clk_port = DEVICE_DT_GET(PDMCLK_PORT_NODE);
static const struct gpio_dt_spec thsel = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_thsel_pin), gpios, {0});
static const struct gpio_dt_spec pdm_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_en_pin), gpios, {0});

static inline void clk_set(int val)
{
    gpio_pin_set(clk_port, PDMCLK_PIN, val);
}

static void clock_bitbang(uint16_t cycles, uint16_t period_us)
{
    for (uint16_t i = 0; i < cycles; i++) {
        clk_set(1);
        k_busy_wait(period_us / 2);
        clk_set(0);
        k_busy_wait(period_us / 2);
    }
}

static void reg_write(uint8_t reg, uint8_t data)
{
    uint8_t wr_buf[] = {FAKE2C_DEVICE_ADDRESS << 1, reg, data};

    /* Start with THSEL low, pre-clock the device. */
    gpio_pin_set_dt(&thsel, 0);
    clock_bitbang(FAKE2C_PRE_WRITE_CYCLES, FAKE2C_CLK_PERIOD_US);

    /* Start condition. */
    gpio_pin_set_dt(&thsel, 1);
    clock_bitbang(FAKE2C_START_PILOT_CLKS, FAKE2C_CLK_PERIOD_US);
    gpio_pin_set_dt(&thsel, 0);
    clock_bitbang(FAKE2C_SPACE, FAKE2C_CLK_PERIOD_US);

    /* Data bits, MSB first. THSEL high for the bit, then a low space. */
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 8; j++) {
            uint8_t cyc = (wr_buf[i] & BIT(7 - j)) ? FAKE2C_ONE : FAKE2C_ZERO;
            gpio_pin_set_dt(&thsel, 1);
            clock_bitbang(cyc, FAKE2C_CLK_PERIOD_US);
            gpio_pin_set_dt(&thsel, 0);
            clock_bitbang(FAKE2C_SPACE, FAKE2C_CLK_PERIOD_US);
        }
    }

    /* Stop condition + apply clocks. */
    gpio_pin_set_dt(&thsel, 1);
    clock_bitbang(FAKE2C_STOP, FAKE2C_CLK_PERIOD_US);
    gpio_pin_set_dt(&thsel, 0);
    clock_bitbang(FAKE2C_POST_WRITE_CYCLES, FAKE2C_CLK_PERIOD_US);
}

static void aad_unlock_sequence(void)
{
    /* Datasheet-provided unlock sequence for AAD modes. */
    static const uint8_t seq[][2] = {
        {0x5C, 0x00},
        {0x3E, 0x00},
        {0x6F, 0x00},
        {0x3B, 0x00},
        {0x4C, 0x00},
    };
    for (size_t i = 0; i < ARRAY_SIZE(seq); i++) {
        reg_write(seq[i][0], seq[i][1]);
    }
}

int t5838_aad_init(void)
{
    int ret;

    if (!device_is_ready(clk_port)) {
        LOG_ERR("gpio1 (PDMCLK) not ready");
        return -ENODEV;
    }
    /* gpio_is_ready_dt() also catches the GPIO_DT_SPEC_GET_OR {0} fallback
     * (port == NULL -> device_is_ready(NULL) is false). */
    if (!gpio_is_ready_dt(&pdm_en) || !gpio_is_ready_dt(&thsel)) {
        LOG_ERR("THSEL/PDM_EN gpio not ready");
        return -ENODEV;
    }

    /* PDM_EN high: power the 1.8V rail (mic VDD + level-shifter VCCA). Propagate
     * configure failures so callers don't treat a dead rail as ready. */
    ret = gpio_pin_configure_dt(&pdm_en, GPIO_OUTPUT_ACTIVE);
    if (ret) {
        LOG_ERR("PDM_EN configure failed: %d", ret);
        return ret;
    }
    ret = gpio_pin_configure_dt(&thsel, GPIO_OUTPUT_INACTIVE);
    if (ret) {
        LOG_ERR("THSEL configure failed: %d", ret);
        return ret;
    }
    LOG_INF("t5838 ll init: PDM_EN driven high, THSEL out low");
    return 0;
}

void t5838_aad_power(bool on)
{
    gpio_pin_set_dt(&pdm_en, on ? 1 : 0);
}

void t5838_aad_release_clk(void)
{
    /* Undo the AAD-sleep line parking: THSEL back low, and hand PDMCLK back to
     * the PDM peripheral (input so pinctrl/PSEL reclaims it on the next START). */
    gpio_pin_set_dt(&thsel, 0);
    gpio_pin_configure(clk_port, PDMCLK_PIN, GPIO_INPUT);
}

int t5838_aad_enter(void)
{
    /* Take THSEL + PDMCLK as GPIO outputs for bit-banging. */
    gpio_pin_configure_dt(&thsel, GPIO_OUTPUT_INACTIVE);
    gpio_pin_configure(clk_port, PDMCLK_PIN, GPIO_OUTPUT_INACTIVE);

    LOG_INF("t5838 AAD: unlock + mode-A config");
    aad_unlock_sequence();

    /* Mode A: disable, set LPF + threshold, then select mode A. */
    reg_write(T5838_REG_AAD_MODE, T5838_AAD_SELECT_NONE);
    reg_write(T5838_REG_AAD_A_LPF, T5838_AAD_A_LPF_2_0kHz);
    reg_write(T5838_REG_AAD_A_THR, T5838_AAD_A_THR_75dB);
    reg_write(T5838_REG_AAD_MODE, T5838_AAD_SELECT_A);

    /* Clock >2 ms so the mic latches config and enters AAD sleep. */
    clock_bitbang(ENTER_SLEEP_CLOCKING_US / ENTER_SLEEP_CLK_PERIOD_US, ENTER_SLEEP_CLK_PERIOD_US);

    /* Park lines HIGH (not low) during AAD sleep. Held low, CLK+THSEL fight the
     * TXS0104's internal 10k pull-ups on both rails (~0.5 mA each). High matches
     * the pull-ups -> no shifter leak. Clock is static (no edges) so the mic
     * stays latched in AAD mode. */
    clk_set(1);
    gpio_pin_set_dt(&thsel, 1);
    LOG_INF("t5838 AAD: entered sleep (mode A, 75dB, CLK/THSEL parked high)");
    return 0;
}
