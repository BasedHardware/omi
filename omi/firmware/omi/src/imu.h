#ifndef OMI_IMU_H_
#define OMI_IMU_H_

#include <stdbool.h>
#include <stdint.h>

/**
 * @brief Prepare the system-off time-recovery boundary.
 *
 * CV1 currently has no sound sub-wrap duration bound, so this consumes any
 * legacy marker and deliberately does not arm elapsed-time recovery.
 */
int lsm6dsl_time_prepare_for_system_off(void);

/**
 * @brief On boot, consume any one-shot system-off time marker.
 *
 * A recovery marker is considered only for verified system-off wake
 * provenance. The current CV1 24-bit counter has no independently enforced
 * sub-wrap sleep bound, so production consumes any marker and leaves UTC
 * invalid for live phone synchronization.
 *
 * @param verified_system_off_wake True only when hardware reset provenance
 * confirms wake from system-off.
 *
 * @return 1 if a bounded adjustment was applied, 0 if not applicable, negative
 * errno on failure.
 */
int lsm6dsl_time_boot_adjust_rtc(bool verified_system_off_wake);

#endif
