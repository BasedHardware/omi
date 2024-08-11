#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include "lib/fatfs/include/ff.h"
#include "storage.h"
#include "sdcard.h"
#include "config.h"

LOG_MODULE_REGISTER(storage, CONFIG_LOG_DEFAULT_LEVEL);

#define AUDIO_DIR "/SD:/audio"
#define INFO_FILE "/SD:/info.txt"
#define MAX_FILENAME_LEN 64
#define MAX_INFO_LEN 128

static char current_filename[MAX_FILENAME_LEN];
static uint32_t file_counter = 0;

int storage_init(void)
{
    int err;

    LOG_INF("Initializing storage...");
    err = mount_sd_card();
    if (err) {
        LOG_ERR("Failed to mount SD card: %d", err);
        return err;
    }

    LOG_INF("Creating audio directory...");
    err = create_directory(AUDIO_DIR);
    if (err) {
        LOG_ERR("Failed to create audio directory: %d", err);
        return err;
    }

    LOG_INF("Creating info file...");
    err = create_file(INFO_FILE);
    if (err) {
        LOG_ERR("Failed to create info file: %d", err);
        return err;
    }

    LOG_INF("Storage initialized successfully");
    return 0;
}

static int create_new_file(void)
{
    int err;

    snprintf(current_filename, sizeof(current_filename), "%s/audio_%08u.raw", AUDIO_DIR, file_counter++);

    LOG_INF("Creating new file: %s", current_filename);
    err = create_file(current_filename);
    if (err) {
        LOG_ERR("Failed to create new file: %d", err);
        return err;
    }

    // Update info.txt with the new file name
    char info[MAX_INFO_LEN];
    snprintf(info, sizeof(info), "%s,status:NEW", current_filename);
    err = write_file(INFO_FILE, (const uint8_t *)info, strlen(info), false);  // Overwrite
    if (err) {
        LOG_ERR("Failed to update info.txt: %d", err);
        return err;
    }

    return 0;
}

int save_audio_to_storage(const uint8_t *data, size_t len)
{
    static size_t total_bytes = 0;
    int err;

    if (total_bytes == 0) {
        err = create_new_file();
        if (err) {
            return err;
        }
    }

    LOG_INF("Writing %zu bytes to file: %s", len, current_filename);
    err = write_file(current_filename, data, len, true);  // Append
    if (err) {
        LOG_ERR("Failed to write to file: %d", err);
        return err;
    }

    total_bytes += len;
    if (total_bytes >= 200000) {
        total_bytes = 0;
        // Update info.txt to mark the file as complete
        char info[MAX_INFO_LEN];
        snprintf(info, sizeof(info), "%s,status:COMPLETE", current_filename);
        err = write_file(INFO_FILE, (const uint8_t *)info, strlen(info), false);  // Overwrite
        if (err) {
            LOG_ERR("Failed to update info.txt for completed file: %d", err);
        }
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
