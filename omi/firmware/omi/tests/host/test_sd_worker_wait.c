#include <stdio.h>

#include "../../src/lib/core/sd_worker_wait.h"

int64_t fake_now;
static struct k_msgq priority, normal;
static struct k_sem wake;
static atomic_t connect_flush;
static unsigned waits;
static k_timeout_t observed_wait;
static void (*during_wait)(void);

int k_sem_take(struct k_sem *sem, k_timeout_t timeout)
{
    ++waits;
    observed_wait = timeout;
    if (sem->count) {
        sem->count = 0;
        return 0;
    }
    if (during_wait) {
        void (*hook)(void) = during_wait;
        during_wait = NULL;
        hook();
    }
    if (sem->count) {
        sem->count = 0;
        return 0;
    }
    assert(timeout != K_FOREVER); /* an unnotified request would hang production */
    fake_now += timeout;
    return -EAGAIN;
}

static void reset(void)
{
    priority = normal = (struct k_msgq){0};
    wake = (struct k_sem){0};
    connect_flush = 0;
    fake_now = 0;
    waits = 0;
    during_wait = NULL;
}

static void put_normal(void)
{
    int request = 42;
    assert(sd_worker_enqueue(&normal, &request, K_NO_WAIT, &wake) == 0);
}

static void put_power_request(void)
{
    int request = 99;
    assert(sd_worker_enqueue(&priority, &request, K_NO_WAIT, &wake) == 0);
}

static void put_connect_flush(void)
{
    connect_flush = 1;
    k_sem_give(&wake);
}

static enum sd_worker_event next(int *request, int64_t deadline)
{
    return sd_worker_next(&priority, &normal, &wake, &connect_flush, request, deadline);
}

int main(void)
{
    int request;
    reset();
    assert(sd_worker_flush_deadline(true, false, 0, 0, 1000) == -1);
    assert(sd_worker_flush_deadline(false, true, 0, 0, 1000) == -1);
    during_wait = put_normal;
    assert(next(&request, -1) == SD_WORKER_REQUEST && request == 42);
    assert(waits == 1 && observed_wait == K_FOREVER);

    /* Priority power/read requests wake an otherwise indefinitely idle worker. */
    reset();
    during_wait = put_power_request;
    assert(next(&request, -1) == SD_WORKER_REQUEST && request == 99);
    assert(waits == 1 && observed_wait == K_FOREVER);

    /* Both queues were published before waiting: priority wins, normal stays FIFO. */
    reset();
    for (int i = 0; i < 3; ++i) {
        assert(sd_worker_enqueue(&normal, &i, K_NO_WAIT, &wake) == 0);
    }
    put_power_request();
    assert(next(&request, -1) == SD_WORKER_REQUEST && request == 99);
    for (int i = 0; i < 3; ++i) {
        assert(next(&request, -1) == SD_WORKER_REQUEST && request == i);
    }
    assert(waits == 0);
    /* A coalesced notification is consumed once; it cannot cause periodic wakes. */
    during_wait = put_power_request;
    assert(next(&request, -1) == SD_WORKER_REQUEST && request == 99);
    assert(waits == 2 && observed_wait == K_FOREVER);

    /* The hook publishes precisely between empty checks and blocking: no lost wake. */
    reset();
    during_wait = put_normal;
    assert(next(&request, 1000) == SD_WORKER_REQUEST && request == 42);
    assert(fake_now == 0 && observed_wait == 1000);

    reset();
    fake_now = 400;
    int64_t deadline = sd_worker_flush_deadline(true, true, 250, 0, 1000);
    assert(deadline == 1250);
    assert(next(&request, deadline) == SD_WORKER_FLUSH_DUE);
    assert(waits == 1 && observed_wait == 850 && fake_now == 1250);
    /* A failed media flush leaves dirty state but cannot spin at the old deadline. */
    deadline = sd_worker_flush_deadline(true, true, 250, fake_now + 1000, 1000);
    assert(next(&request, deadline) == SD_WORKER_FLUSH_DUE);
    assert(observed_wait == 1000 && fake_now == 2250);

    /* Expired inactivity flush is not postponed by a newly queued normal write. */
    reset();
    put_normal();
    fake_now = 1001;
    assert(next(&request, 1000) == SD_WORKER_FLUSH_DUE && normal.count == 1);
    assert(next(&request, -1) == SD_WORKER_REQUEST && request == 42);

    /* A failed full-queue connect enqueue still has a retained out-of-band wake. */
    reset();
    for (int i = 0; i < 16; ++i) {
        assert(sd_worker_enqueue(&priority, &i, K_NO_WAIT, &wake) == 0);
    }
    assert(sd_worker_enqueue(&priority, &request, K_NO_WAIT, &wake) != 0);
    put_connect_flush();
    assert(next(&request, -1) == SD_WORKER_CONNECT_FLUSH);
    assert(priority.count == 16);
    for (int i = 0; i < 16; ++i) {
        assert(next(&request, -1) == SD_WORKER_REQUEST && request == i);
    }
    wake.count = 0;
    during_wait = put_connect_flush;
    assert(next(&request, -1) == SD_WORKER_CONNECT_FLUSH);
    assert(observed_wait == K_FOREVER);

    puts("SD wait: both queues, priority/FIFO, deadlines, retry bound, retained wake passed");
    return 0;
}
