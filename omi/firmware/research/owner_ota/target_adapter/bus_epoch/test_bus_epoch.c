#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "boot_epoch.h"
#include "secure_bus.h"
struct fake {
    struct cv1_secure_bus *b;
    uint32_t epoch;
    uint64_t now;
    int partial, timeout, reset, reenter, clean, calls, finish;
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    int pause, entered, proceed;
};
static int own(void *p)
{
    (void) p;
    return 1;
} /* HOST fixture only */
static uint32_t epoch(void *p)
{
    return ((struct fake *) p)->epoch;
}
static uint64_t millis(void *p)
{
    return ((struct fake *) p)->now;
}
static int finish(void *p)
{
    struct fake *f = p;
    f->finish++;
    return f->clean ? -1 : 0;
}
static int io(void *p, enum cv1_bus_service op, uint32_t off, void *dst, size_t n)
{
    struct fake *f = p;
    f->calls++;
    if (f->pause) {
        assert(!pthread_mutex_lock(&f->mutex));
        f->entered = 1;
        pthread_cond_broadcast(&f->cond);
        while (!f->proceed) {
            struct timespec limit;
            clock_gettime(CLOCK_REALTIME, &limit);
            limit.tv_sec += 2;
            assert(!pthread_cond_timedwait(&f->cond, &f->mutex, &limit));
        }
        assert(!pthread_mutex_unlock(&f->mutex));
    }
    if (f->reenter) {
        uint8_t other[512];
        assert(cv1_bus_read(f->b, f->epoch, CV1_BUS_SD_SECTOR_ZERO, 0, other, 512) == -1);
    }
    assert(op == CV1_BUS_NOR_READ ? off >= 0x130000 && off + n <= 0x1f0000 : off == 0 && n == 512);
    memset(dst, 0x5a, n);
    if (f->timeout)
        f->now += 101;
    if (f->reset)
        f->epoch++;
    return f->partial ? (int) n - 1 : (int) n;
}
struct ledger {
    uint8_t bytes[8192];
    int cut;
};
static int rd(void *p, enum cv1_area a, uint32_t o, uint8_t *dst, size_t n)
{
    struct ledger *l = p;
    if (a != CV1_JOURNAL || n > 8192 || o > 8192 - n)
        return -1;
    memcpy(dst, l->bytes + o, n);
    return 0;
}
static int word(struct ledger *l, uint32_t o, const uint8_t *src)
{
    if (l->cut == 0)
        return -1;
    if (l->cut > 0)
        l->cut--;
    for (unsigned j = 0; j < 4; j++) {
        if (src) {
            if ((l->bytes[o + j] & src[j]) != src[j])
                return -1;
            l->bytes[o + j] &= src[j];
        } else
            l->bytes[o + j] = 255;
    }
    return 0;
}
static int erase(void *p, enum cv1_area a, uint32_t o, size_t n)
{
    struct ledger *l = p;
    if (a != CV1_JOURNAL || o % 4096 || n != 4096 || o > 4096)
        return -1;
    for (size_t i = 0; i < n; i += 4)
        if (word(l, o + i, NULL))
            return -1;
    return 0;
}
static int program(void *p, enum cv1_area a, uint32_t o, const uint8_t *src, size_t n)
{
    struct ledger *l = p;
    if (a != CV1_JOURNAL || o % 4 || n % 4 || n > 8192 || o > 8192 - n)
        return -1;
    for (size_t i = 0; i < n; i += 4)
        if (word(l, o + i, src + i))
            return -1;
    return 0;
}
struct worker {
    struct cv1_secure_bus *bus;
    uint8_t out[512];
    int rc;
};
static void *work(void *p)
{
    struct worker *w = p;
    w->rc = cv1_bus_read(w->bus, 2, CV1_BUS_NOR_READ, 0x130000, w->out, 256);
    return NULL;
}
int main(void)
{
    struct cv1_secure_bus b;
    struct fake f = {.b = &b, .epoch = 2};
    struct cv1_bus_ops ops = {&f, own, epoch, millis, io, finish};
    uint8_t dst[512];
    assert(!cv1_bus_init(&b, ops, 2));
    assert(!cv1_bus_read(&b, 2, CV1_BUS_NOR_READ, 0x130000, dst, 256));
    f.reenter = 1;
    assert(!cv1_bus_read(&b, 2, CV1_BUS_SD_SECTOR_ZERO, 0, dst, 512));
    f.reenter = 0;
    assert(!pthread_mutex_init(&f.mutex, NULL));
    assert(!pthread_cond_init(&f.cond, NULL));
    f.pause = 1;
    struct worker w = {.bus = &b};
    pthread_t thread;
    assert(!pthread_create(&thread, NULL, work, &w));
    assert(!pthread_mutex_lock(&f.mutex));
    while (!f.entered) {
        struct timespec limit;
        clock_gettime(CLOCK_REALTIME, &limit);
        limit.tv_sec += 2;
        assert(!pthread_cond_timedwait(&f.cond, &f.mutex, &limit));
    }
    assert(cv1_bus_read(&b, 2, CV1_BUS_SD_SECTOR_ZERO, 0, dst, 512) == -1);
    f.proceed = 1;
    pthread_cond_broadcast(&f.cond);
    assert(!pthread_mutex_unlock(&f.mutex));
    assert(!pthread_join(thread, NULL));
    assert(w.rc == 0);
    f.pause = 0;
    assert(!pthread_cond_destroy(&f.cond));
    assert(!pthread_mutex_destroy(&f.mutex));
    int calls = f.calls;
    assert(cv1_bus_read(&b, 2, CV1_BUS_NOR_READ, 0x18ffff, dst, 2) == -1);
    assert(cv1_bus_read(&b, 2, CV1_BUS_NOR_READ, 0x120000, dst, 1) == -1);
    assert(cv1_bus_read(&b, 2, CV1_BUS_SD_SECTOR_ZERO, 1, dst, 512) == -1);
    assert(cv1_bus_read(&b, 2, CV1_BUS_NOR_READ, 0x130000, b.bounce, 1) == -1);
    assert(cv1_bus_read(&b, 2, CV1_BUS_NOR_READ, 0x130000, (void *) (UINTPTR_MAX - 2), 8) == -1);
    assert(f.calls == calls);
    assert(cv1_bus_read(&b, 1, CV1_BUS_NOR_READ, 0x130000, dst, 1) == -1);
    atomic_flag_test_and_set(&b.busy);
    assert(cv1_bus_read(&b, 2, CV1_BUS_NOR_READ, 0x130000, dst, 1) == -1);
    atomic_flag_clear(&b.busy);
    for (int failure = 0; failure < 4; failure++) {
        f.epoch = 3;
        f.partial = f.timeout = f.reset = f.clean = 0;
        assert(!cv1_bus_init(&b, ops, 3));
        memset(dst, 0, 512);
        if (failure == 0)
            f.partial = 1;
        if (failure == 1)
            f.timeout = 1;
        if (failure == 2)
            f.reset = 1;
        if (failure == 3)
            f.clean = 1;
        int before = f.finish;
        assert(cv1_bus_read(&b, 3, CV1_BUS_NOR_READ, 0x130000, dst, 256) == -1);
        assert(f.finish == before + 1);
        for (unsigned i = 0; i < 512; i++)
            assert(dst[i] == 0);
        assert(b.poisoned);
        assert(cv1_bus_read(&b, 3, CV1_BUS_SD_SECTOR_ZERO, 0, dst, 512) == -1);
    }
    struct ledger l;
    memset(l.bytes, 255, 8192);
    l.cut = -1;
    struct cv1_flash flash = {&l, rd, erase, program, NULL};
    uint8_t entropy[32] = {0x51};
    uint32_t issued = 99;
    assert(cv1_boot_reserve_epoch(&flash, entropy, &issued) == -1 && issued == 0); /* no auto provision */
    struct cv1_record seed = {
        .sequence = 1, .phase = CV1_CONFIRMED, .size = 1024, .generation = CV1_EPOCH_ROLE, .hash = {1}};
    assert(!cv1_journal_store(&flash, &seed));
    assert(!cv1_boot_reserve_epoch(&flash, entropy, &issued) && issued == 3);
    uint8_t baseline[8192];
    memcpy(baseline, l.bytes, 8192);
    for (int cut = 0; cut <= 2176; cut++) {
        memcpy(l.bytes, baseline, 8192);
        l.cut = cut;
        uint32_t attempted = 0, next = 0;
        int rc = cv1_boot_reserve_epoch(&flash, entropy, &attempted);
        assert(rc ? attempted == 0 : attempted == 5);
        l.cut = -1;
        assert(!cv1_boot_reserve_epoch(&flash, entropy, &next));
        assert(next > 3 && (rc || next > attempted)); /* same entropy, simulated reboot */
    }
    for (unsigned slot = 0; slot < 2; slot++) {
        memcpy(l.bytes, baseline, 8192);
        l.cut = -1;
        l.bytes[slot * 4096] ^= 1;
        assert(!cv1_boot_reserve_epoch(&flash, entropy, &issued) && issued > 3);
    }
    memset(l.bytes, 0, 8192);
    assert(cv1_boot_reserve_epoch(&flash, entropy, &issued) == -1 && issued == 0);
    memset(entropy, 0, 32);
    assert(cv1_boot_reserve_epoch(&flash, entropy, &issued) == -1 && issued == 0);
    printf("PASS HOST: NOR/SD serialization, alias/range, reentry, partial/timeout/reset/cleanup faults; 2177 epoch "
           "journal power-cut prefixes. No physical/DMA proof.\n");
}
