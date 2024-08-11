#ifndef STORAGE_H
#define STORAGE_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#define MAX_PATH_SIZE 256
#define MAX_DATA_SIZE 1024

typedef struct {
    int ret;
    char *data;
} ReadParams;

typedef struct {
    int ret;
    uint8_t name;
} ReadInfo;

int init_storage(void);
ReadInfo get_current_file(void);
ReadParams verify_info(void);
int if_file_exist(void);
int save_audio_in_storage(uint8_t *buffer, size_t length);
char *generate_next_filename(const char *input_filename);
void process_file(const char *file, char *path, int *status);
char *extract_after(const char *data);
int extract_number(const char *input, uint8_t *number);

// Declare these functions if they're defined elsewhere
int mount_sd_card(void);
int create_file(const char *filename);
int write_info(const char *info);
ReadParams read_file(const char *filename);
int write_file(uint8_t *buffer, size_t length, bool append, bool endBuffer);

// Declare this variable as extern if it's defined in another file
extern bool mounted;

#endif // STORAGE_H
