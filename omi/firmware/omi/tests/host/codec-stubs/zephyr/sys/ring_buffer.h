#pragma once
struct ring_buf {
    int unused;
};
static int ring_init_calls;
static inline int ring_buf_put(struct ring_buf *b, uint8_t *d, size_t n)
{
    (void) b;
    (void) d;
    return n;
}
static inline int ring_buf_get(struct ring_buf *b, uint8_t *d, size_t n)
{
    (void) b;
    (void) d;
    return n;
}
static inline int ring_buf_size_get(struct ring_buf *b)
{
    (void) b;
    return 0;
}
static inline void ring_buf_init(struct ring_buf *b, size_t n, uint8_t *d)
{
    (void) b;
    (void) n;
    (void) d;
    ++ring_init_calls;
}
