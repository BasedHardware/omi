#ifndef SDCARD_H
#define SDCARD_H

#include "../storage/config.h"
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <ff.h>

#define MAX_OUTPUT_SIZE 1400
#define MAX_INPUT_SIZE 700
#define DELIMITER ','
#define MAX_DIGITS 4

extern bool mounted;

typedef struct {
    uint8_t *data;
    size_t lenght;
    const char path[MAX_PATH_SIZE];
    bool endBuffer;
    bool concat;
} WriteParams;

typedef struct {
    char *data;
    int ret;
} ReadParams;

typedef struct {
    char *name;
    size_t size;
    int res;
} FileInfo;


int mount_sd_card(void);

int write_info(const char *data);

int write_file(uint8_t *data, size_t lenght, bool concat, bool endBuffer);

int set_path(const char *file_path);

FileInfo file_info(const char *path);

int create_file(const char *file_path);

char* format_values(const char *input);

ReadParams read_file(const char *file_path);

char* revert_format(const char *formatted_input);

uint8_t* convert_to_uint8_array(const char* str, size_t* out_size);

ReadParams read_file_fragmment(const char *file_path, size_t buffer_size, size_t pointer);

int delete_file(const char *file_path);

char* uint8_array_to_string(const uint8_t *array, size_t size);

#endif // SDCARD_H