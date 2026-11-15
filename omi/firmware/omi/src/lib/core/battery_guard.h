#ifndef BATTERY_GUARD_H
#define BATTERY_GUARD_H

#include <stdbool.h>
#include <stdint.h>

/* Critical-battery shutdown policy (committee item 6, 3.0.24).
 *
 * One raw reading used to power the pendant off, even on the charger. Now a
 * shutdown needs BATTERY_CRITICAL_SAMPLES consecutive readings below
 * BATTERY_CRITICAL_MV while not charging. A reading at or above the
 * threshold, or any charging sample, resets the run. Failed reads are not
 * fed in and leave the run unchanged.
 */
#define BATTERY_CRITICAL_MV 3500
#define BATTERY_CRITICAL_SAMPLES 3

struct battery_critical_guard {
    uint8_t low_samples;
};

/** Feed one successful reading; true when the device should shut down now. */
bool battery_critical_should_shutdown(struct battery_critical_guard *guard, uint16_t millivolts, bool charging);

#endif
