#include <ff.h>
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/fs/fs.h>
#include <zephyr/fs/fs_sys.h>
#include <zephyr/logging/log.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/sys/check.h>
#include <zephyr/sys/atomic.h>
#include <string.h>
#include "sdcard.h"
#include "sdcard_config.h"

LOG_MODULE_REGISTER(sdcard, CONFIG_LOG_DEFAULT_LEVEL);

static FATFS fat_fs;

static struct fs_mount_t mount_point = {
	.type = FS_FATFS,
	.fs_data = &fat_fs,
};

struct gpio_dt_spec sd_en_gpio_pin = { .port = DEVICE_DT_GET(DT_NODELABEL(gpio0)), .pin=19, .dt_flags = GPIO_INT_DISABLE };

uint8_t file_count = 0;

static char current_full_path[MAX_PATH_LENGTH];
static char read_buffer[MAX_PATH_LENGTH];
static char write_buffer[MAX_PATH_LENGTH];

uint32_t file_num_array[2];    

static const char *disk_mount_pt = SDCARD_MOUNT_POINT;

bool sd_enabled = false;

// Chunking variables
static char current_chunk_filename[CHUNK_FILENAME_MAX_LENGTH];
bool chunk_active = false;  // Made non-static for external access
static bool system_boot_complete = false;  // Prevent chunking during boot
bool chunking_enabled = true;  // GLOBAL FLAG: Set to true to enable chunking system
static atomic_t chunk_cycle_counter = ATOMIC_INIT(0);  // Thread-safe counter for 500ms cycles

// Persistent chunk counter for unique filenames across reboots
static uint32_t chunk_counter = 0;

// REAL FILE CACHE - Updated by main thread, read by BLE thread
#define MAX_CACHED_FILES 10
#define MAX_FILENAME_LENGTH 64
char recent_files_cache[MAX_CACHED_FILES][MAX_FILENAME_LENGTH];  // Made non-static for external access
int cached_file_count = 0;  // Made non-static for external access
static bool cache_needs_update = true;
static atomic_t cache_update_flag = ATOMIC_INIT(1);  // Thread-safe update flag

static atomic_t should_rotate_flag = ATOMIC_INIT(0);  // Thread-safe flag (0=false, 1=true)

// Forward declarations
int get_file_contents(struct fs_dir_t *zdp, struct fs_dirent *entry);



