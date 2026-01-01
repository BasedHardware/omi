#include <zephyr/logging/log.h>

#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

#include <zephyr/net/net_if.h>
#include <zephyr/net/wifi_mgmt.h>
#include <zephyr/net/net_event.h>
#include <zephyr/net/dhcpv4.h>
#include <zephyr/net/socket.h>

#include <net/wifi_mgmt_ext.h>
#include <net/wifi_ready.h>

#include "wifi.h"
#include "mic.h"

LOG_MODULE_REGISTER(wifi, CONFIG_LOG_DEFAULT_LEVEL);

#define WIFI_SHELL_MGMT_EVENTS (NET_EVENT_WIFI_CONNECT_RESULT |		\
				NET_EVENT_WIFI_DISCONNECT_RESULT |	\
				NET_EVENT_WIFI_DISCONNECT_COMPLETE)

#define STATUS_POLLING_MS   300

/*
 * Some AP/hotspot reconnects (especially after link drop + heavy traffic)
 * can take >10s, and in rare cases the CONNECT_RESULT event can be delayed.
 */
#define WIFI_CONNECT_WAIT_MS 30000
#define WIFI_DHCP_WAIT_MS    15000
#define WIFI_RETRY_BACKOFF_MS 5000

/* WiFi state management */
static wifi_state_t current_wifi_state = WIFI_STATE_OFF;

/* State transition logging */
static const char *wifi_state_str(wifi_state_t state)
{
	switch (state) {
		case WIFI_STATE_OFF: return "OFF";
		case WIFI_STATE_SHUTDOWN: return "SHUTDOWN";
		case WIFI_STATE_ON: return "ON";
		case WIFI_STATE_CONNECTING: return "CONNECTING";
		case WIFI_STATE_CONNECTED: return "CONNECTED";
		case WIFI_STATE_TCP_CONNECTED: return "TCP_CONNECTED";
		default: return "UNKNOWN";
	}
}

static int set_wifi_state(wifi_state_t new_state)
{
	LOG_INF("WiFi state transition: %s -> %s", 
		wifi_state_str(current_wifi_state), 
		wifi_state_str(new_state));
	current_wifi_state = new_state;
	return 0;
}

static wifi_state_t get_wifi_state(void)
{
	wifi_state_t state;
	state = current_wifi_state;
	return state;
}

/* WiFi and TCP connection settings - global variables that can be modified */
char wifi_ssid[WIFI_MAX_SSID_LEN + 1] = "";
char wifi_password[WIFI_MAX_PASSWORD_LEN + 1] = "";
char tcp_server_addr[WIFI_MAX_SERVER_ADDR_LEN + 1] = "";
uint16_t tcp_server_port = 0;

static struct net_mgmt_event_callback wifi_shell_mgmt_cb;
static struct net_mgmt_event_callback net_shell_mgmt_cb;

static atomic_t wifi_ready_status;

K_SEM_DEFINE(dhcp_bound_sem, 0, 1);
static atomic_t dhcp_bound;
static atomic_t dhcp_started;
static atomic_t dhcp_start_pending;

static int64_t tcp_next_setup_ms;
static int64_t tcp_trouble_until_ms;
static int64_t wifi_connect_backoff_until_ms;

/* TCP socket management */
static int tcp_socket = -1;
K_MUTEX_DEFINE(tcp_socket_mutex);

static struct sockaddr_in tcp_sock_addr;
static bool tcp_server_addr_valid;
static bool stop_tcp_traffic = true;

enum {
	WIFI_FLAG_CONNECTED = 0,
	WIFI_FLAG_CONNECT_RESULT,
	WIFI_FLAG_DISCONNECT_REQUESTED,
	WIFI_FLAG_NEED_RECOVER,
};

static atomic_t wifi_flags;
static int wifi_connect(void);
static inline bool wifi_is_connected(void)
{
	return atomic_test_bit(&wifi_flags, WIFI_FLAG_CONNECTED);
}

static inline bool wifi_has_connect_result(void)
{
	return atomic_test_bit(&wifi_flags, WIFI_FLAG_CONNECT_RESULT);
}

static inline void wifi_clear_connect_result(void)
{
	atomic_clear_bit(&wifi_flags, WIFI_FLAG_CONNECT_RESULT);
}

