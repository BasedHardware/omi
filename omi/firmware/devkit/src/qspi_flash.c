#include "qspi_flash.h"
#include <nrfx_qspi.h>
#include <zephyr/drivers/gpio.h>

#define QSPI_SCK_PIN    21
#define QSPI_CS_PIN     25
#define QSPI_IO0_PIN    20
#define QSPI_IO1_PIN    24
#define QSPI_IO2_PIN    22
#define QSPI_IO3_PIN    23

int qspi_flash_init()
{
    const struct device * dev = DEVICE_DT_GET(DT_NODELABEL(gpio0));
    if (!device_is_ready(dev))
    {
        return -ENODEV;
    }
    gpio_pin_configure(dev, QSPI_CS_PIN, GPIO_OUTPUT_HIGH);

    nrfx_qspi_config_t qspi_cfg =
    {
        .xip_offset = 0,
        .pins =
        {
            .sck_pin = QSPI_SCK_PIN,
            .csn_pin = QSPI_CS_PIN,
            .io0_pin = QSPI_IO0_PIN,
            .io1_pin = QSPI_IO1_PIN,
            .io2_pin = QSPI_IO2_PIN,
            .io3_pin = QSPI_IO3_PIN,
        },
        .prot_if = 
        {
            .readoc = NRF_QSPI_READOC_READ4O, // 0x6B read command
            .writeoc = NRF_QSPI_WRITEOC_PP4O, // 0x32 write command
            .addrmode = NRF_QSPI_ADDRMODE_24BIT,
            .dpmconfig = false
        },
        .phy_if =
        {
            .sck_delay = 10,
            .dpmen = false,
            .spi_mode = NRF_QSPI_MODE_0,
            .sck_freq = NRF_QSPI_FREQ_32MDIV16, // start with low 2 Mhz speed
        },
        .irq_priority = 7,
        .skip_gpio_cfg = true,
        .skip_psel_cfg = false
    };

    nrfx_err_t err = nrfx_qspi_init(&qspi_cfg, NULL, NULL);
    if (err != NRFX_SUCCESS)
    {
        return -err;
    }

    return 0;
} 

void qspi_flash_uninit()
{
    nrfx_qspi_uninit();
}

int qspi_flash_command(uint8_t command)
{
    nrf_qspi_cinstr_conf_t cinstr_cfg = {.opcode = command,
                                         .length = NRF_QSPI_CINSTR_LEN_1B,
                                         .io2_level = true,
                                         .io3_level = true,
                                         .wipwait = false,
                                         .wren = false};

    nrfx_err_t err = nrfx_qspi_cinstr_xfer(&cinstr_cfg, NULL, NULL);
    if (err != NRFX_SUCCESS)
    {
        return -err;
    }

    return 0;
}