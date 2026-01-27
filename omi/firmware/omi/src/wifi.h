#ifndef _WIFI_H_
#define _WIFI_H_

#include <zephyr/kernel.h>
#include <stdbool.h>
#include <stdint.h>
#include <zephyr/kernel.h>

#define WIFI_MAX_SSID_LEN        32
#define WIFI_MAX_PASSWORD_LEN    64
#define WIFI_MIN_PASSWORD_LEN    8
#define WIFI_MAX_URL_LEN         256
#define WIFI_MAX_TOKEN_LEN       64

/* WiFi state machine states */
typedef enum {
	WIFI_STATE_OFF,            /* WiFi module is off */
	WIFI_STATE_SHUTDOWN,       /* Try to shut down WiFi */
	WIFI_STATE_ON,             /* WiFi is on in AP mode */
	WIFI_STATE_CONNECTING,     /* Trying to connect to TCP server */
	WIFI_STATE_CONNECT,        /* Connected to TCP server */
	WIFI_STATE_STA_INIT,       /* Station mode initializing */
	WIFI_STATE_STA_CONNECTING, /* Connecting to router in STA mode */
	WIFI_STATE_STA_CONNECTED,  /* Connected to router in STA mode */
	WIFI_STATE_UPLOADING,      /* HTTP upload in progress */
} wifi_state_t;

/* AP mode API functions */
int wifi_init(void);
void wifi_turn_off(void);
int wifi_turn_on(void);
bool wifi_is_hw_available(void);
int setup_wifi_credentials(const char *ssid, const char *password);
int wifi_send_data(const uint8_t *data, size_t len);
bool is_wifi_transport_ready(void);
bool is_wifi_on(void);

/* Direct sync (Station mode) API functions */
int wifi_direct_sync_set_config(const char *ssid, const char *password,
                                const char *backend_url, const char *auth_token);
int wifi_direct_sync_clear_config(void);
bool wifi_direct_sync_has_config(void);
int wifi_direct_sync_trigger(void);
void wifi_on_charging_changed(bool is_charging);

#endif