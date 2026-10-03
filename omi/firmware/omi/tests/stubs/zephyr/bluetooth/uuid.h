#ifndef Z_STUB_BT_UUID_H
#define Z_STUB_BT_UUID_H

#include <stdint.h>

struct bt_uuid {
    uint8_t type;
};

struct bt_uuid_128 {
    struct bt_uuid uuid;
    uint8_t val[16];
};

#define BT_UUID_128_ENCODE(...) 0
#define BT_UUID_INIT_128(...) {{.type = 0}, {0}}

#endif
