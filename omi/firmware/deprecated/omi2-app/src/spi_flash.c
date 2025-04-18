/**
 * @file spi_flash.c
 * @brief Implementation of SPI flash memory interface
 *
 * This file implements a command-line interface for interacting with an external
 * SPI flash memory device. It provides shell commands for flash identification,
 * erasing, reading, and writing operations.
 */
#include <stdlib.h>

#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/flash.h>
#include <zephyr/drivers/regulator.h>
#include <zephyr/kernel.h>
#include <zephyr/pm/device.h>
#include <zephyr/shell/shell.h>

/**
 * @brief Device pointer to the SPI flash controller
 * 
 * Uses Zephyr's devicetree macros to get a reference to the SPI flash device
 * defined in the board's device tree.
 */
static const struct device *const flash = DEVICE_DT_GET(DT_NODELABEL(spi_flash));

/**
 * @brief GPIO specification for the SPI MOSI pin
 * 
 * This is used to control the MOSI pin state when the device is idle,
 * as some flash devices require specific idle states.
 */
static const struct gpio_dt_spec flash_mosi = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(flash_mosi_pin), gpios, {0});

/**
 * @brief Initialization state flag
 */
static bool initialized;

/**
 * @brief Shell command handler for reading flash ID
 *
 * Reads and displays the JEDEC ID from the flash chip, which typically contains
 * manufacturer and device information.
 *
 * @param sh Shell instance
 * @param argc Argument count
 * @param argv Arguments
 * @return 0 on success, negative errno code on failure
 */
static int cmd_flash_id(const struct shell *sh, size_t argc, char **argv)
{
	int ret;
	uint8_t id[3];

	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	if (!initialized)
	{
		shell_error(sh, "Flash module not initialized");
		return -EPERM;
	}
	// set up idle state of mosi to high
	gpio_pin_configure_dt(&flash_mosi, GPIO_OUTPUT);
	gpio_pin_set_dt(&flash_mosi, 1);
	ret = pm_device_action_run(flash, PM_DEVICE_ACTION_RESUME);
	if (ret < 0)
	{
		shell_error(sh, "Failed to resume flash (%d)", ret);
		// return ret;
	}

	ret = flash_read_jedec_id(flash, id);
	if (ret < 0)
	{
		shell_error(sh, "Failed to read flash ID (%d)", ret);
		goto end;
	}

	shell_print(sh, "Flash ID: %02x %02x %02x", id[0], id[1], id[2]);

end:
	(void)pm_device_action_run(flash, PM_DEVICE_ACTION_SUSPEND);

	return ret;
}

/**
 * @brief Shell command handler for erasing flash memory
 *
 * Erases a page of flash memory at the specified address. The page size
 * is determined automatically based on the flash device properties.
 *
 * @param sh Shell instance
 * @param argc Argument count
 * @param argv Arguments (expect address in argv[1])
 * @return 0 on success, negative errno code on failure
 */
static int cmd_flash_erase(const struct shell *sh, size_t argc, char **argv)
{
	int ret;
	uint32_t addr;
	struct flash_pages_info info;

	if (!initialized)
	{
		shell_error(sh, "Flash module not initialized");
		return -EPERM;
	}

	if (argc < 2)
	{
		shell_error(sh, "Missing address or size");
		return -EINVAL;
	}

	addr = strtoul(argv[1], NULL, 0);

	gpio_pin_configure_dt(&flash_mosi, GPIO_OUTPUT);
	gpio_pin_set_dt(&flash_mosi, 1);
	ret = pm_device_action_run(flash, PM_DEVICE_ACTION_RESUME);
	if (ret < 0)
	{
		shell_error(sh, "Failed to resume flash (%d)", ret);
		return ret;
	}

	ret = flash_get_page_info_by_offs(flash, addr, &info);
	if (ret < 0)
	{
		shell_error(sh, "Could not determine page size (%d)", ret);
		goto end;
	}

	ret = flash_erase(flash, addr, info.size);
	if (ret < 0)
	{
		shell_error(sh, "Failed to erase flash (%d)", ret);
		goto end;
	}

	shell_print(sh, "Erased %d bytes at 0x%08x", info.size, addr);

end:
	(void)pm_device_action_run(flash, PM_DEVICE_ACTION_SUSPEND);

	return ret;
}

/**
 * @brief Shell command handler for reading flash memory
 *
 * Reads data from flash memory at the specified address and length,
 * displaying it in a hexdump format.
 *
 * @param sh Shell instance
 * @param argc Argument count
 * @param argv Arguments (expect address in argv[1] and length in argv[2])
 * @return 0 on success, negative errno code on failure
 */
