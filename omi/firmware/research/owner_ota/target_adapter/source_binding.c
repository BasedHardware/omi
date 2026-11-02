#include "source_binding.h"
static int acquire(void *c, uint32_t size, uint64_t *token)
{
    struct cv1_storage_binding *b = c;
    return cv1_storage_acquire(b->storage, b->bank, size, token);
}
static int read_source(void *c, uint64_t t, uint32_t off, uint8_t *dst, size_t n)
{
    return cv1_storage_read(((struct cv1_storage_binding *) c)->storage, t, off, dst, n);
}
static int check(void *c, uint64_t t)
{
    return cv1_storage_check(((struct cv1_storage_binding *) c)->storage, t);
}
static int release(void *c, uint64_t t)
{
    return cv1_storage_release(((struct cv1_storage_binding *) c)->storage, t);
}
struct cv1_source cv1_bound_source(struct cv1_storage_binding *b)
{
    return (struct cv1_source) {b, acquire, read_source, check, release};
}
