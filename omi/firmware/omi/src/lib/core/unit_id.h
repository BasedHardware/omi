#ifndef UNIT_ID_H
#define UNIT_ID_H

#include <stddef.h>

/* 8-byte nRF FICR device ID rendered as 16 uppercase hex characters. */
#define UNIT_ID_HEX_LEN 16

/**
 * @brief Read the immutable per-unit hardware ID as a hex string.
 *
 * The ID comes from the SoC factory information (FICR DEVICEID) via the
 * Zephyr hwinfo driver. It survives reflashing, NVS erase and BLE identity
 * regeneration, so it can key a factory serial/lot roster.
 *
 * @param out Output buffer, at least UNIT_ID_HEX_LEN + 1 bytes
 * @param len Size of @p out
 * @return 0 on success, negative errno on failure
 */
int unit_id_get(char *out, size_t len);

/**
 * @brief Publish the unit ID as the BLE DIS Serial Number String (0x2A25).
 *
 * Must run after settings_load() so a stale persisted "bt/dis/serial" value
 * cannot override the hardware ID. Also prints UNIT_ID on the console next to
 * BLE_ADDR for production-line fixture parsing.
 *
 * @return 0 on success, negative errno on failure
 */
int unit_id_publish(void);

#endif // UNIT_ID_H
