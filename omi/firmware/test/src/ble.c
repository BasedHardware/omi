
#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/hci.h>
#include <bluetooth/services/nus.h>
#include <zephyr/logging/log.h>
#include <shell/shell_bt_nus.h>
#include <stdio.h>

LOG_MODULE_REGISTER(ble_shell);

#define BT_UUID_OMI_VAL \
	BT_UUID_128_ENCODE(0x19b10000, 0xe8f2, 0x537e, 0x4f6c, 0xd104768a1214)

#define DEVICE_NAME             CONFIG_BT_DEVICE_NAME
#define DEVICE_NAME_LEN	        (sizeof(DEVICE_NAME) - 1)


static struct bt_conn *current_conn;

static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA(BT_DATA_NAME_COMPLETE, DEVICE_NAME, DEVICE_NAME_LEN),
};

static const struct bt_data sd[] = {
	BT_DATA_BYTES(BT_DATA_UUID128_ALL, BT_UUID_OMI_VAL),
};

static void connected(struct bt_conn *conn, uint8_t err)
{
	if (err) {
		LOG_ERR("Connection failed, err 0x%02x %s", err, bt_hci_err_to_str(err));
		return;
	}

	LOG_INF("Connected");
	current_conn = bt_conn_ref(conn);
	shell_bt_nus_enable(conn);
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	LOG_INF("Disconnected, reason 0x%02x %s", reason, bt_hci_err_to_str(reason));

	shell_bt_nus_disable();
	if (current_conn) {
		bt_conn_unref(current_conn);
		current_conn = NULL;
	}
}

static char *log_addr(struct bt_conn *conn)
{
	static char addr[BT_ADDR_LE_STR_LEN];

	bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));

	return addr;
}

static void __attribute__((unused)) security_changed(struct bt_conn *conn,
						     bt_security_t level,
						     enum bt_security_err err)
{
	char *addr = log_addr(conn);

	if (!err) {
		LOG_INF("Security changed: %s level %u", addr, level);
	} else {
		LOG_INF("Security failed: %s level %u err %d %s", addr, level, err,
			bt_security_err_to_str(err));
	}
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
	.connected    = connected,
	.disconnected = disconnected,
	COND_CODE_1(CONFIG_BT_SMP,
		    (.security_changed = security_changed), ())
};

static void auth_passkey_display(struct bt_conn *conn, unsigned int passkey)
{
	LOG_INF("Passkey for %s: %06u", log_addr(conn), passkey);
}

static void auth_cancel(struct bt_conn *conn)
{
	LOG_INF("Pairing cancelled: %s", log_addr(conn));
}

static void pairing_complete(struct bt_conn *conn, bool bonded)
{
	LOG_INF("Pairing completed: %s, bonded: %d", log_addr(conn), bonded);
}

static void pairing_failed(struct bt_conn *conn, enum bt_security_err reason)
{
	LOG_INF("Pairing failed conn: %s, reason %d %s", log_addr(conn), reason,
		bt_security_err_to_str(reason));
}

static struct bt_conn_auth_cb conn_auth_callbacks = {
	.passkey_display = auth_passkey_display,
	.cancel = auth_cancel,
};

static struct bt_conn_auth_info_cb conn_auth_info_callbacks = {
	.pairing_complete = pairing_complete,
	.pairing_failed = pairing_failed
};

static int cmd_ble_on(void)
{
	int err;

	printk("Starting Bluetooth NUS shell transport example\n");

	if (IS_ENABLED(CONFIG_BT_SMP)) {
		err = bt_conn_auth_cb_register(&conn_auth_callbacks);
		if (err) {
			printk("Failed to register authorization callbacks.\n");
			return 0;
		}

		err = bt_conn_auth_info_cb_register(&conn_auth_info_callbacks);
		if (err) {
			printk("Failed to register authorization info callbacks.\n");
			return 0;
		}
	}

	err = bt_enable(NULL);
	if (err) {
		LOG_ERR("BLE enable failed (err: %d)", err);
		return 0;
	}

	err = shell_bt_nus_init();
	if (err) {
		LOG_ERR("Failed to initialize BT NUS shell (err: %d)", err);
		return 0;
	}

	err = bt_le_adv_start(BT_LE_ADV_CONN, ad, ARRAY_SIZE(ad), sd,
			      ARRAY_SIZE(sd));
	if (err) {
		LOG_ERR("Advertising failed to start (err %d)", err);
		return 0;
	}

	LOG_INF("Bluetooth ready. Advertising started.");

	return 0;
}

static int cmd_ble_off(void)
{
    int err;
    // unregister authorization callbacks
    if (IS_ENABLED(CONFIG_BT_SMP)) {
        bt_conn_auth_cb_register(NULL);
        bt_conn_auth_info_cb_unregister(&conn_auth_info_callbacks);
    }
	err = bt_disable();
	if (err < 0) {
		printk("Bluetooth disable failed (%d)", err);
		return err;
	}
    printk("Bluetooth disabled");
    return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_ble_cmds,
                               SHELL_CMD(on, NULL, "Turn on BLE", cmd_ble_on),
                               SHELL_CMD(off, NULL, "Turn off BLE", cmd_ble_off),
                               SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(ble, &sub_ble_cmds, "BLE control commands", NULL);