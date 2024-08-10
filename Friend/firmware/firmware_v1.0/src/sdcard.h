#ifndef SDCARD_H
#define SDCARD_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

#define MAX_PATH_SIZE 32 //1024
#define MAX_DATA_SIZE 2048*4 //2048

extern bool sd_card_mounted;
bool is_sd_card_inserted(void);
int mount_sd_card(void);
int create_file(const char *file_path);
int write_file(const char *file_path, const uint8_t *data, size_t length, bool append);
int read_file(const char *file_path, uint8_t *buffer, size_t buffer_size, size_t *bytes_read);
int delete_file(const char *file_path);

#endif // SDCARD_H
