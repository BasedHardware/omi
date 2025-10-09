#ifndef QSPI_FLASH_H__
#define QSPI_FLASH_H__

#include <stdint.h>

/** @brief Initializes QSPI flash module
 *
 *  @retval 0   If the operation was successful.
 *              Otherwise, a (negative) error code is returned.
 */
int qspi_flash_init();

/** @brief Uninitializes the QSPI flash module
 */
void qspi_flash_uninit();

/** @brief Initializes the command handling module
 * 
 *  @param  command. Command to send to the flash
 *
 *  @retval 0   If the operation was successful.
 *              Otherwise, a (negative) error code is returned.
 */
int qspi_flash_command(uint8_t command);

#endif /* QSPI_FLASH_H__ */