static int cmd_flash_read(const struct shell *sh, size_t argc, char **argv)
{
	int ret;
	uint32_t addr;
	uint8_t buf[SHELL_HEXDUMP_BYTES_IN_LINE];
	size_t len;

	if (!initialized)
	{
		shell_error(sh, "Flash module not initialized");
		return -EPERM;
	}

	if (argc < 3)
	{
		shell_error(sh, "Missing address or length");
		return -EINVAL;
	}

	addr = strtoul(argv[1], NULL, 0);
	len = strtoul(argv[2], NULL, 0);
	gpio_pin_configure_dt(&flash_mosi, GPIO_OUTPUT);
	gpio_pin_set_dt(&flash_mosi, 1);
	ret = pm_device_action_run(flash, PM_DEVICE_ACTION_RESUME);
	if (ret < 0)
	{
		shell_error(sh, "Failed to resume flash (%d)", ret);
		return ret;
	}

	while (len > 0U)
	{
		size_t rd = MIN(len, sizeof(buf));

		ret = flash_read(flash, addr, buf, rd);
		if (ret < 0)
		{
			shell_error(sh, "Failed to read from flash (%d)", ret);
			goto end;
		}

		shell_hexdump_line(sh, addr, buf, rd);

		addr += rd;
		len -= rd;
	}

end:
	(void)pm_device_action_run(flash, PM_DEVICE_ACTION_SUSPEND);

	return ret;
}

/**
 * @brief Shell command handler for writing flash memory
 *
 * Writes hex-encoded data to flash memory at the specified address.
 * The data is provided as a hex string (e.g., "01020304").
 *
 * @param sh Shell instance
 * @param argc Argument count
 * @param argv Arguments (expect address in argv[1] and hex data in argv[2])
 * @return 0 on success, negative errno code on failure
 */
static int cmd_flash_write(const struct shell *sh, size_t argc, char **argv)
{
	int ret;
	uint32_t addr;
	uint8_t *buf;
	size_t data_len;

	if (!initialized)
	{
		shell_error(sh, "Flash module not initialized");
		return -EPERM;
	}

	if (argc < 3)
	{
		shell_error(sh, "Missing address or data");
		return -EINVAL;
	}

	addr = strtoul(argv[1], NULL, 0);
	data_len = strlen(argv[2]) / 2U;

	buf = k_malloc(data_len);
	if (buf == NULL)
	{
		shell_error(sh, "Failed to allocate buffer");
		return -ENOMEM;
	}

	// Convert hex string to binary data
	for (size_t i = 0U; i < data_len; i++)
	{
		char hex_byte[3] = {argv[2][i * 2], argv[2][i * 2 + 1], '\0'};
		buf[i] = (uint8_t)strtoul(hex_byte, NULL, 16);
	}
	gpio_pin_configure_dt(&flash_mosi, GPIO_OUTPUT);
	gpio_pin_set_dt(&flash_mosi, 1);
	ret = pm_device_action_run(flash, PM_DEVICE_ACTION_RESUME);
	if (ret < 0)
	{
		shell_error(sh, "Failed to resume flash (%d)", ret);
		k_free(buf);
		return ret;
	}

	ret = flash_write(flash, addr, buf, data_len);
	if (ret < 0)
	{
		shell_error(sh, "Failed to write to flash (%d)", ret);
	}
	else
	{
		shell_print(sh, "Wrote %d bytes to 0x%08x", data_len, addr);
	}

	k_free(buf);

	(void)pm_device_action_run(flash, PM_DEVICE_ACTION_SUSPEND);

	return ret;
}

/**
 * @brief Shell command registration structure
 *
 * Defines the subcommands for the "flash" shell command:
 * - id: Read flash identification
 * - erase: Erase a flash page
 * - read: Read data from flash
 * - write: Write data to flash
 */
SHELL_STATIC_SUBCMD_SET_CREATE(
	sub_flash_cmds, SHELL_CMD(id, NULL, "Read flash ID", cmd_flash_id),
	SHELL_CMD_ARG(erase, NULL, "Erase page: erase PAGE_ADDR", cmd_flash_erase, 2, 0),
	SHELL_CMD_ARG(read, NULL, "Read: read ADDR NUM_BYTES", cmd_flash_read, 3, 0),
	SHELL_CMD_ARG(write, NULL, "Write: write ADDR DATA", cmd_flash_write, 3, 0),
	SHELL_SUBCMD_SET_END);

/**
 * @brief Register the "flash" shell command
 */
SHELL_CMD_REGISTER(flash, &sub_flash_cmds, "Flash", NULL);

/**
 * @brief Initialize the flash module
 *
 * Puts the flash device in a low-power suspended state and marks
 * the module as initialized.
 *
 * @return 0 on success, negative errno code on failure
 */
int flash_init(void)
{
	int ret;
	// pm_device_action_run(flash, PM_DEVICE_ACTION_RESUME);
	// if (!device_is_ready(flash))
	// {	
	// 	pm_device_action_run(flash, PM_DEVICE_ACTION_SUSPEND);
	// 	return -ENODEV;
	// }
	ret = pm_device_action_run(flash, PM_DEVICE_ACTION_SUSPEND);
	if (ret < 0)
	{
		return ret;
	}

	initialized = true;

	return 0;
}