int mount_sd_card(void)
{
    //initialize the sd card enable pin (v2)
    if (gpio_is_ready_dt(&sd_en_gpio_pin)) 
    {
		LOG_INF("SD Enable Pin ready");
	}
    else 
    {
		LOG_ERR("Error setting up SD Enable Pin");
        return -1;
	}

	if (gpio_pin_configure_dt(&sd_en_gpio_pin, GPIO_OUTPUT_ACTIVE) < 0) 
    {
		LOG_ERR("Error setting up SD Pin");
        return -1;
	}
    sd_enabled = true;

    //initialize the sd card
    const char *disk_pdrv = "SD";  
	int err = disk_access_init(disk_pdrv); 
    LOG_INF("disk_access_init: %d", err);
    if (err) 
    {   //reattempt
        k_msleep(1000);
        err = disk_access_init(disk_pdrv); 
        if (err) 
        {
            LOG_ERR("disk_access_init failed");
            return -1;
        }
    }

    mount_point.mnt_point = "/SD:";
    int res = fs_mount(&mount_point);
    if (res == FR_OK) 
    {
        LOG_INF("SD card mounted successfully");
    } 
    else 
    {
        LOG_ERR("f_mount failed: %d", res);
        return -1;
    }
    
    res = fs_mkdir(SDCARD_AUDIO_PATH);

    if (res == FR_OK) 
    {
        LOG_INF("audio directory created successfully");
        initialize_audio_file(1);
    }
    else if (res == FR_EXIST || res == -17) 
    {
        LOG_INF("audio directory already exists");
    }
    else 
    {
        LOG_INF("audio directory creation failed: %d", res);
    }

    if (chunking_enabled) {
        // ======================================================================
        // NEW CHUNKING SYSTEM
        // ======================================================================
        // This is the new audio chunk recording system that creates time-based
        // chunks for better file management and power management. This should be the default mode.
        LOG_INF("Using chunking system");
        file_count = 1;  // Set to 1 for compatibility
        
        // Load the persistent chunk counter
        int ret = get_chunk_counter(&chunk_counter);
        if (ret < 0) {
            LOG_ERR("Failed to load chunk counter: %d", ret);
            chunk_counter = 0; // Use default value on error
        }
        LOG_INF("Loaded chunk counter: %d", chunk_counter);
    } else {
        // ======================================================================
        // LEGACY FILE SYSTEM (DEPRECATED)
        // ======================================================================
        // This is the old file system that uses numbered files (a01.txt, etc.)
        // It is maintained for backward compatibility but should be removed
        // in future versions once chunking is fully validated.
        // TODO: Remove this legacy system in a future release
        LOG_INF("Using legacy file system (DEPRECATED)");
        struct fs_dir_t audio_dir_entry;
        fs_dir_t_init(&audio_dir_entry);
        err = fs_opendir(&audio_dir_entry, SDCARD_AUDIO_PATH);
        if (err) 
        {
            LOG_ERR("error while opening directory: %d", err);
            return -1;
        }
        LOG_INF("result of opendir: %d",err);
        initialize_audio_file(1);
        struct fs_dirent file_count_entry;
        file_count = get_file_contents(&audio_dir_entry, &file_count_entry);
        file_count = 1;
        if (file_count < 0) 
        {
            LOG_ERR(" error getting file count");
            return -1;
        }

        fs_closedir(&audio_dir_entry);
        LOG_INF("new num files: %d",file_count);

        res = move_write_pointer(file_count); 
        if (res) 
        {
            LOG_ERR("erro while moving the write pointer");
            return -1;
        }

        move_read_pointer(file_count);
        if (res) 
        {
            LOG_ERR("error while moving the reader pointer\n");
            return -1;
        }
        LOG_INF("file count: %d",file_count);
    }
   
    struct fs_dirent info_file_entry; //check if the info file exists. if not, generate new info file
    const char *info_path = SDCARD_INFO_FILE;
    res = fs_stat(info_path,&info_file_entry); //for later
    if (res) 
    {
        res = create_file("info.txt");
        save_offset(0);
        LOG_INF("result of info.txt creation: %d", res);
    }
    
    LOG_INF("SD card mount completed");
	return 0;
}

uint32_t get_file_size(uint8_t num)
{
    // For chunk files, use the cached filename approach
    if (chunking_enabled && num <= cached_file_count && num > 0) {
        const char* filename = recent_files_cache[num - 1]; // Convert to 0-based index
        if (filename[0] != '\0') {
            printf("[DEBUG] get_file_size: Cached filename: '%s' (length: %d)\n", filename, (int)strlen(filename));
            snprintf(current_full_path, sizeof(current_full_path), "%saudio/%s", disk_mount_pt, filename);
            printf("[DEBUG] get_file_size: Checking chunk file: %s\n", current_full_path);
            
            struct fs_dirent entry;
            int res = fs_stat(current_full_path, &entry);
            if (res == 0) {
                printf("[DEBUG] get_file_size: Chunk file size: %d bytes\n", (int)entry.size);
                return (uint32_t)entry.size;
            } else {
                printf("[DEBUG] get_file_size: Failed to stat chunk file: %d\n", res);
            }
        }
    }
    
    // Legacy behavior for old audio files (a01.txt, etc.)
    char *ptr = generate_new_audio_header(num);
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, ptr);
    k_free(ptr);
    struct fs_dirent entry;
    int res = fs_stat(&current_full_path,&entry);
    if (res)
    {
        LOG_ERR("invalid file in get file size\n");
        return 0;  
    }
    return (uint32_t)entry.size;
}

int move_read_pointer(uint8_t num) 
{
    // For chunk files, use the cached filename approach
    if (chunking_enabled && num <= cached_file_count && num > 0) {
        const char* filename = recent_files_cache[num - 1]; // Convert to 0-based index
        if (filename[0] != '\0') {
            printf("[DEBUG] move_read_pointer: Cached filename: '%s' (length: %d)\n", filename, (int)strlen(filename));
            snprintf(read_buffer, sizeof(read_buffer), "%saudio/%s", disk_mount_pt, filename);
            printf("[DEBUG] move_read_pointer: Setting read buffer to chunk file: %s\n", read_buffer);
            
            struct fs_dirent entry;
            int res = fs_stat(read_buffer, &entry);
            if (res == 0) {
                printf("[DEBUG] move_read_pointer: Chunk file ready for reading\n");
                return 0;
            } else {
                printf("[DEBUG] move_read_pointer: Failed to stat chunk file: %d\n", res);
            }
        }
    }
    
    // Legacy behavior for old audio files (a01.txt, etc.)
    char *read_ptr = generate_new_audio_header(num);
    snprintf(read_buffer, sizeof(read_buffer), "%s%s", disk_mount_pt, read_ptr);
    k_free(read_ptr);
    struct fs_dirent entry; 
    int res = fs_stat(&read_buffer,&entry);
    if (res) 
    {
        LOG_ERR("invalid file in move read ptr\n");
        return -1;  
    }
    return 0;
}