static inline void wifi_set_connected(bool connected)
{
	if (connected) {
		atomic_set_bit(&wifi_flags, WIFI_FLAG_CONNECTED);
	} else {
		atomic_clear_bit(&wifi_flags, WIFI_FLAG_CONNECTED);
	}
}

static inline void wifi_set_disconnect_requested(bool requested)
{
	if (requested) {
		atomic_set_bit(&wifi_flags, WIFI_FLAG_DISCONNECT_REQUESTED);
	} else {
		atomic_clear_bit(&wifi_flags, WIFI_FLAG_DISCONNECT_REQUESTED);
	}
}

static inline bool wifi_need_recover(void)
{
	return atomic_test_bit(&wifi_flags, WIFI_FLAG_NEED_RECOVER);
}

static inline void wifi_set_need_recover(bool need)
{
	if (need) {
		atomic_set_bit(&wifi_flags, WIFI_FLAG_NEED_RECOVER);
	} else {
		atomic_clear_bit(&wifi_flags, WIFI_FLAG_NEED_RECOVER);
	}
}

static void tcp_close_socket(void)
{
	k_mutex_lock(&tcp_socket_mutex, K_FOREVER);
	if (tcp_socket >= 0) {
        int ret = close(tcp_socket);
        if (ret != 0) {
            LOG_WRN("close(tcp_socket=%d) failed: %d", tcp_socket, errno);
        }
		tcp_socket = -1;
	}
	k_mutex_unlock(&tcp_socket_mutex);
}

static void tcp_update_server_addr_locked(void)
{
	memset(&tcp_sock_addr, 0, sizeof(tcp_sock_addr));
	tcp_sock_addr.sin_family = AF_INET;
	tcp_sock_addr.sin_port = htons(tcp_server_port);
	tcp_server_addr_valid = (tcp_server_port > 0) &&
		(zsock_inet_pton(AF_INET, tcp_server_addr, &tcp_sock_addr.sin_addr) == 1);
}

static bool tcp_is_configured(void)
{
	return (strlen(tcp_server_addr) > 0 && tcp_server_port > 0);
}

static bool wifi_is_configured(void)
{
	return (strlen(wifi_ssid) > 0);
}

static bool wifi_has_ipv4_addr(void)
{
	struct net_if *iface = net_if_get_wifi_sta();
	struct in_addr *addr = NULL;

	if (iface) {
		addr = net_if_ipv4_get_global_addr(iface, NET_ADDR_PREFERRED);
	}

	return (addr != NULL);
}

static bool ipv4_ready(struct net_if *iface)
{
	struct net_if_ipv4 *ipv4 = iface->config.ip.ipv4;

	if (!ipv4) {
		return false;
	}

	return true;
}

static int wifi_wait_for_dhcp(int32_t timeout_ms)
{
	int64_t start_ms = k_uptime_get();
	struct net_if *iface = net_if_get_wifi_sta();

	if (atomic_get(&dhcp_bound)) {
		return 0;
	}

	/* Make sure we don't consume a stale give from previous connections */
	k_sem_reset(&dhcp_bound_sem);
	if (atomic_get(&dhcp_bound)) {
		return 0;
	}

	while (!atomic_get(&dhcp_bound) && !ipv4_ready(iface)) {
		/* Drain semaphore if it was given */
		(void)k_sem_take(&dhcp_bound_sem, K_NO_WAIT);

		if (timeout_ms >= 0) {
			int64_t now_ms = k_uptime_get();
			int64_t elapsed_ms = now_ms - start_ms;
			if (elapsed_ms < 0 || elapsed_ms >= timeout_ms) {
				return -ETIMEDOUT;
			}
		}
	}

	return 0;
}

