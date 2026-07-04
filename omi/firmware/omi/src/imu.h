#ifndef OMI_IMU_H_
#define OMI_IMU_H_

#include <stdint.h>

/**
 * @brief Prepare IMU timestamping so time can be estimated across system_off.
 *
 * Stores a (UTC epoch seconds, IMU timestamp counter) base into settings.
 *
 * Safe to call even if the IMU or UTC time is not available.
 */
void lsm6dsl_time_prepare_for_system_off(void);

/**
 * @brief On boot, adjust UTC epoch using IMU timestamp delta.
 *
 * If a valid base was stored before system_off, reads current IMU timestamp and
 * adds the elapsed time to the persisted UTC epoch via rtc_set_utc_time().
 *
 * @return 1 if an adjustment was applied, 0 if not applicable, negative errno on failure.
 */
int lsm6dsl_time_boot_adjust_rtc(void);

/**
 * @brief Power the IMU regulator off.
 *
 * The IMU is only needed at boot and just before system-off, so it can be shut
 * down during normal operation to save power. lsm6dsl_time_prepare_for_system_off()
 * re-powers it.
 */
void lsm6dsl_power_off(void);

#endif
