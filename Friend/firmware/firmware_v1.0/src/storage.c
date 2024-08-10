#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/fs/fs.h>
#include "storage.h"
#include "sdcard.h"

LOG_MODULE_REGISTER(storage, CONFIG_LOG_DEFAULT_LEVEL);

#define CONFIG_MAX_FILE_SIZE 1024 * 1024
#define MAX_FILENAME_LEN 32
#define AUDIO_DIR "/SD:/audio"

static char current_filename[MAX_FILENAME_LEN];
static uint32_t file_counter = 0;

int storage_init(void)
{
    int err = mount_sd_card();
    if (err) {
        LOG_ERR("Failed to mount SD card: %d", err);
        return err;
    }

    err = fs_mkdir(AUDIO_DIR);
    if (err && err != -EEXIST) {
        LOG_ERR("Failed to create audio directory: %d", err);
        return err;
    }

    return 0;
}

static int create_new_file(void)
{
    snprintf(current_filename, sizeof(current_filename), "%s/audio_%08u.raw", AUDIO_DIR, file_counter++);
    return create_file(current_filename);
}

int save_audio_to_storage(const uint8_t *data, size_t len)
{
    static size_t total_bytes = 0;
    int err;

    if (total_bytes == 0) {
        err = create_new_file();
        if (err) {
            LOG_ERR("Failed to create new file: %d", err);
            return err;
        }
    }

    err = write_file(current_filename, data, len, true);
    if (err) {
        LOG_ERR("Failed to write to file: %d", err);
        return err;
    }

    total_bytes += len;
    if (total_bytes >= CONFIG_MAX_FILE_SIZE) {
        total_bytes = 0;
    }

    return 0;
}

int read_audio_from_storage(uint8_t *buffer, size_t buffer_size, size_t *bytes_read)
{
    return read_file(current_filename, buffer, buffer_size, bytes_read);
}

int delete_audio_file(const char *filename)
{
    char full_path[MAX_FILENAME_LEN + sizeof(AUDIO_DIR)];
    snprintf(full_path, sizeof(full_path), "%s/%s", AUDIO_DIR, filename);
    return delete_file(full_path);
}
