#ifndef BLE_PERM_H
#define BLE_PERM_H

#include <zephyr/bluetooth/gatt.h>

/* Attribute permissions for every characteristic that carries user content
 * (microphone audio, stored recordings, button/motion events) or changes device
 * state (mic gain, LED dim ratio, RTC, haptics, speaker).
 *
 * With CONFIG_OMI_REQUIRE_BLE_ENCRYPTION these resolve to the _ENCRYPT variants,
 * so the ATT layer rejects reads/writes/CCC subscriptions until SMP has raised
 * the link to BT_SECURITY_L2. Device Information, Battery and the Omi features
 * bitmap deliberately keep plain permissions: they expose no user content and
 * the phone reads them to decide what to do next.
 */
#if defined(CONFIG_OMI_REQUIRE_BLE_ENCRYPTION)
#define OMI_GATT_PERM_READ BT_GATT_PERM_READ_ENCRYPT
#define OMI_GATT_PERM_WRITE BT_GATT_PERM_WRITE_ENCRYPT
#else
#define OMI_GATT_PERM_READ BT_GATT_PERM_READ
#define OMI_GATT_PERM_WRITE BT_GATT_PERM_WRITE
#endif

#define OMI_GATT_PERM_CCC (OMI_GATT_PERM_READ | OMI_GATT_PERM_WRITE)

#endif
