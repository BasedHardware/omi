#ifndef SD_H
#define SD_H

#include <zephyr/kernel.h>

/**
 * @brief Initialize the SD card module interface.
 *
 * @return 0 on success, negative error code otherwise.
 */
int app_sd_init(void);

/**
 * @brief Put the SD card interface (controller) into a low-power (suspend) state.
 *        Note: This typically suspends the SPI controller managing the SD card slot.
 *
 * @return 0 on success, negative error code on failure to suspend.
 */
int app_sd_off(void);

/**
 * @brief Force reformat SD card to fix filesystem corruption.
 *
 * @return 0 on success, negative error code on failure.
 */
int force_sd_reformat(void);

// SD Card control functions
void sd_off(void);
void sd_on(void);
bool is_sd_on(void);

// Storage state (defined in sd_card.c)
extern bool storage_is_on;
extern uint32_t file_num_array[2];

// BLE storage service initialization
int storage_init(void);

// File I/O functions
int write_to_file(uint8_t *data, uint32_t length);
uint32_t get_file_size(uint8_t num);
int get_offset(void);
int read_logical_file(uint32_t offset, uint8_t *buffer, uint32_t length);
uint32_t get_logical_file_size(void);
void rebuild_file_map(void);

// File counter and timestamp management
uint32_t get_current_file_counter(void);
uint64_t get_base_timestamp(void);
void set_base_timestamp(uint64_t timestamp);

// Storage health monitoring
struct storage_health_info {
    uint32_t write_errors;
    uint32_t io_errors;
    uint32_t space_errors;
    uint32_t successful_writes;
    bool health_degraded;
    bool offline_recording_disabled;
    uint32_t consecutive_failures;
};

struct storage_health_info get_storage_health(void);
bool is_storage_healthy(void);
void reset_storage_health(void);

#endif // SD_H
