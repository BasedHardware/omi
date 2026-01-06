/*
 * Copyright (c) 2024 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

/** @file
 * @brief Wi-Fi Softap sample
 */

#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(softap, CONFIG_LOG_DEFAULT_LEVEL);

#include <zephyr/net/wifi_mgmt.h>
#include <zephyr/net/wifi_utils.h>
#include "net_private.h"
#if defined(CONFIG_SOFTAP_SAMPLE_DHCPV4_SERVER)
#include <zephyr/net/dhcpv4_server.h>
#endif

#include <net/wifi_ready.h>

#define WIFI_SAP_MGMT_EVENTS (NET_EVENT_WIFI_AP_ENABLE_RESULT)

static K_SEM_DEFINE(wifi_ready_state_changed_sem, 0, 1);
static bool wifi_ready_status;

static struct net_mgmt_event_callback wifi_sap_mgmt_cb;

static K_MUTEX_DEFINE(wifi_ap_sta_list_lock);
struct wifi_ap_sta_node {
	bool valid;
	struct wifi_ap_sta_info sta_info;
};
static struct wifi_ap_sta_node sta_list[CONFIG_SOFTAP_SAMPLE_MAX_STATIONS];
#if defined(CONFIG_SOFTAP_SAMPLE_DHCPV4_SERVER)
static bool dhcp_server_configured;
#endif

