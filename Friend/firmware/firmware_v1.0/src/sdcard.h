#pragma once
#include <zephyr/kernel.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/logging/log.h>
#include <zephyr/device.h>
#include <zephyr/fs/fs.h>
#include <ff.h>

#define SD_MOUNT_POINT "SD:"
#define MAX_PATH 256
static FATFS fat_fs;
typedef struct {
    uint8_t *data;
    size_t length_;
    const char path[MAX_PATH];
    bool end_buffer;
    bool concat;
} write_params_t;

typedef struct {
    char *data;
    int ret;
} read_params_t;

typedef struct {
    char *data;
    uint16_t length;
} info_file_t;

typedef struct {
    char *name;
    size_t size;
    int res;
} file_info_t;


char* get_info_file_data_();
