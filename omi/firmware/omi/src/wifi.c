/*
 * Copyright (c) 2024 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

/** @file
 * @brief Wi-Fi Softap sample
 */

#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(wifi, CONFIG_LOG_DEFAULT_LEVEL);

#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/kernel/thread_stack.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/wifi_mgmt.h>
#include <zephyr/net/wifi_utils.h>
#include <zephyr/net/socket.h>
#include <zephyr/posix/sys/socket.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/net/dhcpv4_server.h>
#include "net_private.h"

#include <net/wifi_ready.h>
#include "wifi.h"
#include "storage.h"

#define WIFI_SAP_MGMT_EVENTS                                                                    \
	(NET_EVENT_WIFI_AP_ENABLE_RESULT | NET_EVENT_WIFI_AP_DISABLE_RESULT |                     \
	 NET_EVENT_WIFI_AP_STA_CONNECTED | NET_EVENT_WIFI_AP_STA_DISCONNECTED)

#define AP_MAX_STATIONS 5

static atomic_t wifi_scan_done;

static K_SEM_DEFINE(wifi_scan_done_sem, 0, 1);
static K_SEM_DEFINE(wifi_ap_disable_result_sem, 0, 1);
static bool wifi_ready_status;

static atomic_t wifi_ap_disable_seen;
static int wifi_ap_disable_status;

static struct net_mgmt_event_callback wifi_sap_mgmt_cb;
static struct net_mgmt_event_callback wifi_scan_mgmt_cb;

static K_MUTEX_DEFINE(wifi_ap_sta_list_lock);
struct wifi_ap_sta_node {
	bool valid;
	struct wifi_ap_sta_info sta_info;
};
static struct wifi_ap_sta_node sta_list[AP_MAX_STATIONS];

/* WiFi state management */
static wifi_state_t current_wifi_state = WIFI_STATE_OFF;
static char ap_ssid[WIFI_SSID_MAX_LEN + 1] = "Omi CV1";
static char ap_password[WIFI_MAX_PASSWORD_LEN + 1] = "12345678";

#define TCP_REMOTE_IP "192.168.1.2"
#define TCP_REMOTE_PORT 12345

static atomic_t tcp_connected_flag;
static K_MUTEX_DEFINE(tcp_sock_lock);
static int tcp_socket = -1;
static atomic_t stop_tcp_traffic = ATOMIC_INIT(1);
static bool is_hardware_available = false;

#define WIFI_CONNECTING_TIMEOUT_MS (60U * 1000U)
static uint32_t connecting_started_ms;
static bool connecting_timer_running;

static int stop_dhcp_server(void);

static inline void wifi_connecting_timer_reset(void)
{
	connecting_timer_running = false;
}

static inline void wifi_connecting_timer_start_once(void)
{
	if (!connecting_timer_running) {
		connecting_started_ms = k_uptime_get_32();
		connecting_timer_running = true;
	}
}

static inline bool wifi_connecting_timer_expired(uint32_t timeout_ms)
{
	if (!connecting_timer_running) {
		return false;
	}

	uint32_t elapsed_ms = (uint32_t)(k_uptime_get_32() - connecting_started_ms);
	return (elapsed_ms > timeout_ms);
}

static bool tcp_client_is_connected(void)
{
	if (!atomic_get(&tcp_connected_flag)) {
		return false;
	}

	k_mutex_lock(&tcp_sock_lock, K_FOREVER);
	int fd = tcp_socket;
	k_mutex_unlock(&tcp_sock_lock);

	if (fd < 0) {
		atomic_clear(&tcp_connected_flag);
		return false;
	}

    struct zsock_pollfd pfd = {
            .fd = fd,
            .events = ZSOCK_POLLIN | ZSOCK_POLLERR | ZSOCK_POLLHUP,
    };

    int pret = zsock_poll(&pfd, 1, 0);
    if (pret < 0) {
            return true;
    }

    if (pret > 0 && (pfd.revents & (ZSOCK_POLLERR | ZSOCK_POLLHUP | ZSOCK_POLLNVAL))) {
            return false;
    }


	return true;
}