int move_write_pointer(uint8_t num) 
{
    char *write_ptr = generate_new_audio_header(num);
    snprintf(write_buffer, sizeof(write_buffer), "%s%s", disk_mount_pt, write_ptr);
    k_free(write_ptr);
    struct fs_dirent entry;
    int res = fs_stat(&write_buffer,&entry);
    if (res) 
    {
        LOG_ERR("invalid file in move write pointer\n");  
        return -1;  
    }
    return 0;   
}

int create_file(const char *file_path)
{
    int ret = 0;
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, file_path);
	struct fs_file_t data_file;
	fs_file_t_init(&data_file);
	ret = fs_open(&data_file, current_full_path, FS_O_WRITE | FS_O_CREATE);
	if (ret) 
	{
        LOG_ERR("File creation failed %d", ret);
		return -2;
	} 
    fs_close(&data_file);
    return 0;
}

int read_audio_data(uint8_t *buf, int amount,int offset) 
{
    struct fs_file_t read_file;
   	fs_file_t_init(&read_file); 
    uint8_t *temp_ptr = buf;

    printf("[DEBUG] read_audio_data: Opening file: %s\n", read_buffer);
    printf("[DEBUG] read_audio_data: Request - offset: %d, amount: %d\n", offset, amount);

	int rc = fs_open(&read_file, read_buffer, FS_O_READ | FS_O_RDWR);
    if (rc < 0) {
        LOG_ERR("Failed to open file for reading: %d", rc);
        printf("[DEBUG] read_audio_data: Failed to open file: %d\n", rc);
        return rc;
    }
    
    // Get file size to check bounds
    struct fs_dirent entry;
    rc = fs_stat(read_buffer, &entry);
    if (rc < 0) {
        LOG_ERR("Failed to stat file: %d", rc);
        printf("[DEBUG] read_audio_data: Failed to stat file: %d\n", rc);
        fs_close(&read_file);
        return rc;
    }
    
    uint32_t file_size = (uint32_t)entry.size;
    printf("[DEBUG] read_audio_data: File size: %d bytes\n", file_size);
    
    // Check if offset is within file bounds
    if (offset >= file_size) {
        LOG_ERR("Offset %d is beyond file size %d", offset, file_size);
        printf("[DEBUG] read_audio_data: ❌ Offset %d >= file_size %d, STOPPING READ\n", offset, file_size);
        fs_close(&read_file);
        return 0; // Return 0 bytes read (EOF)
    }
    
    // Limit amount to what's actually available
    if (offset + amount > file_size) {
        amount = file_size - offset;
        printf("[DEBUG] read_audio_data: Limited read amount to %d bytes (remaining in file)\n", amount);
    }
    
    rc = fs_seek(&read_file, offset, FS_SEEK_SET);
    if (rc < 0) {
        LOG_ERR("Failed to seek to offset %d: %d", offset, rc);
        printf("[DEBUG] read_audio_data: ❌ SEEK FAILED offset=%d, error=%d\n", offset, rc);
        fs_close(&read_file);
        return rc;
    }
    
    printf("[DEBUG] read_audio_data: ✅ Seek successful, reading %d bytes\n", amount);
    rc = fs_read(&read_file, temp_ptr, amount);
    if (rc < 0) {
        LOG_ERR("Failed to read %d bytes: %d", amount, rc);
        printf("[DEBUG] read_audio_data: ❌ READ FAILED amount=%d, error=%d\n", amount, rc);
    } else {
        printf("[DEBUG] read_audio_data: ✅ Successfully read %d bytes\n", rc);
    }
    
  	fs_close(&read_file);

    return rc;
}

