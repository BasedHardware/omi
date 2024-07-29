#ifndef STORAGE_H
#define STORAGE_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include "lib/sdcard/sdcard.h"

int init_storage(void);

ReadParams verify_info(void);

void extract_after(const char *data, char *result);

int extract_number(const char *input, uint8_t *number);

int save_audio_in_storage(uint8_t *buffer, uint32_t length);

void process_file(const char *file, char *path, int *status);

void uint8_buffer_to_char_data(const uint8_t *buffer, size_t length, char *data, size_t data_size);

void generate_next_filename(const char *current_filename, char *new_filename, size_t new_filename_size);

#endif // STORAGE_H