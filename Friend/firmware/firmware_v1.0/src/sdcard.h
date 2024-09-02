#pragma once
#include <zephyr/kernel.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/logging/log.h>
#include <zephyr/device.h>
#include <zephyr/fs/fs.h>
#include <ff.h>

static FATFS fat_fs;

typedef struct {
    char *data;
    uint16_t length;
} info_file_t;

int mount_sd_card(void);

int create_file(const char* file_path);

char* generate_new_audio_header(uint8_t num);
int initialize_audio_file(uint8_t num);
int write_to_file(uint8_t *data,uint32_t length);
int read_audio_data(uint8_t *buf, int amount,int offset);
int rebase_audio_file(uint8_t num);
uint32_t get_file_size(uint8_t num);

int make_and_rebase_audio_file(uint8_t num);

int move_read_pointer(uint8_t num);
int move_write_pointer(uint8_t num);

