#pragma once
#include <stdarg.h>
#include <string.h>
static int err_logs, warn_logs, last_error_value;
static inline void host_log(const char *fmt, ...)
{
    if (strncmp(fmt, "Error at", 8) == 0) {
        va_list ap;
        va_start(ap, fmt);
        (void) va_arg(ap, const char *);
        (void) va_arg(ap, int);
        last_error_value = va_arg(ap, int);
        va_end(ap);
    }
}
#define LOG_MODULE_REGISTER(...)
#define LOG_ERR(...) (++err_logs, host_log(__VA_ARGS__))
#define LOG_WRN(...) (++warn_logs, host_log(__VA_ARGS__))
#define LOG_DBG(...) host_log(__VA_ARGS__)
