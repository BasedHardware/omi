#include "battery_guard.h"

bool battery_critical_should_shutdown(struct battery_critical_guard *guard, uint16_t millivolts, bool charging)
{
    if (charging || millivolts >= BATTERY_CRITICAL_MV) {
        guard->low_samples = 0;
        return false;
    }
    if (guard->low_samples < BATTERY_CRITICAL_SAMPLES) {
        guard->low_samples++;
    }
    return guard->low_samples >= BATTERY_CRITICAL_SAMPLES;
}