int write_to_file(uint8_t *data, uint32_t length)
{
    struct fs_file_t write_file;
    fs_file_t_init(&write_file);
    uint8_t *write_ptr = data;
    
    int ret = fs_open(&write_file, write_buffer, FS_O_WRITE | FS_O_APPEND);
    if (ret < 0) {
        LOG_ERR("Failed to open file for writing: %d", ret);
        return ret;
    }
    
    ret = fs_write(&write_file, write_ptr, length);
    fs_close(&write_file);
    
    if (ret < 0) {
        LOG_ERR("Failed to write to file: %d", ret);
        return ret;
    }
    
    // Return number of bytes written (positive value) or error (negative)
    return ret;
}
    
int initialize_audio_file(uint8_t num) 
{
    char *header = generate_new_audio_header(num);
    if (header == NULL) 
    {
        return -1;
    }
    create_file(header);
    k_free(header);
    return 0;
}

char* generate_new_audio_header(uint8_t num) 
{
    if (num > 99 ) return NULL;
    char *ptr_ = k_malloc(14);
    ptr_[0] = 'a';
    ptr_[1] = 'u';
    ptr_[2] = 'd';
    ptr_[3] = 'i';
    ptr_[4] = 'o';
    ptr_[5] = '/';
    ptr_[6] = 'a';
    ptr_[7] = 48 + (num / 10);
    ptr_[8] = 48 + (num % 10);
    ptr_[9] = '.';
    ptr_[10] = 't';
    ptr_[11] = 'x';
    ptr_[12] = 't';
    ptr_[13] = '\0';

    return ptr_;
}

int get_file_contents(struct fs_dir_t *zdp, struct fs_dirent *entry) 
{
   if (zdp->mp->fs->readdir(zdp, entry) ) 
   {
    return -1;
   }
   if (entry->name[0] == 0) 
   {
    return 0;
   }
   int count = 0;  
   file_num_array[count] = entry->size;
   LOG_INF("file numarray %d %d ",count,file_num_array[count]);
   LOG_INF("file name is %s ", entry->name);
   count++;
   while (zdp->mp->fs->readdir(zdp, entry) == 0 ) 
   {
        if (entry->name[0] ==  0 )
        {
            break;
        }
        file_num_array[count] = entry->size;
        LOG_INF("file numarray %d %d ",count,file_num_array[count]);
        LOG_INF("file name is %s ", entry->name);
        count++;
   }
   return count;
}
//we should clear instead of delete since we lose fifo structure 
int clear_audio_file(uint8_t num) 
{
    char *clear_header = generate_new_audio_header(num);
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, clear_header);
    k_free(clear_header);
    int res = fs_unlink(current_full_path);
    if (res) 
    {
        LOG_ERR("error deleting file");
        return -1;
    }

    char *create_file_header = generate_new_audio_header(num);
    k_msleep(10);
    res = create_file(create_file_header);
    k_free(create_file_header);
    if (res) 
    {
        LOG_ERR("error creating file");
        return -1;
    }

    return 0;
}

int delete_audio_file(uint8_t num) 
{
    char *ptr = generate_new_audio_header(num);
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, ptr);
    k_free(ptr);
    int res = fs_unlink(current_full_path);
    if (res) 
    {
        LOG_PRINTK("error deleting file in delete\n");
        return -1;
    }

    return 0;
}
//the nuclear option.
int clear_audio_directory() 
{
    if (file_count == 1) 
    {
        return 0;
    }
    //check if all files are zero
    // char* path_ = "/SD:/audio";
    // clear_audio_file(file_count);
    int res=0;
    for (uint8_t i = file_count ; i > 0; i-- ) 
    {
        res = delete_audio_file(i);
        k_msleep(10);
        if (res) 
        {
            LOG_PRINTK("error on %d\n",i);
            return -1;
        }  
    }
    res = fs_unlink(SDCARD_AUDIO_PATH);
    if (res) 
    {
        LOG_ERR("error deleting file");
        return -1;
    }
    res = fs_mkdir(SDCARD_AUDIO_PATH);
    if (res) 
    {
        LOG_ERR("failed to make directory");
        return -1;
    }
    res = create_file("audio/a01.txt");
    if (res) 
    {
        LOG_ERR("failed to make new file in directory files");
        return -1;
    }
    LOG_ERR("done with clearing");

    file_count = 1;  
    move_write_pointer(1);
    return 0;
    //if files are cleared, then directory is oked for destrcution.
}

