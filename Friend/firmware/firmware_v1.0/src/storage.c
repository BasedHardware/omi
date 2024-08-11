#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/fs/fs.h>
#include "storage.h"
#include "sdcard.h"
// #include "lib/opus-1.2.1/opus.h"
#include "config.h"
#include "utils.h"
#include <stdint.h>

LOG_MODULE_REGISTER(storage, CONFIG_LOG_DEFAULT_LEVEL);

#define CONFIG_MAX_FILE_SIZE (1024 * 1024)  // 1 MB
#define MAX_FILENAME_LEN 32
#define AUDIO_DIR "/SD:/audio"
#define MAX_PACKET_SIZE (CODEC_PACKAGE_SAMPLES * 2)
#define INFO_FILE "/SD:/info.txt"

static char current_filename[MAX_FILENAME_LEN];
static uint32_t file_counter = 0;
// static OpusEncoder *opus_encoder = NULL;

int storage_init(void)
{
	LOG_INF("Initializing storage...");
    int err = mount_sd_card();
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

    // int opus_err;
    // opus_encoder = opus_encoder_create(16000, 1, OPUS_APPLICATION_VOIP, &opus_err);
    // if (opus_err != OPUS_OK) {
    //     LOG_ERR("Failed to create Opus encoder: %d", opus_err);
    //     return -1;
    // }

    // Create initial info.txt file
    LOG_INF("Creating info file...");
    err = create_file(INFO_FILE);
    if (err) {
        LOG_ERR("Failed to create info.txt: %d", err);
        return err;
    }

    LOG_INF("Storage initialized successfully");
    return 0;
}

static int create_new_file(void)
{
    snprintf(current_filename, sizeof(current_filename), "%s/audio_%08u.opus", AUDIO_DIR, file_counter++);
    int err = create_file(current_filename);
    if (err) {
        LOG_ERR("Failed to create new file: %d", err);
        return err;
    }

    // Update info.txt with the new file name
    char info[64];
    snprintf(info, sizeof(info), "%s,status:NEW", current_filename);
    err = write_file(INFO_FILE, (const uint8_t *)info, strlen(info), false);  // Overwrite
    if (err) {
        LOG_ERR("Failed to update info.txt: %d", err);
        return err;
    }

    LOG_INF("Created new file: %s", current_filename);
    return 0;
}

int save_audio_to_storage(const uint8_t *data, size_t len)
{
    static size_t total_bytes = 0;
	// static uint8_t opus_packet[MAX_PACKET_SIZE];
    int err;

	LOG_INF("Creating audio file: %s", current_filename);
    if (total_bytes == 0) {
        err = create_new_file();
        if (err) {
            LOG_ERR("Failed to create new file: %d", err);
            return err;
        }
    }

    // // Encode the PCM data to Opus
    // opus_int32 encoded_size = opus_encode(opus_encoder, (const opus_int16 *)data,
    //                                       len / 2, opus_packet, sizeof(opus_packet));
    // if (encoded_size < 0) {
    //     LOG_ERR("Opus encoding failed: %d", encoded_size);
    //     return -1;
    // }

    // // Write the Opus packet size and data
    // uint16_t packet_size = (uint16_t)encoded_size;
    // err = write_file(current_filename, (uint8_t*)&packet_size, sizeof(packet_size), true);
    // if (err) {
    //     LOG_ERR("Failed to write packet size: %d", err);
    //     return err;
    // }

	LOG_INF("Writing audio file: %s", current_filename);
    // err = write_file(current_filename, opus_packet, encoded_size, true);
    err = write_file(current_filename, data, len, true);
    if (err) {
        LOG_ERR("Failed to write to file: %d", err);
        return err;
    }

	// total_bytes += encoded_size + sizeof(packet_size);
    total_bytes += len;
    if (total_bytes >= CONFIG_MAX_FILE_SIZE) {
        total_bytes = 0;
        // Update info.txt to mark the file as complete
        char info[64];
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
