#ifndef STORAGE_H
#define STORAGE_H

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE

#include <stdbool.h>

/**
 * @brief Initializes the Storage Transport thread
 *
 * Initializes the Storage Transport thread
 *
 * @return 0 if successful, negative errno code if error
 */
int storage_init();

#endif // CONFIG_OMI_ENABLE_OFFLINE_STORAGE

#endif // STORAGE_H
