#include <stdio.h>
#include <stdlib.h>

#include "../src/lib/core/idle_sleep.h"

static int failures = 0;

static void check(bool condition, const char *what)
{
    if (!condition) {
        printf("FAIL: %s\n", what);
        failures++;
    }
}

static uint32_t seconds_until_sleep(struct omi_idle_inputs in, uint32_t timeout_seconds, uint32_t limit)
{
    uint32_t idle_seconds = 0;
    for (uint32_t elapsed = 1; elapsed <= limit; elapsed++) {
        if (omi_idle_tick(&in, 1, timeout_seconds, &idle_seconds)) {
            return elapsed;
        }
    }
    return 0;
}

int main(void)
{
    struct omi_idle_inputs idle = {0};
    check(!omi_idle_is_busy(&idle), "disconnected online-only build is idle");
    check(seconds_until_sleep(idle, 5, 20) == 5, "sleeps exactly at the timeout");

    struct omi_idle_inputs charging = {.charging = true};
    check(omi_idle_is_busy(&charging), "charging is busy");
    check(seconds_until_sleep(charging, 5, 20) == 0, "never sleeps while charging");

    struct omi_idle_inputs streaming = {.connected = true, .audio_subscribed = true};
    check(omi_idle_is_busy(&streaming), "streaming audio is busy");
    check(seconds_until_sleep(streaming, 5, 20) == 0, "never sleeps while streaming audio");

    struct omi_idle_inputs connected_silent = {.connected = true};
    check(!omi_idle_is_busy(&connected_silent), "connected without audio subscription is idle");

    struct omi_idle_inputs syncing = {.connected = true, .storage_transfer_active = true};
    check(omi_idle_is_busy(&syncing), "storage sync transfer is busy");
    check(seconds_until_sleep(syncing, 5, 20) == 0, "never sleeps mid storage sync");

    struct omi_idle_inputs offline = {.offline_capture_possible = true};
    check(omi_idle_is_busy(&offline), "offline capture build is always busy");
    check(seconds_until_sleep(offline, 5, 20) == 0, "never sleeps when offline capture is possible");

    uint32_t idle_seconds = 0;
    struct omi_idle_inputs blip = {0};
    check(!omi_idle_tick(&blip, 1, 5, &idle_seconds), "no sleep before timeout");
    check(!omi_idle_tick(&blip, 1, 5, &idle_seconds), "no sleep before timeout");
    check(idle_seconds == 2, "idle accumulates");
    blip.charging = true;
    check(!omi_idle_tick(&blip, 1, 5, &idle_seconds), "activity does not sleep");
    check(idle_seconds == 0, "activity resets the idle counter");

    idle_seconds = 0;
    struct omi_idle_inputs disabled = {0};
    check(!omi_idle_tick(&disabled, 1, 0, &idle_seconds), "timeout 0 disables sleep");
    check(seconds_until_sleep(disabled, 0, 20) == 0, "timeout 0 never sleeps");

    check(omi_idle_is_busy(NULL), "null inputs are treated as busy");
    check(!omi_idle_tick(&idle, 1, 5, NULL), "null counter is a no-op");

    if (failures != 0) {
        printf("%d idle-sleep assertion(s) failed\n", failures);
        return EXIT_FAILURE;
    }
    printf("idle-sleep policy tests passed\n");
    return EXIT_SUCCESS;
}
