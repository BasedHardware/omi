#include <stdio.h>

#include "../../src/lib/core/button_input.c"

int64_t fake_now;
static enum button_input_event received[100];
static unsigned received_count;
static bool initial_level;

static int read_level(void)
{
    assert(input_lock.locked);
    return initial_level;
}

static void record_event(enum button_input_event event)
{
    assert(!input_lock.locked);
    received[received_count++] = event;
}

static void reset(bool initially_pressed)
{
    gesture = (struct button_gesture) {0};
    input_work.due = INT64_MAX;
    work_at = NO_DEADLINE;
    edge_count = 0;
    overflowed = started = false;
    received_count = 0;
    fake_now = 0;
    initial_level = initially_pressed;
    button_input_start(record_event, read_level);
}

static void run_to(int64_t time)
{
    assert(time >= fake_now);
    unsigned runs = 0;
    while (input_work.due <= time) {
        assert(++runs < 100);
        fake_now = input_work.due;
        input_work.due = INT64_MAX;
        input_work.handler(&input_work.work);
    }
    fake_now = time;
}

static void edge(int64_t time, bool pressed)
{
    run_to(time);
    button_input_edge(pressed);
}

static void expect_idle(void)
{
    assert(input_work.due == INT64_MAX);
    unsigned count = received_count;
    run_to(fake_now + 100000);
    assert(received_count == count);
}

int main(void)
{
    reset(false);
    expect_idle();
    assert(received_count == 0);

    reset(false);
    edge(0, true);
    edge(100, false);
    run_to(299);
    assert(received_count == 0);
    run_to(300);
    assert(received_count == 1 && received[0] == BUTTON_INPUT_SINGLE);
    run_to(340);
    assert(received_count == 2 && received[1] == BUTTON_INPUT_RELEASE);
    expect_idle();

    reset(false);
    edge(0, true);
    edge(80, false);
    edge(200, true);
    edge(280, false);
    run_to(500);
    assert(received_count == 2 && received[0] == BUTTON_INPUT_DOUBLE && received[1] == BUTTON_INPUT_RELEASE);
    expect_idle();

    /* A second held press suppresses the first single, as in the shipped FSM. */
    reset(false);
    edge(0, true);
    edge(80, false);
    edge(250, true);
    edge(540, false);
    run_to(580);
    assert(received_count == 2 && received[0] == BUTTON_INPUT_DOUBLE && received[1] == BUTTON_INPUT_RELEASE);
    expect_idle();

    /* A medium press emits only release; the tap boundary is strictly <300ms. */
    reset(false);
    edge(0, true);
    edge(300, false);
    run_to(340);
    assert(received_count == 1 && received[0] == BUTTON_INPUT_RELEASE);
    expect_idle();

    reset(true);
    button_input_start(record_event, read_level); /* reconnect activation is idempotent */
    run_to(2999);
    assert(received_count == 0);
    run_to(3000);
    assert(received_count == 1 && received[0] == BUTTON_INPUT_LONG);
    expect_idle(); /* no repeat work while a long press remains held */
    edge(fake_now, false);
    run_to(fake_now + 40);
    assert(received_count == 2 && received[1] == BUTTON_INPUT_RELEASE);
    expect_idle();

    reset(false);
    edge(0, true);
    edge(2999, false);
    run_to(3040);
    assert(received_count == 1 && received[0] == BUTTON_INPUT_RELEASE);
    expect_idle();

    /* Mechanical bounce and sub-debounce pulses produce no synthetic gesture. */
    reset(false);
    edge(0, true);
    edge(5, false);
    edge(10, true);
    edge(15, false);
    run_to(100);
    assert(received_count == 0);
    expect_idle();

    /* SD contention stalls work, but ISR timestamps preserve both complete taps. */
    reset(false);
    fake_now = 1000;
    button_input_edge(true);
    fake_now = 1080;
    button_input_edge(false);
    fake_now = 1200;
    button_input_edge(true);
    fake_now = 1280;
    button_input_edge(false);
    fake_now = 8000;
    input_work.due = INT64_MAX;
    input_work.handler(&input_work.work);
    assert(received_count == 2 && received[0] == BUTTON_INPUT_DOUBLE && received[1] == BUTTON_INPUT_RELEASE);
    expect_idle();

    /* A hold already past 3s is delivered immediately when contention clears. */
    reset(false);
    fake_now = 1000;
    button_input_edge(true);
    fake_now = 4100;
    input_work.due = INT64_MAX;
    input_work.handler(&input_work.work);
    assert(received_count == 1 && received[0] == BUTTON_INPUT_LONG);
    expect_idle();

    /* A delayed worker must not turn a completed 2999ms press into power-off. */
    reset(false);
    fake_now = 0;
    button_input_edge(true);
    fake_now = 2999;
    button_input_edge(false);
    fake_now = 9000;
    input_work.due = INT64_MAX;
    input_work.handler(&input_work.work);
    assert(received_count == 1 && received[0] == BUTTON_INPUT_RELEASE);
    expect_idle();

    /* Overflow resynchronizes from the latest release, never a stale held level. */
    reset(false);
    for (unsigned i = 0; i < EDGE_CAPACITY + 10; ++i) {
        fake_now = i;
        button_input_edge(i % 2 == 0);
    }
    fake_now = 10000;
    input_work.due = INT64_MAX;
    input_work.handler(&input_work.work);
    assert(received_count == 0);
    expect_idle();

    reset(false);
    int64_t base = (int64_t) UINT32_MAX + 5000;
    edge(base, true);
    edge(base + 100, false);
    run_to(base + 340);
    assert(received_count == 2 && received[0] == BUTTON_INPUT_SINGLE && received[1] == BUTTON_INPUT_RELEASE);
    expect_idle();

    puts("button input: idle, gestures, debounce, delayed ISR edges, overflow, uptime passed");
    return 0;
}
