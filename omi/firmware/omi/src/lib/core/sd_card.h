#ifndef SD_CARD_H
#define SD_CARD_H

#include <stdbool.h>
#include <stdint.h>
#include <sys/types.h>
#include <zephyr/kernel.h>

#define MAX_STORAGE_BYTES 0x1E000000U
#define MAX_WRITE_SIZE 440U
#define RAW_AUDIO_TIMESTAMP_BYTES 4U
#define RAW_AUDIO_PACKET_BYTES (RAW_AUDIO_TIMESTAMP_BYTES + MAX_WRITE_SIZE)
#define MAX_FILENAME_LEN 64
#define MAX_AUDIO_FILES 100

typedef struct {
    uint64_t read_seq;
    uint64_t write_seq;
    uint64_t dropped_packets;
    uint32_t capacity_packets;
} sd_ring_info_t;

int app_sd_init(void);
int app_sd_off(void);
void sd_write_pause(bool pause);
bool is_sd_on(void);

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE

uint32_t write_to_file(uint8_t *data, uint32_t length);

int sd_ring_get_info(sd_ring_info_t *info);
int sd_ring_read(uint64_t start_seq, uint8_t *buf, uint32_t max_bytes, uint32_t *bytes_read, uint32_t *packets_read);
int sd_ring_advance(uint64_t new_read_seq);
int sd_ring_clear(void);

uint32_t get_file_size(void);
int get_current_filename(char *buf, size_t buf_size);
int clear_audio_directory(void);
int save_offset(const char *filename, uint32_t offset);
int get_offset(char *filename, uint32_t *offset);
int create_new_audio_file(void);
void sd_notify_ble_state(bool connected);
int get_audio_file_stats(uint32_t *file_count, uint64_t *total_size);
int get_audio_file_list(char filenames[][MAX_FILENAME_LEN], int max_files, int *count);
int get_audio_file_list_with_sizes(char filenames[][MAX_FILENAME_LEN], uint32_t *sizes, int max_files, int *count);
int delete_audio_file(const char *filename);
int sd_flush_current_file(void);
void sd_notify_time_synced(uint32_t utc_time);
int read_audio_data(const char *filename, uint8_t *buf, int amount, int offset);

#endif

#endif