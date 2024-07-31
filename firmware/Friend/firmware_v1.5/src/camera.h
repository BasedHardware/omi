#ifndef CAMERA_H
#define CAMERA_H
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/drivers/i2c.h>

static const struct i2c_dt_spec camera_i2c_dev = I2C_DT_SPEC_GET(DT_NODELABEL(camera));
static const struct spi_dt_spec camera_spi_dev = SPI_DT_SPEC_GET(DT_NODELABEL(camera_spi), SPI_WORD_SET(8) | SPI_TRANSFER_MSB, 1);
// static const struct gpio_dt_spec camera_chip_select = GPIO_DT_SPEC_GET(DT_NODELABEL(camera_cs), gpios);

int camera_start(void);

int take_photo(void);
#endif