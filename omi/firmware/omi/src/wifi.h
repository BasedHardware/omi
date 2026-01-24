#ifndef _WIFI_H_
#define _WIFI_H_

#include <zephyr/kernel.h>
#include <stdbool.h>
#include <stdint.h>
#include <zephyr/kernel.h>

#define WIFI_MAX_SSID_LEN        32
#define WIFI_MAX_PASSWORD_LEN    64
#define WIFI_MIN_PASSWORD_LEN    8

/* WiFi state machine states */
typedef enum {
	WIFI_STATE_OFF,        /* WiFi module is off */
	WIFI_STATE_SHUTDOWN,   /* Try to shut down WiFi */
	WIFI_STATE_ON,         /* WiFi is on in AP mode */
	WIFI_STATE_CONNECTING, /* Trying to connect to TCP server */
	WIFI_STATE_CONNECT     /* Connected to TCP server */
} wifi_state_t;

/* API functions */
int wifi_init(void);
void wifi_turn_off(void);
int wifi_turn_on(void);
bool wifi_is_hw_available(void);
int setup_wifi_credentials(const char *ssid, const char *password);
int wifi_send_data(const uint8_t *data, size_t len);
bool is_wifi_transport_ready(void);
bool is_wifi_on(void);
bool wifi_is_hw_available(void);
#endif