#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "source_binding.h"
struct fake {
    struct cv1_storage *s;
    int ready, partial, calls, reenter, loss;
};
static int owned(void *p)
{
    return ((struct fake *) p)->ready;
}
static int io(void *p, unsigned op, uint32_t o, void *out, size_t n)
{
    struct fake *f = p;
    assert(!op && o >= 0x130000 && o + n <= 0x1f0000);
    ++f->calls;
    if (f->reenter) {
        uint8_t x;
        assert(cv1_storage_read(f->s, f->s->lease, 0, &x, 1) == -1);
    }
    memset(out, 0xa5, n);
    if (f->loss)
        f->ready = 0;
    return f->partial ? (int) n - 1 : (int) n;
}
int main(void)
{
    struct cv1_storage s;
    struct fake f = {.s = &s, .ready = 1};
    struct cv1_storage_ops ops = {&f, owned, io};
    uint64_t a, b;
    uint8_t out[600];
    assert(cv1_storage_init(&s, ops, 1) == 0);
    assert(cv1_storage_acquire(&s, 0, 600, &a) == 0);
    assert(cv1_storage_acquire(&s, 1, 600, &b) == -1);
    atomic_flag_test_and_set(&s.busy);
    assert(cv1_storage_read(&s, a, 0, out, 1) == -1);
    assert(cv1_storage_acquire(&s, 0, 10, &b) == -1);
    atomic_flag_clear(&s.busy);
    f.reenter = 1;
    assert(cv1_storage_read(&s, a, 0, out, 600) == 0);
    assert(f.calls == 3);
    f.reenter = 0;
    for (unsigned i = 0; i < 600; i++)
        assert(out[i] == 0xa5);
    assert(cv1_storage_read(&s, a + 1, 0, out, 1) == -1);
    assert(cv1_storage_read(&s, a, UINT32_MAX, out, 1) == -1);
    assert(cv1_storage_read(&s, a, 599, out, 2) == -1);
    assert(cv1_storage_release(&s, a) == 0);
    assert(cv1_storage_acquire(&s, 1, 600, &b) == 0 && b != a);
    assert(cv1_storage_read(&s, a, 0, out, 1) == -1);
    f.partial = 1;
    assert(cv1_storage_read(&s, b, 0, out, 10) == -1);
    f.partial = 0;
    assert(cv1_storage_acquire(&s, 0, 10, &a) == -1);
    assert(cv1_storage_init(&s, ops, 2) == 0);
    assert(cv1_storage_acquire(&s, 0, 10, &a) == 0 && a != b);
    assert(cv1_storage_read(&s, b, 0, out, 1) == -1);
    f.loss = 1;
    memset(out, 0, 10);
    assert(cv1_storage_read(&s, a, 0, out, 10) == -1);
    for (unsigned i = 0; i < 10; i++)
        assert(out[i] == 0); /* no unowned chunk exposed */
    f.loss = 0;
    f.ready = 1;
    assert(cv1_storage_acquire(&s, 0, 10, &a) == -1);
    assert(!cv1_storage_init(&s, ops, 3));
    f.ready = 0;
    assert(cv1_storage_acquire(&s, 0, 10, &a) == -1);
    f.ready = 1;
    assert(cv1_storage_acquire(&s, 0, 10, &a) == -1);
    assert(cv1_ns_ram_range(0x20012000, 1));
    assert(cv1_ns_ram_range(0x2006ffff, 1));
    assert(!cv1_ns_ram_range(0x30012000, 1));
    assert(!cv1_ns_ram_range(UINTPTR_MAX - 3, 8));
    assert(!cv1_ns_ram_range(0x20002000, 1));
    assert(!cv1_ns_ram_range(0x2006ffff, 2));
    assert(!cv1_ns_ram_range(0x20012000, SIZE_MAX));
    assert(!cv1_ns_ram_range(0x20012000, 0));
    assert(cv1_internal_range(1, 0, 8192, 1));
    assert(!cv1_internal_range(1, 8192, 4, 2));
    assert(cv1_internal_range(2, 0, 0x9c000, 1));
    assert(!cv1_internal_range(2, 0x9bfff, 4, 2));
    assert(!cv1_internal_range(0, 0, 4, 2));
    assert(!cv1_internal_range(2, 0, 3, 2));
    assert(cv1_nor_range(0, 0, 0x60000, 1));
    assert(cv1_nor_range(1, 0, 1, 2));
    assert(!cv1_nor_range(2, 0, 1, 0));
    assert(!cv1_nor_range(0, 0x60000, 1, 2));
    assert(!cv1_nor_range(0, 1, 4096, 1));
    assert(!cv1_nor_range(0, 0, SIZE_MAX, 0));
    assert(cv1_storage_init(&s, ops, 0) == -1);
    assert(cv1_storage_init(&s, ops, UINT64_MAX) == -1);
    assert(cv1_storage_init(&s, ops, 4) == 0);
    struct cv1_storage_binding binding = {&s, 1};
    struct cv1_source source = cv1_bound_source(&binding);
    assert(source.acquire(source.context, 600, &a) == 0);
    assert(source.check(source.context, a) == 0);
    assert(source.read(source.context, a, 0, out, 600) == 0);
    assert(source.release(source.context, a) == 0);
    assert(source.check(source.context, a) == -1);
    puts("PASS: fixed-range, alias/overflow, lease/reset, reentrancy, partial-I/O and ownership-loss contracts; HOST "
         "ONLY");
}
