#include "storage_adapter.h"

#include <string.h>
static int span(uint32_t offset, size_t n, uint32_t cap)
{
    return n && n <= cap && offset <= cap - n;
}
int cv1_ns_ram_range(uintptr_t p, size_t n)
{
    return n && n <= 0x5e000u && p >= 0x20012000u && p <= 0x20070000u - n;
}
int cv1_internal_range(unsigned area, uint32_t o, size_t n, unsigned op)
{
    uint32_t cap = area == 1 ? 0x2000u : area == 2 ? 0x9c000u : 0;
    if (!span(o, n, cap) || op > 2)
        return 0;
    return op == 0 || (op == 1 ? !(o % 4096 || n % 4096) : !(o % 4 || n % 4));
}
int cv1_nor_range(unsigned b, uint32_t o, size_t n, unsigned op)
{
    if (b > 1 || !span(o, n, CV1_BANK_BYTES) || op > 2)
        return 0;
    return op != 1 || !(o % 4096 || n % 4096);
}
int cv1_storage_init(struct cv1_storage *s, struct cv1_storage_ops ops, uint64_t epoch)
{
    if (!s || !ops.owned || !ops.io || !epoch || epoch > UINT32_MAX)
        return -1;
    /* Only before publication or after reset; never concurrent reinit. */
    memset(s, 0, sizeof(*s));
    atomic_flag_clear(&s->busy);
    s->ops = ops;
    s->epoch = epoch << 32;
    return 0;
}
static int enter(struct cv1_storage *s)
{
    return s && !atomic_flag_test_and_set_explicit(&s->busy, memory_order_acquire);
}
static int leave(struct cv1_storage *s, int rc)
{
    atomic_flag_clear_explicit(&s->busy, memory_order_release);
    return rc;
}
static int owned(struct cv1_storage *s)
{
    if (s->poisoned || s->ops.owned(s->ops.context) != 1) {
        s->poisoned = 1;
        s->lease = 0;
        return 0;
    }
    return 1;
}
int cv1_storage_acquire(struct cv1_storage *s, unsigned bank, uint32_t size, uint64_t *token)
{
    if (!token || !enter(s))
        return -1;
    if (bank > 1 || !size || size > CV1_BANK_BYTES || s->lease || !owned(s))
        return leave(s, -1);
    /* No wrap/reuse within a boot. Epoch assignment is a trusted reset service. */
    if ((s->epoch & UINT32_MAX) == UINT32_MAX) {
        s->poisoned = 1;
        return leave(s, -1);
    }
    s->lease = ++s->epoch;
    s->base = bank ? 0x190000u : 0x130000u;
    s->size = size;
    *token = s->lease;
    return leave(s, 0);
}
int cv1_storage_read(struct cv1_storage *s, uint64_t token, uint32_t o, uint8_t *dst, size_t n)
{
    if (!dst || !enter(s))
        return -1;
    if (!token || token != s->lease || !span(o, n, s->size) || !owned(s))
        return leave(s, -1);
    size_t done = 0;
    while (done < n) {
        size_t chunk = n - done > CV1_BOUNCE ? CV1_BOUNCE : n - done;
        if (!owned(s) || s->ops.io(s->ops.context, 0, s->base + o + (uint32_t) done, s->bounce, chunk) != (int) chunk ||
            !owned(s)) {
            s->poisoned = 1;
            s->lease = 0;
            memset(s->bounce, 0, sizeof(s->bounce));
            return leave(s, -1);
        }
        memcpy(dst + done, s->bounce, chunk);
        done += chunk;
    }
    memset(s->bounce, 0, sizeof(s->bounce));
    return leave(s, 0);
}
int cv1_storage_release(struct cv1_storage *s, uint64_t token)
{
    if (!enter(s))
        return -1;
    if (!token || token != s->lease || !owned(s))
        return leave(s, -1);
    s->lease = 0;
    s->size = 0;
    return leave(s, 0);
}
int cv1_storage_check(struct cv1_storage *s, uint64_t token)
{
    if (!enter(s))
        return -1;
    int ok = token && token == s->lease && owned(s);
    return leave(s, ok ? 0 : -1);
}