int save_offset(uint32_t offset)
{
    uint8_t buf[4] = {
	offset & 0xFF,
	(offset >> 8) & 0xFF,
	(offset >> 16) & 0xFF, 
	(offset >> 24) & 0xFF 
    };

    struct fs_file_t write_file;
    fs_file_t_init(&write_file);
    int res = fs_open(&write_file, SDCARD_INFO_FILE, FS_O_WRITE | FS_O_CREATE);
    if (res) 
    {
        LOG_ERR("error opening file %d",res);
        return -1;
    }
    res = fs_write(&write_file,&buf,4);
    if (res < 0)
    {
        LOG_ERR("error writing file %d",res);
        return -1;
    }
    fs_close(&write_file);
    return 0;
}

int get_offset()
{
    uint8_t buf[4];
    struct fs_file_t read_file;
    fs_file_t_init(&read_file);
    int rc = fs_open(&read_file, SDCARD_INFO_FILE, FS_O_READ | FS_O_RDWR);
    if (rc < 0)
    {
        LOG_ERR("error opening file %d",rc);
        return -1;
    }
    rc = fs_seek(&read_file,0,FS_SEEK_SET);
    if (rc < 0)
    {
        LOG_ERR("error seeking file %d",rc);
        return -1;
    }
    rc = fs_read(&read_file, &buf, 4);
    if (rc < 0)
    {
        LOG_ERR("error reading file %d",rc);
        return -1;
    }
    fs_close(&read_file);
    uint32_t *offset_ptr = (uint32_t*)buf;
    LOG_INF("get offset is %d",offset_ptr[0]);
    fs_close(&read_file);

    return offset_ptr[0];
}

int save_chunk_counter(uint32_t counter)
{
    uint8_t buf[4] = {
        counter & 0xFF,
        (counter >> 8) & 0xFF,
        (counter >> 16) & 0xFF, 
        (counter >> 24) & 0xFF 
    };

    struct fs_file_t write_file;
    fs_file_t_init(&write_file);
    int res = fs_open(&write_file, SDCARD_CHUNK_COUNTER_FILE, FS_O_WRITE | FS_O_CREATE);
    if (res < 0) 
    {
        LOG_ERR("error opening chunk counter file %d", res);
        return res;
    }
    res = fs_write(&write_file, &buf, 4);
    if (res < 0)
    {
        LOG_ERR("error writing chunk counter file %d", res);
        fs_close(&write_file);
        return res;
    }
    fs_close(&write_file);
    return 0;
}

int get_chunk_counter(uint32_t *counter)
{
    if (counter == NULL) {
        return -EINVAL;
    }
    
    uint8_t buf[4];
    struct fs_file_t read_file;
    fs_file_t_init(&read_file);
    int rc = fs_open(&read_file, SDCARD_CHUNK_COUNTER_FILE, FS_O_READ);
    if (rc < 0)
    {
        // File doesn't exist, start with counter 0
        LOG_INF("chunk counter file doesn't exist, starting with 0");
        *counter = 0;
        return 0;
    }
    
    rc = fs_read(&read_file, &buf, 4);
    fs_close(&read_file);
    
    if (rc < 0)
    {
        LOG_ERR("error reading chunk counter file %d", rc);
        return rc; // Return the actual error code
    }
    
    if (rc != 4) {
        LOG_ERR("incomplete read of chunk counter, got %d bytes", rc);
        return -EIO;
    }
    
    uint32_t *counter_ptr = (uint32_t*)buf;
    *counter = counter_ptr[0];
    LOG_INF("loaded chunk counter: %d", *counter);
    return 0;
}

void sd_off()
 {
//    gpio_pin_set_dt(&sd_en_gpio_pin, 0);  
    sd_enabled = false; 
}


void sd_on()
{
//    gpio_pin_set_dt(&sd_en_gpio_pin, 1);  
    sd_enabled = true; 
}

bool is_sd_on()
{
    return sd_enabled;
}