static void handle_wifi_connect_result(struct net_mgmt_event_callback *cb, struct net_if *iface)
{
	if (wifi_is_connected()) {
		return;
	}

	bool connected = false;

#if defined(CONFIG_NET_MGMT_EVENT_INFO)
	const struct wifi_status *status = (const struct wifi_status *)cb->info;
	if (status) {
		if (status->status == 0) {
			connected = true;
		} else {
			LOG_ERR("Connection failed with status code: %d", status->status);
			switch (status->status) {
			case 1:
				LOG_ERR("Authentication timeout or wrong password");
				break;
			case 2:
				LOG_ERR("Association rejected");
				break;
			case 3:
				LOG_ERR("Association timeout");
				break;
			case 4:
				LOG_ERR("Authentication failed");
				break;
			default:
				LOG_ERR("Unknown connection failure");
				break;
			}
		}
	}
#endif

	/* Fallback if event info is not available */
	if (!connected) {
		struct wifi_iface_status if_status = { 0 };
		if (iface == NULL) {
			iface = net_if_get_wifi_sta();
		}
		int ret = net_mgmt(NET_REQUEST_WIFI_IFACE_STATUS, iface, &if_status, sizeof(if_status));
		if (ret == 0 && if_status.state >= WIFI_STATE_ASSOCIATED) {
			connected = true;
		} else {
			LOG_ERR("Connection failed (state=%s, ret=%d)", wifi_state_txt(if_status.state), ret);
		}
	}

	if (connected) {
		LOG_INF("Connected");
		wifi_set_connected(true);
		set_wifi_state(WIFI_STATE_CONNECTED);
		wifi_set_need_recover(false);

		/* Start DHCP from the Wi-Fi worker thread */
		atomic_set(&dhcp_bound, 0);
		k_sem_reset(&dhcp_bound_sem);
		atomic_set(&dhcp_started, 0);
		atomic_set(&dhcp_start_pending, 1);
	} else {
		set_wifi_state(WIFI_STATE_ON);
	}

	atomic_set_bit(&wifi_flags, WIFI_FLAG_CONNECT_RESULT);
}

static void handle_wifi_disconnect_result(struct net_mgmt_event_callback *cb, struct net_if *iface)
{
	if (!wifi_is_connected()) {
		return;
	}

	const struct wifi_status *status = (const struct wifi_status *)cb->info;
	if (status && status->status) {
		LOG_WRN("Disconnect status: %d", status->status);
	}

	atomic_set_bit(&wifi_flags, WIFI_FLAG_DISCONNECT_REQUESTED);
	LOG_WRN("WiFi disconnected, close TCP socket if any");
	set_wifi_state(WIFI_STATE_ON);
	k_msleep(100);
	tcp_close_socket();
}

static void wifi_mgmt_event_handler(struct net_mgmt_event_callback *cb,
				     uint32_t mgmt_event, struct net_if *iface)
{
	switch (mgmt_event) {
	case NET_EVENT_WIFI_CONNECT_RESULT:
		handle_wifi_connect_result(cb, iface);
		break;
	case NET_EVENT_WIFI_DISCONNECT_RESULT:
	case NET_EVENT_WIFI_DISCONNECT_COMPLETE:
		handle_wifi_disconnect_result(cb, iface);
		break;
	default:
		break;
	}
}

