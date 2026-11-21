#include "secure_bus.h"

#include <string.h>
static int overlap(uintptr_t a, size_t n, uintptr_t b, size_t m)
{
    if (!n || a > UINTPTR_MAX - n || b > UINTPTR_MAX - m)
        return 1;
    return a < b + m && b < a + n;
}
static int range(enum cv1_bus_service op, uint32_t off, size_t n)
{
    if (op == CV1_BUS_SD_SECTOR_ZERO)
        return off == 0 && n == 512;
    if (op != CV1_BUS_NOR_READ || !n || n > 512)
        return 0;
    return (off >= 0x130000u && off <= 0x190000u - n) || (off >= 0x190000u && off <= 0x1f0000u - n);
}
int cv1_bus_init(struct cv1_secure_bus *b, struct cv1_bus_ops ops, uint32_t epoch)
{
    if (!b || !epoch || !ops.owned || !ops.epoch || !ops.millis || !ops.whole_read || !ops.finish)
        return -1;
    /* Only before publication/after actual reset; never while previous call exists. */
    memset(b, 0, sizeof(*b));
    atomic_flag_clear(&b->busy);
    b->ops = ops;
    b->epoch = epoch;
    if (ops.epoch(ops.context) != epoch || ops.owned(ops.context) != 1) {
        b->poisoned = 1;
        return -1;
    }
    return 0;
}
int cv1_bus_read(struct cv1_secure_bus *b,
                 uint32_t epoch,
                 enum cv1_bus_service op,
                 uint32_t off,
                 uint8_t *dst,
                 size_t n)
{
    if (!b || !dst || !range(op, off, n) || overlap((uintptr_t) dst, n, (uintptr_t) b, sizeof(*b)))
        return -1;
    if (atomic_flag_test_and_set_explicit(&b->busy, memory_order_acquire))
        return -1;
    int rc = -1;
    if (b->poisoned || !epoch || epoch != b->epoch)
        goto done;
    if (b->ops.epoch(b->ops.context) != epoch || b->ops.owned(b->ops.context) != 1) {
        b->poisoned = 1;
        goto done;
    }
    uint64_t start = b->ops.millis(b->ops.context);
    int transferred = b->ops.whole_read(b->ops.context, op, off, b->bounce, n);
    /* Always ask whole-driver cleanup, including partial/timeout; failure stays
     * uncertain/poisoned. Never use a made-up config with spi_release(). */
    int finished = b->ops.finish(b->ops.context);
    uint64_t end = b->ops.millis(b->ops.context);
    if (transferred != (int) n || finished || end < start || end - start > 100 ||
        b->ops.epoch(b->ops.context) != epoch || b->ops.owned(b->ops.context) != 1) {
        b->poisoned = 1;
        goto done;
    }
    memcpy(dst, b->bounce, n);
    rc = 0;
done:
    memset(b->bounce, 0, sizeof(b->bounce));
    atomic_flag_clear_explicit(&b->busy, memory_order_release);
    return rc;
}
int cv1_bus_nor_io(void *context, unsigned op, uint32_t off, void *dst, size_t n)
{
    struct cv1_secure_bus *b = context;
    if (op || !b)
        return -1;
    return cv1_bus_read(b, b->epoch, CV1_BUS_NOR_READ, off, dst, n) == 0 ? (int) n : -1;
}