char* generate_timestamp_audio_filename(void)
{
    // Increment and save the chunk counter for unique filenames across reboots
    chunk_counter++;
    int ret = save_chunk_counter(chunk_counter);
    if (ret < 0) {
        LOG_ERR("Failed to save chunk counter: %d", ret);
        // Continue anyway - we can still generate filename with current counter
    }
    
    int64_t current_time = k_uptime_get();
    
    // Simple timestamp based on uptime (in seconds since boot)
    uint32_t uptime_seconds = current_time / 1000;
    uint32_t hours = (uptime_seconds / 3600) % 24;
    uint32_t minutes = (uptime_seconds / 60) % 60;
    uint32_t seconds = uptime_seconds % 60;
    
    char *filename = k_malloc(CHUNK_FILENAME_MAX_LENGTH);
    if (filename == NULL) {
        LOG_ERR("Failed to allocate memory for chunk filename");
        return NULL;
    }
    
    // Format: audio/chunk_HHMMSS_NNNNN.b (with unique counter after timestamp)  
    int len = snprintf(filename, CHUNK_FILENAME_MAX_LENGTH, CHUNK_FILENAME_FORMAT, 
                      (int)hours, (int)minutes, (int)seconds, (int)chunk_counter);
    
    printf("[DEBUG] generate_timestamp_audio_filename: Generated filename: %s\n", filename);
    
    if (len >= 40 || len < 0) {
        LOG_ERR("Filename too long or formatting error");
        k_free(filename);
        return NULL;
    }
    
    LOG_DBG("Generated chunk filename: %s", filename);
    return filename;
}

int initialize_chunk_file(void)
{
    // Safety check - ensure chunking is enabled and SD is properly initialized
    if (!chunking_enabled) {
        LOG_ERR("Cannot initialize chunk - chunking disabled");
        return SDCARD_ERR_CHUNKING_DISABLED;
    }
    
    if (!sd_enabled) {
        LOG_ERR("Cannot initialize chunk - SD not enabled");
        return SDCARD_ERR_SD_NOT_ENABLED;
    }
    
    char *filename = generate_timestamp_audio_filename();
    if (filename == NULL) {
        LOG_ERR("Failed to generate chunk filename - out of memory");
        return SDCARD_ERR_FILENAME_GENERATION;
    }
    
    // Copy to current chunk filename buffer
    strncpy(current_chunk_filename, filename, sizeof(current_chunk_filename) - 1);
    current_chunk_filename[sizeof(current_chunk_filename) - 1] = '\0';
    
    // Create the file
    int ret = create_file(filename);
    k_free(filename);
    
    if (ret == 0) {
        // Update write buffer to point to new file
        int len = snprintf(write_buffer, sizeof(write_buffer), "%s%s", disk_mount_pt, current_chunk_filename);
        if (len >= sizeof(write_buffer)) {
            LOG_ERR("Write buffer path too long, truncated");
        }
        atomic_set(&chunk_cycle_counter, 0);     // Thread-safe: Reset cycle counter for new chunk
        chunk_active = true;
        atomic_set(&should_rotate_flag, 0);      // Thread-safe: Reset rotation flag for new chunk
        LOG_INF("NEW AUDIO CHUNK CREATED: %s", current_chunk_filename);
        LOG_INF("File path: %s", write_buffer);
        LOG_INF("Chunk will rotate in %d cycles (%d seconds)", CHUNK_DURATION_CYCLES, CHUNK_DURATION_CYCLES / 2);
        
        // Trigger cache update since a new file was created
        trigger_cache_update();
    } else {
        LOG_ERR("Failed to create chunk file: %d", ret);
        // Reset chunk state on failure
        chunk_active = false;
        memset(current_chunk_filename, 0, sizeof(current_chunk_filename));
    }
    
    return ret;
}

bool should_rotate_chunk(void)
{
    // Safety check - if chunking disabled, SD not enabled, or system still booting
    if (!chunking_enabled || !sd_enabled || !system_boot_complete) {
        return false;
    }
    
    if (!chunk_active) {
        return true; // No active chunk, should start one
    }
    
    // Thread-safe: Atomic read of the rotation flag
    return atomic_get(&should_rotate_flag) != 0;
}

void check_chunk_rotation_timing(void)
{
    // This function should be called every 500ms from main loop
    // Only check timing if chunking is enabled and chunk is active
    if (!chunking_enabled || !sd_enabled || !system_boot_complete || !chunk_active) {
        atomic_set(&should_rotate_flag, 0);  // Clear flag
        atomic_set(&chunk_cycle_counter, 0); // Reset counter when not active
        return;
    }
    
    // Thread-safe: Atomic increment of the cycle counter
    uint32_t current_cycles = atomic_inc(&chunk_cycle_counter);
    
    // Set the flag if we've reached the target number of cycles
    if (current_cycles >= CHUNK_DURATION_CYCLES) {
        atomic_set(&should_rotate_flag, 1);
    }
}

