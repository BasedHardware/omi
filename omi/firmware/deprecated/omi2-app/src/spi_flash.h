/**
 * @file spi_flash.h
 * @brief Header file for SPI flash memory operations
 *
 * This module provides functions to interact with an external SPI flash memory
 * device using the Zephyr RTOS flash API. It supports operations like reading
 * flash ID, erasing, reading, and writing data.
 */
#ifndef APP_SRC_FLASH_H_
#define APP_SRC_FLASH_H_

/**
 * @brief Initialize the SPI flash interface
 *
 * This function initializes the SPI flash interface and puts the flash
 * device in a low-power suspended state until needed.
 *
 * @return 0 on success, negative errno code on failure
 */
int flash_init(void);

#endif /* APP_SRC_FLASH_H_ */