static void tcp_client_stop(void)
{
	atomic_clear(&tcp_connected_flag);

	k_mutex_lock(&tcp_sock_lock, K_FOREVER);
	int fd = tcp_socket;
	tcp_socket = -1;
	k_mutex_unlock(&tcp_sock_lock);

	if (fd >= 0) {
		(void)shutdown(fd, ZSOCK_SHUT_RDWR);
		(void)close(fd);
	}
}

static void wifi_scan_event_handler(struct net_mgmt_event_callback *cb,
				    uint32_t mgmt_event, struct net_if *iface)
{
	ARG_UNUSED(cb);
	ARG_UNUSED(iface);

	if (mgmt_event == NET_EVENT_WIFI_SCAN_DONE) {
		atomic_set(&wifi_scan_done, 1);
		k_sem_give(&wifi_scan_done_sem);
	}
}

static bool wifi_probe_rpu(struct net_if *iface)
{
	struct wifi_scan_params params = { 0 };
	int ret;

	atomic_set(&wifi_scan_done, 0);
	k_sem_reset(&wifi_scan_done_sem);

	params.scan_type = WIFI_SCAN_TYPE_ACTIVE;
	params.bands = 0; /* 0 == no restriction */
	params.dwell_time_active = 20;
	params.dwell_time_passive = 60;
	params.max_bss_cnt = 1;

	ret = net_mgmt(NET_REQUEST_WIFI_SCAN, iface, &params, sizeof(params));
	if (ret != 0 && ret != -EALREADY) {
		LOG_WRN("Wi-Fi scan probe request failed: %d", ret);
		return false;
	}

	ret = k_sem_take(&wifi_scan_done_sem, K_SECONDS(5));
	if (ret != 0) {
		LOG_ERR("Wi-Fi scan probe timed out (RPU not responding?)");
		return false;
	}

	return true;
}

static bool wifi_check_hardware_ready()
{
	struct net_if *iface = net_if_get_wifi_sta();

	if (!iface) {
		LOG_ERR("No Wi-Fi interface found");
		return false;
	}

	int ret = net_if_up(iface);
	if (ret != 0 && ret != -EALREADY) {
		LOG_ERR("net_if_up failed: %d", ret);
		return false;
	}

	if (!wifi_probe_rpu(iface)) {
		LOG_ERR("Wi-Fi RPU probe failed");
		net_if_down(iface);
		return false;
	}
	net_if_down(iface);

	return true;
}

static int tcp_client_start(void)
{
	if (atomic_get(&tcp_connected_flag)) {
		return 0;
	}

	/* Always start from a clean state */
	tcp_client_stop();

	int fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
	if (fd < 0) {
		LOG_ERR("tcp: socket() failed: %d (%s)", errno, strerror(errno));
		return -errno;
	}

	int one = 1;
	(void)setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
	struct timeval tv = {
		.tv_sec = 0,
		.tv_usec = 0,
	};

	setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
	struct sockaddr_in addr = {0};
	addr.sin_family = AF_INET;
	addr.sin_port = htons(TCP_REMOTE_PORT);
	if (zsock_inet_pton(AF_INET, TCP_REMOTE_IP, &addr.sin_addr) != 1) {
		LOG_ERR("tcp: invalid remote IP: %s", TCP_REMOTE_IP);
		close(fd);
		return -EINVAL;
	}

	LOG_INF("tcp: connecting to %s:%d", TCP_REMOTE_IP, TCP_REMOTE_PORT);
	if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
		LOG_ERR("TCP connect failed: %d", errno);
		close(fd);
		return -errno;
	}

	k_mutex_lock(&tcp_sock_lock, K_FOREVER);
	tcp_socket = fd;
	k_mutex_unlock(&tcp_sock_lock);
	atomic_set(&tcp_connected_flag, 1);
	LOG_INF("tcp: connected");
	return 0;
}

