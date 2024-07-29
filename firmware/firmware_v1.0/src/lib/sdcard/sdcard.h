#ifndef SDCARD_H
#define SDCARD_H

#define DATA_SIZE 2048

#include <zephyr/kernel.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/logging/log.h>
#include <zephyr/device.h>
#include <zephyr/fs/fs.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <ff.h>

typedef struct {
    uint8_t *data;
    uint32_t lenght;
    bool endBuffer;
    bool concat;
} WriteParams;

typedef struct {
    char *data;
    int ret;
} ReadParams;

typedef struct {
    char *files;
    int res;
} Result;

extern char current_full_path[2048];
extern char current_path[2048];

void uint8_buffer_to_char_data(const uint8_t *buffer, size_t length, char *data, size_t data_size);

int write_file(WriteParams params);

int write_info(const char *data);

int create_file(const char *file_path);

int set_path(const char *file_path);

Result lsdir(const char *path);

int mount_sd_card(void);

ReadParams read_file(const char *file_path);

#endif // SDCARD_H