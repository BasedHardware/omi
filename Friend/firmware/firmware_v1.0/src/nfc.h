#ifndef NFC_H
#define NFC_H

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

#endif /* NFC_H */
