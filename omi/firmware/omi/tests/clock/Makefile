CC ?= cc
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -Wno-unused-parameter -Wno-unused-variable -pthread
CPPFLAGS += -Istubs -I../../src
BUILD_DIR ?= build
HEADERS := $(shell find stubs -name '*.h')

$(BUILD_DIR)/test_recording_clock: test_recording_clock.c ../../src/rtc.c ../../src/rtc.h ../../src/sd_card.c ../../src/lib/core/storage.c $(HEADERS)
	mkdir -p $(BUILD_DIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) test_recording_clock.c -o $@

run: $(BUILD_DIR)/test_recording_clock
	$(BUILD_DIR)/test_recording_clock

.PHONY: run
