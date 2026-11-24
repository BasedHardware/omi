#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../omi/src/boot_identity.h"
struct state {
    int fail;
    int reads;
    int updates;
    int begins;
    int finishes;
};
static int readable(void *p)
{
    return ((struct state *) p)->fail == 1 ? -1 : 0;
}
static int begin(void *p)
{
    struct state *s = p;
    ++s->begins;
    return s->fail == 2 ? -1 : 0;
}
static int read_chunk(void *p, uint32_t off, uint8_t *out, size_t n)
{
    struct state *s = p;
    assert(off == (uint32_t) s->reads * 256);
    assert(n == 256);
    ++s->reads;
    memset(out, (int) (off / 256), n);
    return s->fail == 3 && s->reads == 128 ? -1 : 0;
}
static int update(void *p, const uint8_t *data, size_t n)
{
    struct state *s = p;
    assert(n == 256);
    for (size_t i = 0; i < n; ++i)
        assert(data[i] == (uint8_t) s->updates);
    ++s->updates;
    return s->fail == 4 && s->updates == 128 ? -1 : 0;
}
static int finish(void *p, uint8_t digest[32])
{
    struct state *s = p;
    ++s->finishes;
    memset(digest, 0xab, 32);
    return s->fail == 5 ? -1 : 0;
}
int main(void)
{
    const struct omi_boot_identity_ops ops = {readable, begin, read_chunk, update, finish};
    uint8_t out[44];
    for (int fail = 0; fail <= 5; ++fail) {
        struct state s = {.fail = fail};
        memset(out, 0xcd, sizeof out);
        omi_boot_identity_measure(out, &ops, &s);
        assert(out[0] == 1 && out[2] == 1 && out[3] == 0 && out[10] == 1);
        for (int i = 4; i < 12; ++i)
            if (i != 10)
                assert(out[i] == 0);
        assert(out[1] == (fail == 0 ? 1 : fail == 1 ? 2 : 3));
        for (int i = 12; i < 44; ++i)
            assert(out[i] == (fail ? 0 : 0xab));
        if (fail == 1)
            assert(s.reads == 0 && s.begins == 0);
        if (fail == 2)
            assert(s.reads == 0);
        if (fail == 0)
            assert(s.reads == 256 && s.updates == 256 && s.finishes == 1);
    }
    omi_boot_identity_measure(out, NULL, NULL);
    assert(out[1] == 3);
    for (int i = 12; i < 44; ++i)
        assert(out[i] == 0);
    puts("boot identity core: bounded range, status, callback failures, no partial digest PASS");
}