static int tcp_setup_socket(void)
{
	int sock;
	int ret;

	/* Close existing socket if any */
	tcp_close_socket();

	LOG_INF("Creating TCP socket...");

	sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
	if (sock < 0) {
		LOG_ERR("Failed to create TCP socket: %d", errno);
		return -errno;
	}

	LOG_INF("TCP socket created successfully");

	int one = 1;
	setsockopt(sock, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
	struct timeval tv = {
		.tv_sec = 0,
		.tv_usec = 0,
	};

	setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
	k_mutex_lock(&tcp_socket_mutex, K_FOREVER);
	tcp_update_server_addr_locked();
	if (!tcp_server_addr_valid) {
		k_mutex_unlock(&tcp_socket_mutex);
		LOG_ERR("Invalid server address: %s", tcp_server_addr);
		close(sock);
		return -EINVAL;
	}

	ret = connect(sock, (struct sockaddr *)&tcp_sock_addr, sizeof(tcp_sock_addr));
	if (ret < 0) {
		k_mutex_unlock(&tcp_socket_mutex);
		LOG_ERR("TCP connect failed: %d", errno);
		close(sock);
		return -errno;
	}

	/* Store socket for later use */
	tcp_socket = sock;
	k_mutex_unlock(&tcp_socket_mutex);

	return 0;
}

static void handle_dhcp_bound(struct net_if *iface)
{
	char ip[NET_IPV4_ADDR_LEN];
	struct in_addr *addr = NULL;

	if (iface) {
		addr = net_if_ipv4_get_global_addr(iface, NET_ADDR_PREFERRED);
	}

	if (addr) {
		net_addr_ntop(AF_INET, addr, ip, sizeof(ip));
		LOG_INF("DHCP IPv4 address: %s", ip);
	} else {
		LOG_INF("DHCP bound (no addr yet)");
	}

	/* Signal DHCP is bound and we have IP */
	atomic_set(&dhcp_bound, 1);
	k_sem_give(&dhcp_bound_sem);
	LOG_INF("DHCP semaphore signaled, dhcp_bound=%ld", (long)atomic_get(&dhcp_bound));
}

static void net_mgmt_event_handler(struct net_mgmt_event_callback *cb,
				    uint32_t mgmt_event, struct net_if *iface)
{
	LOG_DBG("Net mgmt event received: 0x%08X", mgmt_event);
	
	switch (mgmt_event) {
	case NET_EVENT_IPV4_ADDR_ADD:
		LOG_INF("NET_EVENT_IPV4_ADDR_ADDED received!");
		handle_dhcp_bound(iface);
		break;
	case NET_EVENT_IPV4_DHCP_BOUND:
		LOG_INF("NET_EVENT_IPV4_DHCP_BOUND received!");
		handle_dhcp_bound(iface);
		break;
	case NET_EVENT_IF_DOWN:
		LOG_WRN("NET_EVENT_IF_DOWN: iface %p going down during DHCP!", iface);
		break;
	case NET_EVENT_IF_UP:
		LOG_INF("NET_EVENT_IF_UP: iface %p coming up", iface);
		break;
	default:
		LOG_INF("Unhandled net event: 0x%08X", mgmt_event);
		break;
	}
}

static int wifi_connect(void)
{
	struct net_if *iface = net_if_get_wifi_sta();
	struct wifi_connect_req_params params = {0};
	struct wifi_iface_status if_status = { 0 };

	if (!iface) {
		LOG_ERR("No Wi-Fi interface available");
		return -ENODEV;
	}

	LOG_INF("Preparing WiFi connection...");
	tcp_close_socket();
	net_dhcpv4_stop(iface);
	wifi_set_connected(false);
	wifi_clear_connect_result();
	atomic_set(&dhcp_bound, 0);
	k_sem_reset(&dhcp_bound_sem);

	LOG_INF("Resetting WiFi interface before connecting...");
	if (!net_if_is_up(iface)) {
		LOG_INF("WiFi iface is down, bringing up...");
		net_if_up(iface);
		/* Give driver time to fully initialize after interface up */
		k_msleep(1000);
		LOG_INF("Interface should be ready now");
	}

	LOG_INF("Starting WiFi connection...");
	/* Use global variables for SSID and password */
	if (strlen(wifi_ssid) == 0) {
		LOG_ERR("WiFi SSID not set!");
		return -EINVAL;
	}

	params.ssid = wifi_ssid;
	params.ssid_length = strlen(wifi_ssid);
	params.psk = wifi_password;
	params.psk_length = strlen(wifi_password);
	/* Allow driver to choose best band/channel (2.4 or 5 GHz) */
	params.band = WIFI_FREQ_BAND_UNKNOWN;
	params.channel = WIFI_CHANNEL_ANY;
	/*
	 * Phone hotspots are often WPA2/WPA3 mixed or WPA3-only. Use AUTO_PERSONAL
	 * so wpa_supplicant can negotiate WPA2-PSK vs WPA3-SAE.
	 */
	if (strlen(wifi_password) > 0) {
		params.security = WIFI_SECURITY_TYPE_WPA_AUTO_PERSONAL;
		params.sae_password = wifi_password;
		params.sae_password_length = strlen(wifi_password);
	} else {
		params.security = WIFI_SECURITY_TYPE_NONE;
		params.sae_password = NULL;
		params.sae_password_length = 0;
	}
	params.mfp = WIFI_MFP_OPTIONAL;
	/* Bounded timeout so we always get a CONNECT_RESULT event */
	params.timeout = WIFI_CONNECT_WAIT_MS;

	LOG_INF("Connecting to SSID: %s (len=%d)", wifi_ssid, params.ssid_length);
	LOG_INF("Password len: %d", params.psk_length);
	LOG_INF("Security: %s, MFP: %d, Band: auto", 
		wifi_security_txt(params.security),
		params.mfp);

	LOG_INF("Calling net_mgmt(NET_REQUEST_WIFI_CONNECT)...");
	if (net_mgmt(NET_REQUEST_WIFI_CONNECT, iface, &params,
		     sizeof(struct wifi_connect_req_params))) {
		LOG_ERR("Connection request failed");
		return -ENOEXEC;
	}

	net_dhcpv4_start(iface);

	LOG_INF("Connection requested");

	return 0;
}

static void handle_wifi_shutdown(void)
{
	int ret = 0;
	wifi_state_t state = get_wifi_state();

	LOG_INF("Processing WIFI_SHUTDOWN");
	stop_tcp_traffic = true;
	if (state == WIFI_STATE_OFF) {
		LOG_WRN("WiFi already OFF");
		ret = -EALREADY;
	} else {
		/* Best-effort: close TCP and disconnect if connected */
		tcp_close_socket();
		atomic_set(&dhcp_bound, 0);
		k_sem_reset(&dhcp_bound_sem);
		struct net_if *iface = net_if_get_wifi_sta();
		(void)net_mgmt(NET_REQUEST_WIFI_DISCONNECT, iface, NULL, 0);

		if (iface) {
			LOG_INF("TURN_OFF: calling net_if_down");
			net_if_down(iface);
		}

		wifi_set_connected(false);
		wifi_clear_connect_result();
		atomic_set(&wifi_ready_status, 0);

		/* Power down the Wi-Fi chip if supported */
		set_wifi_state(WIFI_STATE_OFF);
		ret = 0;
	}
}

/* State-specific handlers */
static void handle_wifi_on(void)
{
	if (!wifi_is_configured()) {
		k_msleep(500);
		return;
	}

	if (wifi_connect_backoff_until_ms) {
		int64_t now_ms = k_uptime_get();
		if (now_ms < wifi_connect_backoff_until_ms) {
			k_msleep(100);
			return;
		}
		wifi_connect_backoff_until_ms = 0;
	}

	if (!atomic_get(&wifi_ready_status)) {
		/* Wi-Fi stack not ready yet */
		k_msleep(250);
		return;
	}

	/* Initiate connection */
	LOG_INF("Auto-connecting to: %s", wifi_ssid);

	if (wifi_need_recover()) {
		wifi_set_need_recover(false);
	}

	set_wifi_state(WIFI_STATE_CONNECTING);
	int ret = wifi_connect();;
	if (ret != 0) {
		LOG_WRN("wifi_connect() failed (%d), recovering...", ret);
		set_wifi_state(WIFI_STATE_ON);
	}
}

static void handle_wifi_connecting(void)
{
	static int64_t connect_start_ms = 0;
	static bool waiting = false;
	int ret;

	if (!waiting) {
		connect_start_ms = k_uptime_get();
		waiting = true;
		LOG_INF("Waiting for WiFi connect result (max %d ms)...", WIFI_CONNECT_WAIT_MS);
	}

	if (wifi_has_connect_result()) {
		LOG_INF("WiFi connected");
		set_wifi_state(WIFI_STATE_CONNECTED);
		waiting = false;
		return;
	}

	int64_t now_ms = k_uptime_get();
	if (now_ms - connect_start_ms >= WIFI_CONNECT_WAIT_MS) {
		LOG_WRN("WiFi connect wait timeout, recovering...");
		wifi_set_need_recover(true);
		if (get_wifi_state() != WIFI_STATE_OFF) {
			set_wifi_state(WIFI_STATE_ON);
			k_msleep(WIFI_RETRY_BACKOFF_MS);
		}
		waiting = false;
	}
}

static void handle_wifi_connected(void)
{
	if (!wifi_is_connected()) {
		/* Disconnected while in this state */
		LOG_WRN("WiFi disconnected, retrying...");
		set_wifi_state(WIFI_STATE_ON);
		tcp_close_socket();
		atomic_set(&dhcp_bound, 0);
		k_sem_reset(&dhcp_bound_sem);
		wifi_clear_connect_result();
		k_msleep(1000);
		return;
	}

	/* Setup TCP if configured and have IP */
	if (tcp_is_configured() && wifi_has_ipv4_addr()) {
		int64_t now_ms = k_uptime_get();
		if (tcp_next_setup_ms && now_ms < tcp_next_setup_ms) {
			/* backoff */
		} else {
			// wait for DHCP to be bound
			LOG_INF("Waiting for DHCP to assign IP...");
			if (!wifi_wait_for_dhcp(WIFI_DHCP_WAIT_MS)) {
				stop_tcp_traffic = false;
				tcp_next_setup_ms = 0;
				int ret = tcp_setup_socket();
				if (ret == 0) {
					set_wifi_state(WIFI_STATE_TCP_CONNECTED);
					LOG_INF("TCP socket ready");
				} else {
					LOG_ERR("TCP socket setup failed: %d, retrying...", ret);
					tcp_next_setup_ms = now_ms + 1000;
				}
			} else {
				LOG_WRN("Can't get IPv4 - retrying ...");
				set_wifi_state(WIFI_STATE_ON);
			}
		}
	}

	k_msleep(500);
}

static void handle_wifi_tcp_connected(void)
{
	if (!wifi_is_connected()) {
		/* Disconnected while in this state */
		LOG_WRN("WiFi disconnected, retrying...");
		set_wifi_state(WIFI_STATE_ON);
		tcp_close_socket();
		k_msleep(100);
		atomic_set(&dhcp_bound, 0);
		k_sem_reset(&dhcp_bound_sem);
		wifi_clear_connect_result();
		k_msleep(1000);
		return;
	}

	k_msleep(500);
}
void start_wifi_thread(void);
K_THREAD_DEFINE(start_wifi_thread_id, 8192, start_wifi_thread, NULL, NULL,
		      NULL, 6, 0, -1);

void start_wifi_thread(void)
{
	LOG_INF("WiFi thread started, using DHCP for IP assignment");

	while (1) {
		/* Handle state-specific logic */
		wifi_state_t current_state = get_wifi_state();
		switch (current_state) {
		case WIFI_STATE_OFF:
			k_msleep(500);
			break;
		case WIFI_STATE_SHUTDOWN:
			handle_wifi_shutdown();
			break;
		case WIFI_STATE_ON:
			handle_wifi_on();
			break;
		case WIFI_STATE_CONNECTING:
			handle_wifi_connecting();
			break;
		case WIFI_STATE_CONNECTED:
			handle_wifi_connected();
			break;
		case WIFI_STATE_TCP_CONNECTED:
			handle_wifi_tcp_connected();
			break;
		default:
			LOG_ERR("Unknown WiFi state: %d", current_state);
			k_msleep(500);
			break;
		}
	}
}

void wifi_ready_cb(bool wifi_ready)
{
	LOG_DBG("Is Wi-Fi ready?: %s", wifi_ready ? "yes" : "no");
	atomic_set(&wifi_ready_status, wifi_ready ? 1 : 0);
}

static void net_mgmt_callback_init(void)
{
	atomic_set(&wifi_flags, 0);
	atomic_set(&wifi_ready_status, 0);
	atomic_set(&dhcp_bound, 0);
	k_sem_reset(&dhcp_bound_sem);
	tcp_server_addr_valid = false;

	net_mgmt_init_event_callback(&wifi_shell_mgmt_cb,
				     wifi_mgmt_event_handler,
				     WIFI_SHELL_MGMT_EVENTS);

	net_mgmt_add_event_callback(&wifi_shell_mgmt_cb);

	net_mgmt_init_event_callback(&net_shell_mgmt_cb,
				     net_mgmt_event_handler,
				     NET_EVENT_IPV4_DHCP_BOUND |
					 NET_EVENT_IPV4_ADDR_ADD |
				     NET_EVENT_IF_DOWN |
				     NET_EVENT_IF_UP);

	net_mgmt_add_event_callback(&net_shell_mgmt_cb);

	/* No blocking sleeps here: keep init fast and deterministic */
}

static int register_wifi_ready(void)
{
	int ret = 0;
	wifi_ready_callback_t cb;
	struct net_if *iface = net_if_get_first_wifi();

	if (!iface) {
		LOG_ERR("Failed to get Wi-Fi interface");
		return -1;
	}

	cb.wifi_ready_cb = wifi_ready_cb;

	LOG_DBG("Registering Wi-Fi ready callbacks");
	ret = register_wifi_ready_callback(cb, iface);
	if (ret) {
		LOG_ERR("Failed to register Wi-Fi ready callbacks %s", strerror(ret));
		return ret;
	}

	return ret;
}

/**
 * @brief Turn WiFi off
 */
void wifi_turn_off(void)
{
    wifi_state_t state = get_wifi_state();

    LOG_INF("Processing WIFI_TURN_OFF");
    if (state == WIFI_STATE_OFF) {
        LOG_WRN("WiFi already OFF");
    } else {
        set_wifi_state(WIFI_STATE_SHUTDOWN);
        // wait util the state changes to OFF
        while (get_wifi_state() != WIFI_STATE_OFF) {
            k_msleep(100);
        }
        // Ensure WiFi power is off
        struct net_if *iface = net_if_get_first_wifi();
        if (iface) {
            net_if_down(iface);
        }
    }
}

/**
 * @brief Turn WiFi on
 * @return 0 on success, negative error code on failure
 */
int wifi_turn_on(void)
{
    int ret = 0;
    wifi_state_t state = get_wifi_state();
    LOG_INF("Processing WIFI_TURN_ON");
    if (state != WIFI_STATE_OFF) {
        LOG_WRN("WiFi already ON (state: %s)", wifi_state_str(state));
        ret = -EALREADY;
    } else {

        atomic_set(&dhcp_bound, 0);
        k_sem_reset(&dhcp_bound_sem);
        wifi_set_connected(false);
        wifi_clear_connect_result();

		/* Bring interface up; driver will report readiness via wifi_ready callback */
		struct net_if *iface = net_if_get_first_wifi();
		if (iface) {
			net_if_up(iface);
		}
		/*
		 * Some builds do not emit wifi_ready callbacks on resume.
		 * Treat TURN_ON as "ready to attempt connect" and let connect failures
		 * drive retries.
		 */
		atomic_set(&wifi_ready_status, 1);
		set_wifi_state(WIFI_STATE_ON);
		ret = 0;
	}
	
	return ret;
}

/**
 * @brief Update WiFi credentials
 * @param ssid WiFi SSID (max 32 characters)
 * @param password WiFi password (max 64 characters)
 * @return 0 on success, negative error code on failure
 */
int setup_wifi_credentials(const char *ssid, const char *password)
{
	if (!ssid || strlen(ssid) == 0 || strlen(ssid) > 32) {
		LOG_ERR("Invalid SSID");
		return -EINVAL;
	}

	if (password && strlen(password) > 64) {
		LOG_ERR("Password too long");
		return -EINVAL;
	}

	LOG_INF("Processing WIFI_UPDATE_CREDENTIALS");
	// Can update credentials in any state
	strncpy(wifi_ssid, ssid, WIFI_MAX_SSID_LEN);
	wifi_ssid[WIFI_MAX_SSID_LEN] = '\0';
	strncpy(wifi_password, password, WIFI_MAX_PASSWORD_LEN);
	wifi_password[WIFI_MAX_PASSWORD_LEN] = '\0';
	LOG_INF("Credentials updated: SSID=%s, password_len=%d",
		wifi_ssid, (int)strlen(wifi_password));

	return 0;
}

/**
 * @brief Update TCP server connection parameters
 * @param server_addr TCP server IP address
 * @param server_port TCP server port
 * @return 0 on success, negative error code on failure
 */
int setup_tcp_server(const char *server_addr, uint16_t server_port)
{
	if (!server_addr || strlen(server_addr) == 0 || strlen(server_addr) > WIFI_MAX_SERVER_ADDR_LEN - 1) {
		LOG_ERR("Invalid server address");
		return -EINVAL;
	}

	if (server_port == 0) {
		LOG_ERR("Invalid server port");
		return -EINVAL;
	}

	strncpy(tcp_server_addr, server_addr, WIFI_MAX_SERVER_ADDR_LEN);
	tcp_server_addr[WIFI_MAX_SERVER_ADDR_LEN] = '\0';
	tcp_server_port = server_port;
	k_mutex_lock(&tcp_socket_mutex, K_FOREVER);
	tcp_update_server_addr_locked();
	k_mutex_unlock(&tcp_socket_mutex);

	return 0;
}

/**
 * @brief Send data over TCP connection (non-blocking, direct send)
 * @param data Pointer to data buffer
 * @param len Length of data to send
 * @return Number of bytes sent on success, negative error code on failure
 */
int wifi_send_data(const uint8_t *data, size_t len)
{
	int ret;
	wifi_state_t state = get_wifi_state();
	int sock;
	bool server_valid;
	static int64_t last_tcp_err_log_ms;

	if (stop_tcp_traffic) {
		return -ECONNABORTED;
	}

	if (!data || len == 0) {
		LOG_ERR("Invalid data parameters");
		return -EINVAL;
	}

	if (state != WIFI_STATE_TCP_CONNECTED) {
		LOG_ERR("Cannot send data: TCP not ready (state: %s)", wifi_state_str(state));
		return -ENOTCONN;
	}

	k_mutex_lock(&tcp_socket_mutex, K_FOREVER);
	sock = tcp_socket;
	server_valid = tcp_server_addr_valid;
	k_mutex_unlock(&tcp_socket_mutex);
	if (sock < 0 || !server_valid) {
		LOG_ERR("TCP socket not available");
		return -ENOTCONN;
	}

	/* TCP send - socket is already connected */
	int poll_retries = 0;
	while (1) {
		if (is_wifi_transport_ready()) {
			ret = send(sock, data, len, ZSOCK_MSG_DONTWAIT);
			if (ret < 0) {
				int err = errno;
				if (err == EINPROGRESS || err == EAGAIN || err == ENOBUFS) {
					struct zsock_pollfd pfd = {
						.fd = sock,
						.events = ZSOCK_POLLOUT
					};
					int poll_ret = zsock_poll(&pfd, 1, 100); // 100ms timeout
					if (poll_ret <= 0) {
						k_msleep(1);
						continue;
					}
					// Socket writable, retry send
					continue;
				}
				int64_t now_ms = k_uptime_get();
				if (now_ms - last_tcp_err_log_ms > 1000) {
					LOG_WRN("TCP send error %d", err);
					last_tcp_err_log_ms = now_ms;
				}
				LOG_ERR("TCP send failed with error: %d", err);
				struct net_if *iface = net_if_get_wifi_sta();
				if (!iface) {
					LOG_ERR("No Wi-Fi interface available");
					return -ENODEV;
				}
				tcp_close_socket();
				set_wifi_state(WIFI_STATE_ON);
				net_mgmt(NET_REQUEST_WIFI_DISCONNECT, iface, NULL, 0);
				stop_tcp_traffic = true;
				tcp_next_setup_ms = now_ms + 1000;
				return -err;
			}
			break;
		} else {
			return -ENOTCONN;
		}
	}

	return ret;
}

/**
 * @brief Initialize WiFi module
 * @return 0 on success, negative error code on failure
 */
int wifi_init(void)
{
	int ret = 0;

	set_wifi_state(WIFI_STATE_OFF);

	/* Register callbacks FIRST before anything else */
	net_mgmt_callback_init();
	LOG_INF("Network management callbacks registered");

	ret = register_wifi_ready();
	if (ret) {
		return ret;
	}

	/* Best-effort: start in a true OFF state (power + interface) */
	{
		struct net_if *iface = net_if_get_first_wifi();
		if (iface) {
			net_if_down(iface);
		}
	}
	
	k_thread_start(start_wifi_thread_id);
	return ret;
}

bool is_wifi_transport_ready(void)
{
	wifi_state_t state = get_wifi_state();
	return state == WIFI_STATE_TCP_CONNECTED ? true : false;
}

bool is_wifi_on(void)
{
	wifi_state_t state = get_wifi_state();
	return state >= WIFI_STATE_ON ? true : false;
}
