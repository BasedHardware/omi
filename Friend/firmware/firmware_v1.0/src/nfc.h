#ifndef NFC_H
#define NFC_H

int nfc_sleep(void);
int nfc_wake(void);

#include <zephyr/kernel.h>

/**
 * @brief Initialize NFC functionality
 *
 * This function sets up NFC with the device's pairing ID and URL.
 *
 * @return 0 if successful, negative errno code if error
 */
int nfc_init(void);

/**
 * @brief Update NFC payload
 *
 * This function updates the NFC payload with new data if needed.
 *
 * @param new_data Pointer to the new data
 * @param len Length of the new data
 * @return 0 if successful, negative errno code if error
 */
int nfc_update_payload(const uint8_t *new_data, size_t len);

/**
 * @brief Get Device ID
 *
 * This function fetches the hardware device ID.
 *
 * @param device_id Device ID pointer
 * @param len Length of the device ID
 * @return 0 if successful, negative errno code if error
 */
int get_device_id(char *device_id, size_t len);

#endif /* NFC_H */