static void wifi_ap_stations_unlocked(void)
{
	size_t id = 1;

	LOG_INF("AP stations:");
	LOG_INF("============");

	for (int i = 0; i < CONFIG_SOFTAP_SAMPLE_MAX_STATIONS; i++) {
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
	for (i = 0; i < CONFIG_SOFTAP_SAMPLE_MAX_STATIONS; i++) {
		if (!sta_list[i].valid) {
			sta_list[i].sta_info = *sta_info;
			sta_list[i].valid = true;
			break;
		}
	}

	if (i == CONFIG_SOFTAP_SAMPLE_MAX_STATIONS) {
		LOG_ERR("No space to store station info: "
			"Increase CONFIG_SOFTAP_SAMPLE_MAX_STATIONS");
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
	for (i = 0; i < CONFIG_SOFTAP_SAMPLE_MAX_STATIONS; i++) {
		if (!sta_list[i].valid) {
			continue;
		}

		if (!memcmp(sta_list[i].sta_info.mac, sta_info->mac,
			    WIFI_MAC_ADDR_LEN)) {
			sta_list[i].valid = false;
			break;
		}
	}

	if (i == CONFIG_SOFTAP_SAMPLE_MAX_STATIONS) {
		LOG_WRN("No matching MAC address found in the list");
	}

	wifi_ap_stations_unlocked();
	k_mutex_unlock(&wifi_ap_sta_list_lock);
}

static void wifi_mgmt_event_handler(struct net_mgmt_event_callback *cb,
				    uint32_t mgmt_event, struct net_if *iface)
{
	switch (mgmt_event) {
	case NET_EVENT_WIFI_AP_ENABLE_RESULT:
		handle_wifi_ap_enable_result(cb);
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
#ifdef CONFIG_SOFTAP_SAMPLE_2_4GHz
	params->band = WIFI_FREQ_BAND_2_4_GHZ;
#elif CONFIG_SOFTAP_SAMPLE_5GHz
	params->band = WIFI_FREQ_BAND_5_GHZ;
#endif
	params->channel = CONFIG_SOFTAP_SAMPLE_CHANNEL;

	/* SSID */
	params->ssid = CONFIG_SOFTAP_SAMPLE_SSID;
	params->ssid_length = strlen(params->ssid);
	if (params->ssid_length > WIFI_SSID_MAX_LEN) {
		LOG_ERR("SSID length is too long, expected is %d characters long",
			WIFI_SSID_MAX_LEN);
		return -1;
	}

#if defined(CONFIG_SOFTAP_SAMPLE_KEY_MGMT_WPA2)
	params->security = 1;
#elif defined(CONFIG_SOFTAP_SAMPLE_KEY_MGMT_WPA2_256)
	params->security = 2;
#elif defined(CONFIG_SOFTAP_SAMPLE_KEY_MGMT_WPA3)
	params->security = 3;
#else
	params->security = 0;
#endif

#if !defined(CONFIG_SOFTAP_SAMPLE_KEY_MGMT_NONE)
	params->psk = CONFIG_SOFTAP_SAMPLE_PASSWORD;
	params->psk_length = strlen(params->psk);
#endif

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

static int wifi_set_reg_domain(void)
{
	struct net_if *iface;
	struct wifi_reg_domain regd = {0};
	int ret = -1;

	iface = net_if_get_first_wifi();
	if (!iface) {
		LOG_ERR("Failed to get Wi-Fi iface");
		return ret;
	}

	regd.oper = WIFI_MGMT_SET;
	strncpy(regd.country_code, CONFIG_SOFTAP_SAMPLE_REG_DOMAIN,
		(WIFI_COUNTRY_CODE_LEN + 1));

	ret = net_mgmt(NET_REQUEST_WIFI_REG_DOMAIN, iface,
		       &regd, sizeof(regd));
	if (ret) {
		LOG_ERR("Cannot %s Regulatory domain: %d", "SET", ret);
	} else {
		LOG_INF("Regulatory domain set to %s", CONFIG_SOFTAP_SAMPLE_REG_DOMAIN);
	}

	return ret;
}

static int configure_dhcp_server(void)
{
#if !defined(CONFIG_SOFTAP_SAMPLE_DHCPV4_SERVER)
	return 0;
#else
	struct net_if *iface;
	struct in_addr pool_start;
	int ret = -1;

	iface = net_if_get_first_wifi();
	if (!iface) {
		LOG_ERR("Failed to get Wi-Fi interface");
		goto out;
	}

	if (net_addr_pton(AF_INET, CONFIG_SOFTAP_SAMPLE_DHCPV4_POOL_START, &pool_start.s_addr)) {
		LOG_ERR("Invalid address: %s", CONFIG_SOFTAP_SAMPLE_DHCPV4_POOL_START);
		goto out;
	}

	ret = net_dhcpv4_server_start(iface, &pool_start);
	if (ret == -EALREADY) {
		dhcp_server_configured = true;
		LOG_ERR("DHCPv4 server already running on interface");
	} else if (ret < 0) {
		LOG_ERR("DHCPv4 server failed to start and returned %d error", ret);
	} else {
		dhcp_server_configured = true;
		LOG_INF("DHCPv4 server started and pool address starts from %s",
			CONFIG_SOFTAP_SAMPLE_DHCPV4_POOL_START);
	}
out:
	return ret;

#endif
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

	CHECK_RET(wifi_set_reg_domain);

	CHECK_RET(configure_dhcp_server);

	CHECK_RET(wifi_softap_enable);

	cmd_wifi_status();

	return 0;
}

#if defined(CONFIG_SOFTAP_SAMPLE_DHCPV4_SERVER)
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

	dhcp_server_configured = false;
	LOG_INF("DHCPv4 server stopped");

	return ret;
}
#endif

void start_wifi_thread(void);
K_THREAD_DEFINE(start_wifi_thread_id, CONFIG_SOFTAP_SAMPLE_START_WIFI_THREAD_STACK_SIZE,
		start_wifi_thread, NULL, NULL, NULL,
		6, 0, -1);

void start_wifi_thread(void)
{
	bool waiting_for_wifi = true;

	while (1) {
		int ret;

		if (waiting_for_wifi) {
			LOG_INF("Waiting for Wi-Fi to be ready");
		}

		ret = k_sem_take(&wifi_ready_state_changed_sem, K_FOREVER);
		if (ret) {
			LOG_ERR("Failed to take semaphore: %d", ret);
			return;
		}

		if (!wifi_ready_status) {
			LOG_INF("Wi-Fi is not ready");
			#if defined(CONFIG_SOFTAP_SAMPLE_DHCPV4_SERVER)
			if (dhcp_server_configured) {
				stop_dhcp_server();
			}
			#endif
			waiting_for_wifi = true;
			continue;
		}
		start_app();
		waiting_for_wifi = false;
	}
}

void wifi_ready_cb(bool wifi_ready)
{
	LOG_DBG("Is Wi-Fi ready?: %s", wifi_ready ? "yes" : "no");
	wifi_ready_status = wifi_ready;
	k_sem_give(&wifi_ready_state_changed_sem);
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
	net_mgmt_init_event_callback(&wifi_sap_mgmt_cb,
				     wifi_mgmt_event_handler,
				     WIFI_SAP_MGMT_EVENTS);

	net_mgmt_add_event_callback(&wifi_sap_mgmt_cb);
}

int wifi_init(void)
{
	int ret = 0;

	#if defined(CONFIG_SOFTAP_SAMPLE_DHCPV4_SERVER)
	dhcp_server_configured = false;
	#endif

	net_mgmt_callback_init();

	ret = register_wifi_ready();
	if (ret) {
		return ret;
	}
	k_thread_start(start_wifi_thread_id);

	return ret;
}
