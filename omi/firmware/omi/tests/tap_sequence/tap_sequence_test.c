#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "tap_sequence.h"

#define POLL_MS 40
#define MAX_EVENTS 16

struct recorded {
    int kind;
    int count;
    uint32_t at_ms;
};

static struct tap_sequence seq;
static struct recorded events[MAX_EVENTS];
static int event_count;
static uint32_t now_ms;
static int failures;

static void reset(uint32_t start_ms)
{
    memset(&seq, 0, sizeof(seq));
    memset(events, 0, sizeof(events));
    event_count = 0;
    now_ms = start_ms;
}

static void hold(bool pressed, uint32_t duration_ms)
{
    uint32_t end = now_ms + duration_ms;
    do {
        uint8_t count = 0;
        enum tap_sequence_event event = tap_sequence_update(&seq, pressed, now_ms, &count);
        if (event != TAP_SEQUENCE_NONE && event_count < MAX_EVENTS) {
            events[event_count].kind = event;
            events[event_count].count = count;
            events[event_count].at_ms = now_ms;
            event_count++;
        }
        now_ms += POLL_MS;
    } while (now_ms < end);
}

static void expect_events(const char *name, const int *expected, int pairs)
{
    int ok = event_count == pairs;
    for (int i = 0; ok && i < pairs; i++) {
        ok = events[i].kind == expected[2 * i] && events[i].count == expected[2 * i + 1];
    }
    if (!ok) {
        failures++;
        printf("FAIL %s: got", name);
        for (int i = 0; i < event_count; i++) {
            printf(" (%d,%d)", events[i].kind, events[i].count);
        }
        printf("\n");
    } else {
        printf("ok   %s\n", name);
    }
}

int main(void)
{
    reset(0);
    hold(true, 120);
    hold(false, 600);
    expect_events("single tap reports the tap then the end", (int[]){TAP_SEQUENCE_TAP, 1, TAP_SEQUENCE_END, 1}, 2);

    reset(0);
    hold(true, 120);
    hold(false, 160);
    hold(true, 120);
    hold(false, 600);
    expect_events("double tap counts up and ends once",
                  (int[]){TAP_SEQUENCE_TAP, 1, TAP_SEQUENCE_TAP, 2, TAP_SEQUENCE_END, 2},
                  3);

    reset(0);
    for (int i = 0; i < 3; i++) {
        hold(true, 120);
        hold(false, 160);
    }
    hold(false, 600);
    expect_events(
        "triple tap", (int[]){TAP_SEQUENCE_TAP, 1, TAP_SEQUENCE_TAP, 2, TAP_SEQUENCE_TAP, 3, TAP_SEQUENCE_END, 3}, 4);

    reset(0);
    hold(true, 120);
    hold(false, 120);
    uint32_t release_ms = events[0].at_ms;
    hold(false, 600);
    int waited = event_count == 2 && events[1].at_ms - release_ms > TAP_SEQUENCE_GAP_MS &&
                 events[1].at_ms - release_ms <= TAP_SEQUENCE_GAP_MS + POLL_MS;
    if (!waited) {
        failures++;
        printf("FAIL end arrives one poll after the gap\n");
    } else {
        printf("ok   end arrives one poll after the gap\n");
    }

    reset(0);
    hold(true, 120);
    hold(false, 160);
    hold(true, 1000);
    hold(false, 600);
    expect_events(
        "a hold after a tap ends the sequence while still held", (int[]){TAP_SEQUENCE_TAP, 1, TAP_SEQUENCE_END, 1}, 2);

    reset(0);
    hold(true, 1000);
    hold(false, 600);
    expect_events("a hold on its own reports nothing", (int[]){0}, 0);

    reset(UINT32_MAX - 200);
    hold(true, 120);
    hold(false, 160);
    hold(true, 120);
    hold(false, 600);
    expect_events(
        "timing survives uptime wraparound", (int[]){TAP_SEQUENCE_TAP, 1, TAP_SEQUENCE_TAP, 2, TAP_SEQUENCE_END, 2}, 3);

    if (failures) {
        printf("%d failure(s)\n", failures);
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
