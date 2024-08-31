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

typedef struct {
    char name;
    uint32_t size;
    struct fs_file_t *file;
} audio_info_t;


char* get_info_file_data_();
int close_audio_file();
int initialize_audio_file();
int write_audio_file_unsafe(uint8_t *buf, int amount);
int create_file();
int read_audio_data(uint8_t *buf, int amount,int offset);
int write_entry_info(uint8_t entry_num,uint32_t size);
int get_file_size();