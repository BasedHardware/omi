#ifndef OMI_LSM6DSO_TIME_H_
#define OMI_LSM6DSO_TIME_H_

#include <stdint.h>

/**
 * @brief Prepare IMU timestamping so time can be estimated across system_off.
 *
 * Stores a (UTC epoch seconds, IMU timestamp counter) base into settings.
 *
 * Safe to call even if the IMU or UTC time is not available.
 */
void lsm6dso_time_prepare_for_system_off(void);

/**
 * @brief On boot, adjust UTC epoch using IMU timestamp delta.
 *
 * If a valid base was stored before system_off, reads current IMU timestamp and
 * adds the elapsed time to the persisted UTC epoch via rtc_set_utc_time().
 *
 * @return 1 if an adjustment was applied, 0 if not applicable, negative errno on failure.
 */
int lsm6dso_time_boot_adjust_rtc(void);

#endif
