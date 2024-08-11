#ifndef STORAGE_H
#define STORAGE_H

#include <zephyr/kernel.h>
#include <stdint.h>
#include <stdbool.h>

int storage_init(void);
int save_audio_to_storage(const uint8_t *data, size_t len);
int read_audio_from_storage(uint8_t *buffer, size_t buffer_size, size_t *bytes_read);
int delete_audio_file(const char *filename);

#endif /* STORAGE_H */
