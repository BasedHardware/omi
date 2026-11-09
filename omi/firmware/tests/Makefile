CC ?= cc
BUILD_DIR ?= $(if $(wildcard /Volumes/Ephemeral/scratch),/Volumes/Ephemeral/scratch,/tmp)/omi-safe-mode-host
CFLAGS = -pthread -std=c11 -O2 -Wall -Wextra -Werror
CPPFLAGS = -Istubs -I../omi/sim -DCONFIG_OMI_NATIVE_SIM=1 -DOMI_SAFE_MODE_HOST=1 \
 -DCONFIG_OMI_SAFE_MODE_BOOT_LIMIT=3 -DCONFIG_OMI_SAFE_MODE_GOOD_UPTIME_S=60 \
 -DCONFIG_OMI_WATCHDOG_TIMEOUT_MS=30000 -DCONFIG_BT_DIS_FW_REV_STR='"3.0.23"'
.PHONY: test
test:
	mkdir -p $(BUILD_DIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) test_safe_mode.c -o $(BUILD_DIR)/test_safe_mode
	$(BUILD_DIR)/test_safe_mode
	$(CC) $(CPPFLAGS) $(CFLAGS) test_watchdog.c -o $(BUILD_DIR)/test_watchdog
	$(BUILD_DIR)/test_watchdog
	$(CC) $(CFLAGS) test_battery_guard.c -o $(BUILD_DIR)/test_battery_guard
	$(BUILD_DIR)/test_battery_guard
	python3 ../omi/sim/test_power_model.py
	$(CC) $(CFLAGS) -iquote ../omi/src/lib/core ../omi/src/lib/core/audio_packet_logic.c ../omi/tests/host/audio_packet_logic_test.c -o $(BUILD_DIR)/test_audio_packet_logic
	$(BUILD_DIR)/test_audio_packet_logic
	$(CC) $(CPPFLAGS) $(CFLAGS) test_boot_telemetry.c ../omi/src/boot_telemetry_logic.c ../omi/src/diagnostics_packet.c -o $(BUILD_DIR)/test_boot_telemetry
	$(BUILD_DIR)/test_boot_telemetry
	$(CC) $(CFLAGS) -I../omi/src ../omi/tests/diagnostics_packet_test.c ../omi/src/diagnostics_packet.c -o $(BUILD_DIR)/test_diagnostics_packet
	$(BUILD_DIR)/test_diagnostics_packet
	python3 check_ota_slot_geometry.py
	python3 test_build_guard.py
	python3 test_rc_integration.py
	python3 -m unittest discover -s ../tools/cv1 -p test_startup_replay.py
	python3 ../tools/cv1/test_jig_gestures.py
