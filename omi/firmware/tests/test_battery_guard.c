/* Critical-battery shutdown policy: debounce and charger suppression. */
#include <assert.h>
#include <stdio.h>

#include "../omi/src/lib/core/battery_guard.c"

int main(void)
{
    struct battery_critical_guard g = {0};
    /* A single dip below the threshold never shuts down. */
    assert(!battery_critical_should_shutdown(&g, 3400, false));
    assert(!battery_critical_should_shutdown(&g, 3600, false));
    assert(!battery_critical_should_shutdown(&g, 3400, false));
    assert(!battery_critical_should_shutdown(&g, 3400, false));
    /* The third consecutive low reading does. */
    assert(battery_critical_should_shutdown(&g, 3400, false));

    /* Boundary: exactly the threshold is not critical. */
    g = (struct battery_critical_guard){0};
    for (int i = 0; i < 10; ++i) {
        assert(!battery_critical_should_shutdown(&g, BATTERY_CRITICAL_MV, false));
    }
    for (int i = 0; i < BATTERY_CRITICAL_SAMPLES - 1; ++i) {
        assert(!battery_critical_should_shutdown(&g, BATTERY_CRITICAL_MV - 1, false));
    }
    assert(battery_critical_should_shutdown(&g, BATTERY_CRITICAL_MV - 1, false));

    /* Charging suppresses the shutdown no matter how low or how long. */
    g = (struct battery_critical_guard){0};
    for (int i = 0; i < 1000; ++i) {
        assert(!battery_critical_should_shutdown(&g, 3000, true));
    }
    /* ... and a charging sample resets a run in progress. */
    assert(!battery_critical_should_shutdown(&g, 3000, false));
    assert(!battery_critical_should_shutdown(&g, 3000, false));
    assert(!battery_critical_should_shutdown(&g, 3000, true));
    assert(!battery_critical_should_shutdown(&g, 3000, false));
    assert(!battery_critical_should_shutdown(&g, 3000, false));
    assert(battery_critical_should_shutdown(&g, 3000, false));
    /* The run saturates instead of wrapping. */
    for (int i = 0; i < 1000; ++i) {
        assert(battery_critical_should_shutdown(&g, 3000, false));
    }
    puts("battery guard: debounce, threshold boundary and charger suppression tests passed");
    return 0;
}
