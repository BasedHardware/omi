#ifndef Z_STUB_BT_GATT_H
#define Z_STUB_BT_GATT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
#include <zephyr/bluetooth/uuid.h>

struct bt_conn;
struct bt_gatt_attr {
    int tag;
    const void *ref1;
    const void *ref2;
};

struct bt_gatt_service {
    struct bt_gatt_attr *attrs;
};

#define BT_GATT_CHRC_READ 0x02
#define BT_GATT_CHRC_WRITE 0x08
#define BT_GATT_CHRC_NOTIFY 0x10
#define BT_GATT_PERM_READ 0x01
#define BT_GATT_PERM_WRITE 0x02
#define BT_GATT_CCC_NOTIFY 0x0001

#define BT_GATT_PRIMARY_SERVICE(uuid) {.tag = 1}
#define BT_GATT_CHARACTERISTIC(uuid, props, perm, read_fn, write_fn, user_data)                                        \
    {.tag = 2, .ref1 = (const void *) (read_fn), .ref2 = (const void *) (write_fn)}
#define BT_GATT_CCC(cfg_changed, perm) {.tag = 3, .ref1 = (const void *) (cfg_changed)}
#define BT_GATT_SERVICE(attr_array) {.attrs = (attr_array)}

struct bt_gatt_notify_params {
    const struct bt_gatt_attr *attr;
    const void *data;
    uint16_t len;
    void (*func)(struct bt_conn *conn, void *user_data);
    void *user_data;
};

bool bt_gatt_is_subscribed(struct bt_conn *conn, const struct bt_gatt_attr *attr, uint16_t ccc_value);
int bt_gatt_notify(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *data, uint16_t len);
int bt_gatt_notify_cb(struct bt_conn *conn, struct bt_gatt_notify_params *params);
uint16_t bt_gatt_get_mtu(struct bt_conn *conn);
ssize_t bt_gatt_attr_read(struct bt_conn *conn,
                          const struct bt_gatt_attr *attr,
                          void *buf,
                          uint16_t buf_len,
                          uint16_t offset,
                          const void *value,
                          size_t value_len);

#endif
