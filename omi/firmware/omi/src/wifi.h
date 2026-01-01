#ifndef _WIFI_H_
#define _WIFI_H_

#include <zephyr/kernel.h>
#include <stdint.h>

#define WIFI_MAX_SSID_LEN        32
#define WIFI_MAX_PASSWORD_LEN    64
#define WIFI_MAX_SERVER_ADDR_LEN 64

/* WiFi state machine states */
typedef enum {
	WIFI_STATE_OFF,          /* WiFi is off */
	WIFI_STATE_SHUTDOWN,     /* WiFi is shutting down */
	WIFI_STATE_ON,           /* WiFi is on but not connected */
	WIFI_STATE_CONNECTING,   /* WiFi is connecting */
	WIFI_STATE_CONNECTED,    /* WiFi connected but no TCP */
	WIFI_STATE_TCP_CONNECTED /* WiFi and TCP connected */
} wifi_state_t;

/* API functions */
int wifi_init(void);
void wifi_turn_off(void);
int wifi_turn_on(void);
int setup_wifi_credentials(const char *ssid, const char *password);
int setup_tcp_server(const char *server_addr, uint16_t server_port);
int wifi_send_data(const uint8_t *data, size_t len);
bool is_wifi_transport_ready(void);
bool is_wifi_on(void);
#endif