void wifi_turn_off(void)
{
	if (current_wifi_state == WIFI_STATE_OFF) {
		LOG_INF("Wi-Fi already off");
		return;
	}
	/* Stop new TCP sends immediately */
	atomic_set(&stop_tcp_traffic, 1);
	current_wifi_state = WIFI_STATE_SHUTDOWN;

	// wait for wifi to turn off (max 10s)
	int timeout_count = 0;
	while (current_wifi_state != WIFI_STATE_OFF && timeout_count < 100) {
		k_msleep(100);
		timeout_count++;
	}

    // Ensure WiFi power is off
    struct net_if *iface = net_if_get_first_wifi();
    if (iface) {
        net_if_down(iface);
    }
}

int wifi_turn_on(void)
{
	if (current_wifi_state != WIFI_STATE_OFF) {
		return -EALREADY;
	} else {
		/* Bring interface up; driver will report readiness via wifi_ready callback */
		struct net_if *iface = net_if_get_first_wifi();
		if (iface) {
			net_if_up(iface);
		}
	}

	current_wifi_state = WIFI_STATE_ON;
	atomic_clear(&stop_tcp_traffic);

	return 0;
}

int setup_wifi_credentials(const char *ssid, const char *password)
{
	if (!ssid || !password) {
		return -EINVAL;
	}

	size_t len = strlen(ssid);
	if (len == 0 || len > WIFI_SSID_MAX_LEN) {
		return -EINVAL;
	}

	len = strlen(password);
	if (len < 8 || len > WIFI_MAX_PASSWORD_LEN) {
		return -EINVAL;
	}

	strncpy(ap_ssid, ssid, sizeof(ap_ssid) - 1);
	ap_ssid[sizeof(ap_ssid) - 1] = '\0';
	strncpy(ap_password, password, sizeof(ap_password) - 1);
	ap_password[sizeof(ap_password) - 1] = '\0';
	return 0;
}

