#include <stddef.h>
#include <stdint.h>

extern "C" void* rnnoise_alloc(size_t size)
{
    static uint8_t buf[12288];
    static size_t off = 0;

    size_t aligned = (off + 15u) & ~15u;
    if (aligned + size > sizeof(buf)) {
        return nullptr;
    }

    void* p = (void*)(buf + aligned);
    off = aligned + size;
    return p;
}

extern "C" void rnnoise_free(void* ptr)
{
    (void)ptr;
}

