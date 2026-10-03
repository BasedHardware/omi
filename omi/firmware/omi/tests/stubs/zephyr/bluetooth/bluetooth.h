#ifndef Z_STUB_BT_BLUETOOTH_H
#define Z_STUB_BT_BLUETOOTH_H

#include <stdint.h>

struct bt_conn {
    int id;
    int refs;
    bool subscribed;
    uint16_t mtu;
};

#define BT_HCI_ERR_REMOTE_USER_TERM_CONN 0x16

struct bt_conn_info {
    struct {
        uint16_t interval;
        uint16_t latency;
        uint16_t timeout;
    } le;
};

struct bt_conn *bt_conn_ref(struct bt_conn *conn);
void bt_conn_unref(struct bt_conn *conn);
int bt_conn_get_info(struct bt_conn *conn, struct bt_conn_info *info);
int bt_conn_disconnect(struct bt_conn *conn, uint8_t reason);

#endif