int start_new_chunk(void)
{
    if (chunk_active) {
        uint32_t cycles = atomic_get(&chunk_cycle_counter);  // Thread-safe read
        LOG_INF("FINALIZING CHUNK: %s", current_chunk_filename);
        LOG_INF("Duration: %d cycles (%d seconds)", cycles, cycles / 2);
        // Current chunk is automatically finalized when we stop writing to it
    }
    
    return initialize_chunk_file();
}

void set_system_boot_complete(void)
{
    system_boot_complete = true;
    LOG_INF("System boot marked as complete - chunking enabled");
}

void update_files_cache(void)
{
    // This function runs in MAIN THREAD context - safe to use fs_opendir
    if (!atomic_get(&cache_update_flag)) {
        return;  // No update needed
    }
    
    if (!sd_enabled) {
        printf("[DEBUG] update_files_cache: SD card not enabled\n");
        return;
    }
    
    printf("[DEBUG] update_files_cache: Starting cache update (MAIN THREAD - SAFE)\n");
    
    struct fs_dir_t dir;
    struct fs_dirent entry;
    int res;
    int local_file_count = 0;
    
    // Clear the cache first
    memset(recent_files_cache, 0, sizeof(recent_files_cache));
    
    fs_dir_t_init(&dir);
    res = fs_opendir(&dir, SDCARD_AUDIO_PATH);
    if (res) {
        LOG_ERR("Failed to open audio directory for cache update: %d", res);
        printf("[DEBUG] update_files_cache: Failed to open audio directory: %d\n", res);
        cached_file_count = 0;
        // Clear file_num_array for storage system
        extern uint8_t file_count;
        file_count = 0;
        file_num_array[0] = 0;
        file_num_array[1] = 0;
        atomic_set(&cache_update_flag, 0);  // Clear flag even on error
        return;
    }
    
    printf("[DEBUG] update_files_cache: Successfully opened audio directory\n");
    
    // Read directory entries and populate cache with REAL files
    while ((res = fs_readdir(&dir, &entry)) == 0 && local_file_count < MAX_CACHED_FILES) {
        if (entry.name[0] == 0) {
            // End of directory
            printf("[DEBUG] update_files_cache: End of directory reached\n");
            break;
        }
        
        // Skip hidden files and directories
        if (entry.name[0] == '.') {
            continue;
        }
        
        // Only include .b files (chunk files) and .txt files (legacy)
        if (strstr(entry.name, ".b") != NULL || strstr(entry.name, ".txt") != NULL) {
            strncpy(recent_files_cache[local_file_count], entry.name, MAX_FILENAME_LENGTH - 1);
            recent_files_cache[local_file_count][MAX_FILENAME_LENGTH - 1] = '\0';  // Ensure null termination
            
            printf("[DEBUG] update_files_cache: Cached file %d: %s (size: %d bytes)\n", 
                   local_file_count + 1, recent_files_cache[local_file_count], (int)entry.size);
            
            // CRITICAL: Update file_num_array for storage download system compatibility
            if (local_file_count < 2) {  // Only store first 2 files in file_num_array for now
                file_num_array[local_file_count] = entry.size;
                printf("[DEBUG] update_files_cache: Updated file_num_array[%d] = %d bytes\n", 
                       local_file_count, (int)entry.size);
            }
            
            local_file_count++;
        }
    }
    
    fs_closedir(&dir);
    
    cached_file_count = local_file_count;
    
    // Update global file_count for storage system (declared as extern in storage.c)
    extern uint8_t file_count;
    file_count = (local_file_count > 0) ? local_file_count : 0;
    
    // If we have fewer than 2 files, clear remaining file_num_array entries
    for (int i = local_file_count; i < 2; i++) {
        file_num_array[i] = 0;
    }
    
    atomic_set(&cache_update_flag, 0);  // Clear update flag
    
    printf("[DEBUG] update_files_cache: Cache updated with %d REAL files\n", cached_file_count);
    printf("[DEBUG] update_files_cache: Updated global file_count=%d, file_num_array[0]=%d, file_num_array[1]=%d\n", 
           file_count, file_num_array[0], file_num_array[1]);
    LOG_INF("File cache updated: %d files", cached_file_count);
}

void trigger_cache_update(void)
{
    atomic_set(&cache_update_flag, 1);
    printf("[DEBUG] trigger_cache_update: Cache update requested\n");
}

