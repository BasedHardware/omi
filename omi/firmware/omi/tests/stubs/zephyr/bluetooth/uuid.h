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
/* Brace-in-macro formatting differs between clang-format major versions
 * (CI runs 18, local toolchains commonly 19+); keep the stub macro in
 * its compact hand-written form.
 */
/* clang-format off */
#define BT_UUID_INIT_128(...) {{.type = 0}, {0}}
/* clang-format on */

#endif
