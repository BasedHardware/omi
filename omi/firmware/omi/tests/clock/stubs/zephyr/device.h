#ifndef Z_STUB_DEVICE_H
#define Z_STUB_DEVICE_H

#include <stdbool.h>

struct device {
    const char *name;
};

#define DT_NODELABEL(name) z_stub_dev_##name
#define DEVICE_DT_GET(node_id) (&(node_id))
#define DT_NODE_EXISTS(node_id) 1

static inline bool device_is_ready(const struct device *dev)
{
    (void) dev;
    return true;
}

extern struct device z_stub_dev_sdhc0;
extern struct device z_stub_dev_gpio1;
extern struct device z_stub_dev_spi3;
extern struct device z_stub_dev_sdcard_en_pin;

#endif
