#ifndef OMI_SD_WORKER_WAIT_H
#define OMI_SD_WORKER_WAIT_H

#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

enum sd_worker_event { SD_WORKER_REQUEST, SD_WORKER_FLUSH_DUE, SD_WORKER_CONNECT_FLUSH };

/* A binary notification covers both queues and the out-of-band connect flush.
 * Give after publishing: an arrival between the empty checks and the wait is
 * retained by the semaphore. Queue contents remain the authority for ordering. */
static inline int sd_worker_enqueue(struct k_msgq *queue, const void *request, k_timeout_t timeout, struct k_sem *wake)
{
    int ret = k_msgq_put(queue, request, timeout);
    if (ret == 0) {
        k_sem_give(wake);
    }
    return ret;
}

static inline enum sd_worker_event sd_worker_next(struct k_msgq *priority,
                                                  struct k_msgq *normal,
                                                  struct k_sem *wake,
                                                  atomic_t *connect_flush,
                                                  void *request,
                                                  int64_t flush_at)
{
    for (;;) {
        if (atomic_cas(connect_flush, 1, 0)) {
            return SD_WORKER_CONNECT_FLUSH;
        }
        if (k_msgq_get(priority, request, K_NO_WAIT) == 0) {
            return SD_WORKER_REQUEST;
        }
        int64_t remaining = flush_at < 0 ? -1 : flush_at - k_uptime_get();
        if (flush_at >= 0 && remaining <= 0) {
            return SD_WORKER_FLUSH_DUE;
        }
        if (k_msgq_get(normal, request, K_NO_WAIT) == 0) {
            return SD_WORKER_REQUEST;
        }
        (void) k_sem_take(wake, flush_at < 0 ? K_FOREVER : K_MSEC(remaining));
    }
}

static inline int64_t
sd_worker_flush_deadline(bool mounted, bool dirty, int64_t last_activity, int64_t retry_at, int64_t interval)
{
    if (!mounted || !dirty) {
        return -1;
    }
    int64_t deadline = last_activity + interval;
    return deadline > retry_at ? deadline : retry_at;
}

#endif