int wifi_send_data(const uint8_t *data, size_t len)
{
	int ret;
	if (!data || len == 0) {
		return 0;
	}

	if (atomic_get(&stop_tcp_traffic)) {
		return -ECONNABORTED;
	}

	if (!atomic_get(&tcp_connected_flag)) {
		return -ENOTCONN;
	}

	k_mutex_lock(&tcp_sock_lock, K_FOREVER);
	int fd = tcp_socket;
	if (fd < 0) {
		k_mutex_unlock(&tcp_sock_lock);
		return -ENOTCONN;
	}
	k_mutex_unlock(&tcp_sock_lock);

	while (1) {
		if (is_wifi_transport_ready()) {
			ret = send(fd, data, len, ZSOCK_MSG_DONTWAIT);
			if (ret < 0) {
				int err = errno;
				if (err == EINPROGRESS || err == EAGAIN || err == ENOBUFS) {
					struct zsock_pollfd pfd = {
						.fd = fd,
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

				LOG_ERR("TCP send failed with error: %d", err);
				tcp_client_stop();
				atomic_set(&stop_tcp_traffic, 1);
				current_wifi_state = WIFI_STATE_CONNECTING;
				return -err;
			}
			return ret;
		} else {
			return -ENOTCONN;
		}
	}

	return -EAGAIN;
}

bool is_wifi_transport_ready(void)
{
	return atomic_get(&tcp_connected_flag);
}

bool is_wifi_on(void)
{
	/* Treat SHUTDOWN as off for data-path loops so they can exit quickly. */
	return (current_wifi_state != WIFI_STATE_OFF) &&
	       (current_wifi_state != WIFI_STATE_SHUTDOWN);
}

static void wifi_ap_stations_unlocked(void)
{
	size_t id = 1;

	LOG_INF("AP stations:");
	LOG_INF("============");

	for (int i = 0; i < AP_MAX_STATIONS; i++) {
		struct wifi_ap_sta_info *sta;
		uint8_t mac_string_buf[sizeof("xx:xx:xx:xx:xx:xx")];

		if (!sta_list[i].valid) {
			continue;
		}

		sta = &sta_list[i].sta_info;

		LOG_INF("Station %zu:", id++);
		LOG_INF("==========");
		LOG_INF("MAC: %s",
			net_sprint_ll_addr_buf(sta->mac,
					       WIFI_MAC_ADDR_LEN,
					       mac_string_buf,
					       sizeof(mac_string_buf)));
		LOG_INF("Link mode: %s", wifi_link_mode_txt(sta->link_mode));
		LOG_INF("TWT: %s", sta->twt_capable ? "Supported" : "Not supported");
	}

	if (id == 1) {
		LOG_INF("No stations connected");
	}
}

static void handle_wifi_ap_enable_result(struct net_mgmt_event_callback *cb)
{
	const struct wifi_status *status =
		(const struct wifi_status *)cb->info;

	if (status->status) {
		LOG_ERR("AP enable request failed (%d)", status->status);
	} else {
		LOG_INF("AP enable requested");
	}
}

static void handle_wifi_ap_disable_result(struct net_mgmt_event_callback *cb)
{
	const struct wifi_status *status =
		(const struct wifi_status *)cb->info;

	wifi_ap_disable_status = status->status;
	atomic_set(&wifi_ap_disable_seen, 1);

	if (status->status) {
		LOG_ERR("AP disable request failed (%d)", status->status);
	} else {
		LOG_INF("AP disable requested");
	}

	k_sem_give(&wifi_ap_disable_result_sem);
}

static void handle_wifi_ap_sta_connected(struct net_mgmt_event_callback *cb)
{
	const struct wifi_ap_sta_info *sta_info =
		(const struct wifi_ap_sta_info *)cb->info;
	uint8_t mac_string_buf[sizeof("xx:xx:xx:xx:xx:xx")];
	int i;

	LOG_INF("Station connected: %s",
		net_sprint_ll_addr_buf(sta_info->mac, WIFI_MAC_ADDR_LEN,
				       mac_string_buf, sizeof(mac_string_buf)));

	k_mutex_lock(&wifi_ap_sta_list_lock, K_FOREVER);
	for (i = 0; i < AP_MAX_STATIONS; i++) {
		if (!sta_list[i].valid) {
			sta_list[i].sta_info = *sta_info;
			sta_list[i].valid = true;
			break;
		}
	}

	if (i == AP_MAX_STATIONS) {
		LOG_ERR("No space to store station info: "
			"Increase AP_MAX_STATIONS");
	}

	wifi_ap_stations_unlocked();
	k_mutex_unlock(&wifi_ap_sta_list_lock);
}

static void handle_wifi_ap_sta_disconnected(struct net_mgmt_event_callback *cb)
{
	const struct wifi_ap_sta_info *sta_info =
		(const struct wifi_ap_sta_info *)cb->info;
	uint8_t mac_string_buf[sizeof("xx:xx:xx:xx:xx:xx")];
	int i;

	LOG_INF("Station disconnected: %s",
		net_sprint_ll_addr_buf(sta_info->mac, WIFI_MAC_ADDR_LEN,
				       mac_string_buf, sizeof(mac_string_buf)));

	k_mutex_lock(&wifi_ap_sta_list_lock, K_FOREVER);
	for (i = 0; i < AP_MAX_STATIONS; i++) {
		if (!sta_list[i].valid) {
			continue;
		}

		if (!memcmp(sta_list[i].sta_info.mac, sta_info->mac,
			    WIFI_MAC_ADDR_LEN)) {
			sta_list[i].valid = false;
			break;
		}
	}

	if (i == AP_MAX_STATIONS) {
		LOG_WRN("No matching MAC address found in the list");
	}

	wifi_ap_stations_unlocked();
	k_mutex_unlock(&wifi_ap_sta_list_lock);

	/* close TCP and go back to CONNECTING state */
	if (current_wifi_state == WIFI_STATE_CONNECT) {
		LOG_INF("No stations connected, closing TCP connection");
		tcp_client_stop();
		current_wifi_state = WIFI_STATE_CONNECTING;
	}
}

static void wifi_mgmt_event_handler(struct net_mgmt_event_callback *cb,
				    uint32_t mgmt_event, struct net_if *iface)
{
	switch (mgmt_event) {
	case NET_EVENT_WIFI_AP_ENABLE_RESULT:
		handle_wifi_ap_enable_result(cb);
		break;
	case NET_EVENT_WIFI_AP_DISABLE_RESULT:
		handle_wifi_ap_disable_result(cb);
		break;
	case NET_EVENT_WIFI_AP_STA_CONNECTED:
		handle_wifi_ap_sta_connected(cb);
		break;
	case NET_EVENT_WIFI_AP_STA_DISCONNECTED:
		handle_wifi_ap_sta_disconnected(cb);
		break;
	default:
		break;
	}
}

static int __wifi_args_to_params(struct wifi_connect_req_params *params)
{
	params->band = WIFI_FREQ_BAND_2_4_GHZ;
	params->channel = 1;
	params->ssid = ap_ssid;
	params->ssid_length = strlen(params->ssid);
	if (params->ssid_length > WIFI_SSID_MAX_LEN) {
		LOG_ERR("SSID length is too long, expected is %d characters long",
			WIFI_SSID_MAX_LEN);
		return -1;
	}

	params->security = WIFI_SECURITY_TYPE_PSK;
	params->psk = ap_password;
	params->psk_length = strlen(params->psk);

	return 0;
}

static void cmd_wifi_status(void)
{
	struct net_if *iface;
	struct wifi_iface_status status = { 0 };

	iface = net_if_get_first_wifi();
	if (!iface) {
		LOG_ERR("Failed to get Wi-FI interface");
		return;
	}

	if (net_mgmt(NET_REQUEST_WIFI_IFACE_STATUS, iface, &status,
				sizeof(struct wifi_iface_status))) {
		LOG_ERR("Status request failed");
		return;
	}

	LOG_INF("Status: successful");
	LOG_INF("==================");
	LOG_INF("State: %s", wifi_state_txt(status.state));

	if (status.state >= WIFI_STATE_ASSOCIATED) {
		uint8_t mac_string_buf[sizeof("xx:xx:xx:xx:xx:xx")];

		LOG_INF("Interface Mode: %s", wifi_mode_txt(status.iface_mode));
		LOG_INF("Link Mode: %s", wifi_link_mode_txt(status.link_mode));
		LOG_INF("SSID: %.32s", status.ssid);
		LOG_INF("BSSID: %s",
			net_sprint_ll_addr_buf(status.bssid,
					       WIFI_MAC_ADDR_LEN, mac_string_buf,
					       sizeof(mac_string_buf)));
		LOG_INF("Band: %s", wifi_band_txt(status.band));
		LOG_INF("Channel: %d", status.channel);
		LOG_INF("Security: %s", wifi_security_txt(status.security));
		LOG_INF("MFP: %s", wifi_mfp_txt(status.mfp));
		LOG_INF("Beacon Interval: %d", status.beacon_interval);
		LOG_INF("DTIM: %d", status.dtim_period);
		LOG_INF("TWT: %s",
			status.twt_capable ? "Supported" : "Not supported");
	}
}

static int wifi_softap_enable(void)
{
	struct net_if *iface;
	static struct wifi_connect_req_params cnx_params;
	int ret = -1;

	iface = net_if_get_first_wifi();
	if (!iface) {
		LOG_ERR("Failed to get Wi-Fi iface");
		goto out;
	}

	if (__wifi_args_to_params(&cnx_params)) {
		goto out;
	}

	if (!wifi_utils_validate_chan(cnx_params.band, cnx_params.channel)) {
		LOG_ERR("Invalid channel %d in %d band",
			cnx_params.channel, cnx_params.band);
		goto out;
	}

	ret = net_mgmt(NET_REQUEST_WIFI_AP_ENABLE, iface, &cnx_params,
		       sizeof(struct wifi_connect_req_params));
	if (ret) {
		LOG_ERR("AP mode enable failed: %s", strerror(-ret));
	} else {
		LOG_INF("AP mode enabled");
	}

out:
	return ret;
}

static int configure_dhcp_server(void)
{
	struct net_if *iface;
	struct in_addr pool_start;
	int ret = -1;

	iface = net_if_get_first_wifi();
	if (!iface) {
		LOG_ERR("Failed to get Wi-Fi interface");
		goto out;
	}

	if (net_addr_pton(AF_INET, "192.168.1.2", &pool_start.s_addr)) {
		LOG_ERR("Invalid address: %s", "192.168.1.2");
		goto out;
	}

	ret = net_dhcpv4_server_start(iface, &pool_start);
	if (ret == -EALREADY) {
		LOG_ERR("DHCPv4 server already running on interface");
	} else if (ret < 0) {
		LOG_ERR("DHCPv4 server failed to start and returned %d error", ret);
	} else {
		LOG_INF("DHCPv4 server started and pool address starts from %s",
			"192.168.1.2");
	}
out:
	return ret;

}

static void handle_wifi_shutdown(void)
{
	LOG_INF("Wi-Fi state: SHUTDOWN");
	atomic_set(&stop_tcp_traffic, 1);
	LOG_INF("TCP traffic stopped - no new sends allowed");

	/* Wait briefly until no thread holds the socket lock (best-effort). */
	for (int i = 0; i < 50; i++) {
		if (k_mutex_lock(&tcp_sock_lock, K_NO_WAIT) == 0) {
			k_mutex_unlock(&tcp_sock_lock);
			break;
		}
		k_msleep(20);
	}

	tcp_client_stop();
	LOG_INF("TCP socket closed");

	stop_dhcp_server();
	LOG_INF("DHCP server stopped");
	
	struct net_if *iface = net_if_get_first_wifi();
	if (!iface) {
		LOG_ERR("No WiFi interface - transition to OFF");
		current_wifi_state = WIFI_STATE_OFF;
		return;
	}
	
	/* Step: Disable AP and wait for the actual result callback. */
	atomic_clear(&wifi_ap_disable_seen);
	wifi_ap_disable_status = -1;
	k_sem_reset(&wifi_ap_disable_result_sem);

	LOG_INF("Requesting AP disable...");
	int ret = net_mgmt(NET_REQUEST_WIFI_AP_DISABLE, iface, NULL, 0);
	if (ret) {
		LOG_ERR("AP disable request call failed: %d", ret);
		k_sleep(K_SECONDS(2));
		return; /* stay in SHUTDOWN */
	}

	/* Wait for NET_EVENT_WIFI_AP_DISABLE_RESULT. If this times out, wpa_supp is stuck. */
	ret = k_sem_take(&wifi_ap_disable_result_sem, K_SECONDS(8));
	if (ret) {
		LOG_ERR("AP disable result timeout -> WPA supplicant likely stuck");
		k_sleep(K_SECONDS(2));
		return; /* stay in SHUTDOWN */
	}

	if (!atomic_get(&wifi_ap_disable_seen) || wifi_ap_disable_status != 0) {
		LOG_ERR("AP disable failed (status=%d)", wifi_ap_disable_status);
		k_sleep(K_SECONDS(2));
		return; /* stay in SHUTDOWN */
	}

	LOG_INF("AP disabled, bringing interface down...");
	net_if_down(iface);
	LOG_INF("Interface down complete");

	current_wifi_state = WIFI_STATE_OFF;
	LOG_INF("Wi-Fi shutdown complete");
}

#define CHECK_RET(func, ...) \
	do { \
		ret = func(__VA_ARGS__); \
		if (ret) { \
			LOG_ERR("Failed to configure %s", #func); \
			return -1; \
		} \
	} while (0)

int start_app(void)
{
	int ret;

	CHECK_RET(wifi_softap_enable);
	CHECK_RET(configure_dhcp_server);

	cmd_wifi_status();

	return 0;
}

static int stop_dhcp_server(void)
{
	int ret;

	struct net_if *iface = net_if_get_first_wifi();

	if (!iface) {
		LOG_ERR("Failed to get Wi-Fi interface");
		return -1;
	}

	ret = net_dhcpv4_server_stop(iface);
	if (ret) {
		LOG_ERR("Failed to stop DHCPv4 server, error: %d", ret);
	}

	LOG_INF("DHCPv4 server stopped");

	return ret;
}

void start_wifi_thread(void);
K_THREAD_DEFINE(start_wifi_thread_id, 4096,
		start_wifi_thread, NULL, NULL, NULL,
		6, 0, -1);

void start_wifi_thread(void)
{
	current_wifi_state = WIFI_STATE_OFF;

	// check if Wi-Fi hardware is broken/unavailable
	if (!wifi_check_hardware_ready()) {
		LOG_ERR("Wi-Fi hardware not ready");
		return;
	}
	is_hardware_available = true;
	LOG_INF("Wi-Fi hardware is ready");

	while (1) {
		switch (current_wifi_state) {
		case WIFI_STATE_OFF:
			k_msleep(100);
			break;

		case WIFI_STATE_SHUTDOWN:
			// Ensure mic is resumed
			if(!mic_is_running()) {
				LOG_INF("Microphone resumed when Wi-Fi shuts down");
				mic_resume();
			}
			wifi_connecting_timer_reset();
			handle_wifi_shutdown();
			break;

		case WIFI_STATE_ON:
            LOG_INF("Wi-Fi state: ON (starting AP)");
            if (!wifi_ready_status) {
                    LOG_WRN("Wi-Fi not ready yet, retrying...");
					k_sleep(K_SECONDS(1));
                    break;
            }
            if (start_app() == 0) {
                    current_wifi_state = WIFI_STATE_CONNECTING;
						wifi_connecting_timer_reset();
            } else {
                    k_sleep(K_SECONDS(1));
            }

			break;

		case WIFI_STATE_CONNECTING:
			LOG_INF("Wi-Fi state: CONNECTING (TCP)");
			wifi_connecting_timer_start_once();
			if (wifi_connecting_timer_expired(WIFI_CONNECTING_TIMEOUT_MS)) {
				LOG_WRN("TCP connecting > 60s -> shutting down Wi-Fi");
				storage_stop_transfer();
				current_wifi_state = WIFI_STATE_SHUTDOWN;
				break;
			}
			if (!wifi_ready_status) {
				current_wifi_state = WIFI_STATE_SHUTDOWN;
				break;
			}
			if (tcp_client_start() == 0) {
				current_wifi_state = WIFI_STATE_CONNECT;
				wifi_connecting_timer_reset();
			} else {
				k_msleep(1000);
			}
			break;

		case WIFI_STATE_CONNECT:
			wifi_connecting_timer_reset();
			/* Keep the connection; if it drops, retry connect. */
			if (!wifi_ready_status) {
				current_wifi_state = WIFI_STATE_SHUTDOWN;
				break;
			}
			if (!tcp_client_is_connected()) {
				LOG_WRN("tcp: disconnected");
				tcp_client_stop();
				current_wifi_state = WIFI_STATE_CONNECTING;
				break;
			}
			/* Check connection status periodically */
			k_sleep(K_MSEC(1000));
			break;

		default:
			/* Unknown state: reset state machine. */
			tcp_client_stop();
			current_wifi_state = WIFI_STATE_OFF;
			break;
		}
	}
}

void wifi_ready_cb(bool wifi_ready)
{
	LOG_DBG("Is Wi-Fi ready?: %s", wifi_ready ? "yes" : "no");
	wifi_ready_status = wifi_ready;
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

void net_mgmt_callback_init(void)
{
	atomic_set(&wifi_scan_done, 0);
	net_mgmt_init_event_callback(&wifi_sap_mgmt_cb,
				     wifi_mgmt_event_handler,
				     WIFI_SAP_MGMT_EVENTS);

	net_mgmt_add_event_callback(&wifi_sap_mgmt_cb);
	net_mgmt_init_event_callback(&wifi_scan_mgmt_cb,
				     wifi_scan_event_handler,
				     NET_EVENT_WIFI_SCAN_DONE);
	net_mgmt_add_event_callback(&wifi_scan_mgmt_cb);
}

int wifi_init(void)
{
	int ret = 0;
	net_mgmt_callback_init();

	ret = register_wifi_ready();
	if (ret) {
		return ret;
	}
	k_thread_start(start_wifi_thread_id);

	return ret;
}

bool wifi_is_hw_available(void)
{
	return is_hardware_available;
}