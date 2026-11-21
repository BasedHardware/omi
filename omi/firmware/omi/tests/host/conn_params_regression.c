#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <zephyr/sys/atomic.h>

#define CONFIG_BT_MAX_CONN 2
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define LOG_INF(...) ignore_log(__VA_ARGS__)
#define LOG_WRN(...) ignore_log(__VA_ARGS__)
static void ignore_log(const char *format, ...)
{
    (void) format;
}

struct bt_conn {
    uint8_t index;
};
struct bt_le_conn_param {
    uint16_t interval_min, interval_max, latency, timeout;
};
static unsigned calls;
static uint16_t requested_timeout;
static int api_error;
#ifdef OMI_CV1_BLE_BASELINE
static unsigned sleeps;
static void k_sleep(unsigned millis)
{
    assert(millis == 300);
    sleeps++;
}
#define K_MSEC(ms) (ms)
#define EXPECTED_TIMEOUT 400
#else
#define EXPECTED_TIMEOUT 600
static uint8_t bt_conn_index(struct bt_conn *conn)
{
    return conn->index;
}
#endif
static int bt_conn_le_param_update(struct bt_conn *conn, const struct bt_le_conn_param *p)
{
    (void) conn;
    assert(p->interval_min == 6 && p->interval_max == 12 && p->latency == 0 && p->timeout == EXPECTED_TIMEOUT);
    /* Convert both sides to microseconds; mixed Bluetooth units must not be compared directly. */
    assert(p->interval_max * 1250U * (p->latency + 1U) * 3U < p->timeout * 10000U);
    requested_timeout = p->timeout;
    calls++;
    return api_error;
}
#ifdef OMI_CV1_BLE_BASELINE
#include "conn_params_baseline_block.inc"
#else
/* Real production request, update callback and lifecycle reset statements. No k_sleep shim:
 * a blocking callback retry fails compilation. */
#include "conn_params_block.inc"
#endif
int main(void)
{
    struct bt_conn a = {0};
#ifndef OMI_CV1_BLE_BASELINE
    connected_reset(&a);
#endif
    update_conn_params(&a); /* Initial request counts toward the same budget. */
    _le_param_updated(&a, 24, 0, 600);
    assert(calls == 1);
    for (unsigned i = 0; i < 8; i++)
        _le_param_updated(&a, 25, 0, 400);
    printf("initial plus eight callbacks: %u requests, timeout %u ms\n", calls, requested_timeout * 10U);
#ifdef OMI_CV1_BLE_BASELINE
    assert(calls == 9 && sleeps == 0);
    api_error = -16;
    _le_param_updated(&a, 25, 0, 400);
    assert(calls == 12 && sleeps == 2);
    printf("immediate API failure: %u sleeps\n", sleeps);
#else
    struct bt_conn b = {1}, invalid = {2};
    assert(calls == 3);
    for (unsigned i = 0; i < 1000; i++)
        _le_param_updated(&a, 25, 0, 400);
    assert(calls == 3);
    _le_param_updated(&a, 6, 0, 600);
    _le_param_updated(&a, 48, 0, 400);
    assert(calls == 3); /* A transient good interval never refills the budget. */
    update_conn_params(&b);
    assert(calls == 4); /* Independent connections do not share a budget. */
    disconnected_reset(&a);
    assert(atomic_get(&conn_param_requests[0]) == 0);
    connected_reset(&a); /* Same-index reconnect gets a fresh, finite budget. */
    api_error = -16;
    for (unsigned i = 0; i < 1000; i++)
        _le_param_updated(&a, 48, 0, 600);
    assert(calls == 7); /* Immediate failures consume attempts too. */
    update_conn_params(&invalid);
    assert(calls == 7);
    puts("PASS timeout, unchanged intervals, refusal cap, API failures, reconnect reset, independent links, "
         "nonblocking callback");
#endif
    return 0;
}
