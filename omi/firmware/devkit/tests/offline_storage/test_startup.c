#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "startup.h"

static int mount_result;
static int storage_result;
static int transport_result;
static int mount_calls;
static int storage_calls;
static int transport_calls;
static int sleep_calls;
static int32_t last_sleep_ms;
static bool last_transport_storage_available;
static bool sd_on;
static int sd_off_calls;
// mount_sd_card() powers the card before the steps that can fail, so a failed
// mount normally leaves it on; only the early GPIO-not-ready exit does not.
static bool mount_powers_sd;

static void reset_fakes(void)
{
    mount_result = 0;
    storage_result = 0;
    transport_result = 0;
    mount_calls = 0;
    storage_calls = 0;
    transport_calls = 0;
    sleep_calls = 0;
    last_sleep_ms = 0;
    last_transport_storage_available = false;
    sd_on = false;
    sd_off_calls = 0;
    mount_powers_sd = true;
}

int mount_sd_card(void)
{
    mount_calls++;
    if (mount_powers_sd) {
        sd_on = true;
    }
    return mount_result;
}

bool is_sd_on(void)
{
    return sd_on;
}

void sd_off(void)
{
    sd_off_calls++;
    sd_on = false;
}

int storage_init(void)
{
    storage_calls++;
    return storage_result;
}

int transport_start(bool offline_storage_available)
{
    transport_calls++;
    last_transport_storage_available = offline_storage_available;
    return transport_result;
}

int32_t k_msleep(int32_t ms)
{
    sleep_calls++;
    last_sleep_ms = ms;
    return 0;
}

static void test_storage_success(void)
{
    reset_fakes();

    startup_init_optional_storage();
    int result = startup_start_transport();

    assert(result == 0);
    assert(mount_calls == 1);
    assert(storage_calls == 1);
    assert(sleep_calls == 1);
    assert(last_sleep_ms == 500);
    assert(transport_calls == 1);
    assert(last_transport_storage_available);
    assert(sd_off_calls == 0);
    assert(sd_on);
}

static void test_mount_failure_still_starts_transport(void)
{
    reset_fakes();
    mount_result = -EIO;

    startup_init_optional_storage();
    int result = startup_start_transport();

    assert(result == 0);
    assert(mount_calls == 1);
    assert(storage_calls == 0);
    assert(sleep_calls == 0);
    assert(transport_calls == 1);
    assert(!last_transport_storage_available);
    assert(sd_off_calls == 1);
    assert(!sd_on);
}

static void test_mount_failure_before_power_on_skips_sd_off(void)
{
    reset_fakes();
    mount_result = -EIO;
    mount_powers_sd = false;

    startup_init_optional_storage();
    int result = startup_start_transport();

    assert(result == 0);
    assert(sd_off_calls == 0);
    assert(transport_calls == 1);
    assert(!last_transport_storage_available);
}

static void test_storage_failure_still_starts_transport(void)
{
    reset_fakes();
    storage_result = -ENOMEM;

    startup_init_optional_storage();
    int result = startup_start_transport();

    assert(result == 0);
    assert(mount_calls == 1);
    assert(storage_calls == 1);
    assert(sleep_calls == 1);
    assert(last_sleep_ms == 500);
    assert(transport_calls == 1);
    assert(!last_transport_storage_available);
    assert(sd_off_calls == 1);
    assert(!sd_on);
}

static void test_transport_failure_is_propagated(void)
{
    reset_fakes();
    transport_result = -ENETDOWN;

    startup_init_optional_storage();
    int result = startup_start_transport();

    assert(result == -ENETDOWN);
    assert(transport_calls == 1);
    assert(last_transport_storage_available);

    reset_fakes();
    mount_result = -EIO;
    transport_result = -ENETDOWN;

    startup_init_optional_storage();
    result = startup_start_transport();

    assert(result == -ENETDOWN);
    assert(transport_calls == 1);
    assert(!last_transport_storage_available);
}

int main(void)
{
    test_storage_success();
    test_mount_failure_still_starts_transport();
    test_mount_failure_before_power_on_skips_sd_off();
    test_storage_failure_still_starts_transport();
    test_transport_failure_is_propagated();
    puts("DevKit offline storage startup tests passed");
    return 0;
}