int delete_chunk_file(const char* filename)
{
    if (!sd_enabled) {
        LOG_ERR("SD card not enabled");
        printf("[DEBUG] delete_chunk_file: SD card not enabled\n");
        return -ENODEV;
    }
    
    if (filename == NULL || strlen(filename) == 0) {
        LOG_ERR("Invalid filename");
        printf("[DEBUG] delete_chunk_file: Invalid filename\n");
        return -EINVAL;
    }
    
    char full_path[MAX_PATH_LENGTH];
    snprintf(full_path, sizeof(full_path), "%saudio/%s", disk_mount_pt, filename);
    
    printf("[DEBUG] delete_chunk_file: Attempting to delete: %s\n", full_path);
    
    // Check if file exists first
    struct fs_dirent entry;
    int res = fs_stat(full_path, &entry);
    if (res != 0) {
        LOG_ERR("File not found: %s", filename);
        printf("[DEBUG] delete_chunk_file: File not found: %s\n", filename);
        return -ENOENT;
    }
    
    // Delete the file
    res = fs_unlink(full_path);
    if (res != 0) {
        LOG_ERR("Failed to delete file %s: %d", filename, res);
        printf("[DEBUG] delete_chunk_file: Failed to delete %s: %d\n", filename, res);
        return res;
    }
    
    printf("[DEBUG] delete_chunk_file: ✅ Successfully deleted: %s\n", filename);
    
    // Update the cache to reflect the deletion
    trigger_cache_update();
    
    return 0;
}

int get_audio_file_names(char* buffer, size_t buffer_size)
{
    printf("[DEBUG] get_audio_file_names: Called with buffer_size=%d (BLE THREAD CONTEXT)\n", (int)buffer_size);
    
    if (buffer == NULL || buffer_size == 0) {
        LOG_ERR("Invalid buffer parameters");
        printf("[DEBUG] get_audio_file_names: Invalid buffer parameters\n");
        return -EINVAL;
    }
    
    if (!sd_enabled) {
        LOG_ERR("SD card not enabled");
        printf("[DEBUG] get_audio_file_names: SD card not enabled\n");
        return -ENODEV;
    }
    
    printf("[DEBUG] get_audio_file_names: Using CACHED REAL FILES (thread-safe)\n");
    printf("[DEBUG] get_audio_file_names: Cache contains %d real files\n", cached_file_count);
    
    int offset = 0;
    int file_count = 0;
    
    // Copy real cached filenames to buffer (thread-safe read)
    for (int i = 0; i < cached_file_count && file_count < MAX_CACHED_FILES; i++) {
        if (recent_files_cache[i][0] != '\0') {  // File exists in cache
            int name_len = strlen(recent_files_cache[i]);
            
            // Check if we have space (name length + newline + null terminator + safety margin)
            if (offset + name_len + 2 < buffer_size) {
                strcpy(buffer + offset, recent_files_cache[i]);
                offset += name_len;
                buffer[offset++] = '\n';
                file_count++;
                printf("[DEBUG] get_audio_file_names: Added REAL file %d: %s\n", file_count, recent_files_cache[i]);
            } else {
                printf("[DEBUG] get_audio_file_names: Buffer full, stopping at %d files\n", file_count);
                break;
            }
        }
    }
    
    // If no cached files, add informational message
    if (file_count == 0) {
        const char* no_files = "no_files_cached.info";
        if (strlen(no_files) + 1 < buffer_size) {
            strcpy(buffer, no_files);
            offset = strlen(no_files);
            file_count = 1;
            printf("[DEBUG] get_audio_file_names: No cached files, returning info message\n");
        }
    }
    
    printf("[DEBUG] get_audio_file_names: File enumeration complete, found %d files\n", file_count);
    
    if (offset > 0) {
        buffer[offset - 1] = '\0';  // Replace last newline with null terminator
        offset--;  // Adjust offset to not count the null terminator
        printf("[DEBUG] get_audio_file_names: Replaced last newline with null terminator\n");
    } else {
        buffer[0] = '\0';  // Empty list
        printf("[DEBUG] get_audio_file_names: No files found, empty list\n");
    }
    
    LOG_INF("Found %d files, %d bytes of file names", file_count, offset);
    printf("[DEBUG] get_audio_file_names: Final result: %d files, %d bytes\n", file_count, offset);
    
    printf("[DEBUG] get_audio_file_names: Returning offset=%d\n", offset);
    return offset;
}



