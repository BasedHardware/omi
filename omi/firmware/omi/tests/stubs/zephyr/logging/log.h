#ifndef Z_STUB_LOG_H
#define Z_STUB_LOG_H

#include <stdio.h>

#define LOG_MODULE_REGISTER(name, level)
#define LOG_INF(...)                                                                                                   \
    do {                                                                                                               \
    } while (0)
#define LOG_WRN(...)                                                                                                   \
    do {                                                                                                               \
    } while (0)
#define LOG_ERR(...) fprintf(stderr, "SDERR " __VA_ARGS__), fputc('\n', stderr)

#endif
