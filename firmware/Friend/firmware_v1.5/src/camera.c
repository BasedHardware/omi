#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include "camera.h"
#include "utils.h"
#include "./camera/sequences.h"

#define GPIO_PORT_NAME DT_LABEL(DT_NODELABEL(gpio0))
#define OTHER_CS_NAME 28

//
// i2c device
//

int write_reg_8_8(uint8_t reg, uint8_t value)
{
    return i2c_reg_write_byte_dt(&camera_i2c_dev, reg, value);
}

int write_regs(uint8_t *values)
{
    uint16_t reg_addr = 0;
    uint16_t reg_val = 0;
    uint8_t *next = values;
    while ((reg_addr != 0xff) | (reg_val != 0xff))
    {
        reg_addr = next[0];
        reg_val = next[1];
        ASSERT_OK(write_reg_8_8(reg_addr, reg_val));
        next += 2;
    }
    return 0;
}

//
// SPI device
//

int write_spi_reg_8_8(uint8_t reg, uint8_t value)
{
    uint8_t data[2] = {reg | 0x80, value};
    struct spi_buf tx_b = {
        .buf = data,
        .len = 2};
    struct spi_buf_set tx = {
        .buffers = {&tx_b}, .count = 1};

    return spi_write_dt(&camera_spi_dev, &tx);
}

int read_spi_reg_8_8(uint8_t reg)
{
    uint8_t tx_buf[1] = {reg & 0x7f};
    uint8_t rx_buf[2] = {0, 0};
    const struct spi_buf tx_bufs[] = {
        {.buf = tx_buf, .len = sizeof(tx_buf)},
    };
    const struct spi_buf rx_bufs[] = {
        {.buf = rx_buf, .len = sizeof(rx_buf)},
    };
    struct spi_buf_set tx = {
        .buffers = {&tx_bufs}, .count = 1};
    struct spi_buf_set rx = {
        .buffers = {&rx_bufs}, .count = 1};

    ASSERT_OK(spi_transceive_dt(&camera_spi_dev, &tx, &rx));

    return rx_buf[1];
}

int read_spi_single(uint8_t reg)
{
    uint8_t tx_buf[1] = {reg};
    uint8_t rx_buf[1] = {0};
    const struct spi_buf tx_bufs[] = {
        {.buf = tx_buf, .len = sizeof(tx_buf)},
    };
    const struct spi_buf rx_bufs[] = {
        {.buf = rx_buf, .len = sizeof(rx_buf)},
    };
    struct spi_buf_set tx = {
        .buffers = {&tx_bufs}, .count = 1};
    struct spi_buf_set rx = {
        .buffers = {&rx_bufs}, .count = 1};

    ASSERT_OK(spi_transceive_dt(&camera_spi_dev, &tx, &rx));

    return rx_buf[0];
}

int read_bit(uint8_t addr, uint8_t bit)
{
    uint8_t temp;
    int out = read_spi_reg_8_8(addr);
    if (out < 0)
    {
        return out;
    }
    else
    {
        temp = out;
    }
    temp = temp & bit;
    return temp;
}

int read_spi_buffer(uint8_t reg, uint8_t *data, uint32_t len)
{
    uint8_t tx_buf[1] = {reg};
    const struct spi_buf tx_bufs[] = {
        {.buf = tx_buf, .len = sizeof(tx_buf)},
    };
    const struct spi_buf rx_bufs[] = {
        {.buf = data, .len = len},
    };
    struct spi_buf_set tx = {
        .buffers = {&tx_bufs}, .count = 1};
    struct spi_buf_set rx = {
        .buffers = {&rx_bufs}, .count = 1};

    return spi_transceive_dt(&camera_spi_dev, &tx, &rx);
}

//
// Implementation
//

uint8_t img_buffer[6000];

int camera_start()
{

    // Check if the I2C bus is ready
    if (!device_is_ready(camera_i2c_dev.bus))
    {
        printk("I2C bus %s is not ready!\n", camera_i2c_dev.bus->name);
        return -1;
    }

    // Check if the SPI device is ready
    if (!device_is_ready(camera_spi_dev.bus))
    {
        printk("SPI device not found!\n");
        return -1;
    }

    // Disable SD Card
    ASSERT_OK(gpio_pin_configure(gpio0_port, 28, GPIO_OUTPUT_ACTIVE));
    ASSERT_OK(gpio_pin_configure(gpio1_port, 8, GPIO_OUTPUT_ACTIVE));

    // Reset SPI
    ASSERT_OK(write_reg_8_8(0x07, 0x80));
    k_sleep(K_MSEC(100));
    ASSERT_OK(write_reg_8_8(0x07, 0x00));
    k_sleep(K_MSEC(100));

    // Check SPI
    ASSERT_OK(write_spi_reg_8_8(0x00, 0x55));
    int output = read_spi_reg_8_8(0x00);
    printk("SPI test: %d\n", output);

    // Read chip ID from i2c
    uint8_t id_high, id_low;
    ASSERT_OK(i2c_reg_read_byte_dt(&camera_i2c_dev, 0x0A, &id_high));
    ASSERT_OK(i2c_reg_read_byte_dt(&camera_i2c_dev, 0x0B, &id_low));
    uint16_t id = (id_high << 8) | id_low;
    printk("Camera ID: 0x%04X\n", id);

    // Configuring
    ASSERT_OK(write_reg_8_8(0xff, 0x01));
    ASSERT_OK(write_reg_8_8(0x12, 0x80));
    k_sleep(K_MSEC(100));
    ASSERT_OK(write_regs(OV2640_JPEG_INIT));
    ASSERT_OK(write_regs(OV2640_YUV422));
    ASSERT_OK(write_regs(OV2640_JPEG));
    ASSERT_OK(write_reg_8_8(0xff, 0x01));
    ASSERT_OK(write_reg_8_8(0x15, 0x00));
    ASSERT_OK(write_regs(OV2640_320x240_JPEG));

    printk("Camera started\n");

    return 0;
}

int take_photo()
{
    // Start capture
    ASSERT_OK(write_spi_reg_8_8(0x04, 0x01)); // Flush FIFO
    ASSERT_OK(write_spi_reg_8_8(0x04, 0x02)); // Start Capture

    // Wait for capture to finish
    while (1)
    {
        if (read_bit(0x41, 0x08))
        {
            printk("Capture done\n");
            break;
        }
        else
        {
            k_sleep(K_MSEC(100));
        }
    }

    // Read length
    int size1 = read_spi_reg_8_8(0x42);
    int size2 = read_spi_reg_8_8(0x43);
    int size3 = read_spi_reg_8_8(0x44);
    ASSERT_OK(size1);
    ASSERT_OK(size2);
    ASSERT_OK(size3);
    int length = ((size3 << 16) | (size2 << 8) | size1) & 0x07fffff;
    printk("Length: %d\n", length);

    // Read buffer
    // ASSERT_OK(read_spi_single(0x3C));
    ASSERT_OK(read_spi_buffer(0x3C, img_buffer, length));
    for (int i = 1; i < length; i++)
    {
        printk("%02X", img_buffer[i]);
    }
    printk("\n");
    printk("Buffer read\n");

    // Clear FIFO
    ASSERT_OK(write_spi_reg_8_8(0x04, 0x01)); // Flush FIFO
}