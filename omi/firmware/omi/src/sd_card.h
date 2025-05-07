#ifndef SD_H
#define SD_H

#include <zephyr/kernel.h>

/**
 * @brief Initialize the SD card module interface.
 *
 * @return 0 on success, negative error code otherwise.
 */
int app_sd_init(void);

/**
 * @brief Put the SD card interface (controller) into a low-power (suspend) state.
 *        Note: This typically suspends the SPI controller managing the SD card slot.
 *
 * @return 0 on success, negative error code on failure to suspend.
 */
int app_sd_off(void);

#endif // SD_H
