#ifndef Z_STUB_UTIL_H
#define Z_STUB_UTIL_H

#include <stddef.h>
#include <stdint.h>

#ifndef MIN
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#endif
#ifndef MAX
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#endif
#ifndef ARRAY_SIZE
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#endif
#ifndef ARG_UNUSED
#define ARG_UNUSED(x) ((void) (x))
#endif
#ifndef BIT64
#define BIT64(n) (1ULL << (n))
#endif
#define BUILD_ASSERT(cond, msg) _Static_assert(cond, msg)

#endif
