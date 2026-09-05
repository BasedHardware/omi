#ifndef STARTUP_H
#define STARTUP_H

/**
 * @brief Initializes optional offline storage without aborting device startup.
 */
void startup_init_optional_storage(void);

/**
 * @brief Starts BLE transport with the offline storage availability determined at startup.
 *
 * @return 0 if successful, negative errno code if transport startup fails
 */
int startup_start_transport(void);

#endif
