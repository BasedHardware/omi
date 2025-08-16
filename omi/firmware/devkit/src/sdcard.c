#include <ff.h>
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/fs/fs.h>
#include <zephyr/fs/fs_sys.h>
#include <zephyr/logging/log.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/sys/check.h>
#include <string.h>
#include "sdcard.h"

LOG_MODULE_REGISTER(sdcard, CONFIG_LOG_DEFAULT_LEVEL);

static FATFS fat_fs;

static struct fs_mount_t mount_point = {
	.type = FS_FATFS,
	.fs_data = &fat_fs,
};

struct gpio_dt_spec sd_en_gpio_pin = { .port = DEVICE_DT_GET(DT_NODELABEL(gpio0)), .pin=19, .dt_flags = GPIO_INT_DISABLE };

uint8_t file_count = 0;

#define MAX_PATH_LENGTH 32
static char current_full_path[MAX_PATH_LENGTH];
static char read_buffer[MAX_PATH_LENGTH];
static char write_buffer[MAX_PATH_LENGTH];

uint32_t file_num_array[2];    

static const char *disk_mount_pt = "/SD:/";

bool sd_enabled = false;

// Chunking variables
static int64_t chunk_start_time = 0;
static char current_chunk_filename[64];
bool chunk_active = false;  // Made non-static for external access
static bool system_boot_complete = false;  // Prevent chunking during boot
bool chunking_enabled = true;  // GLOBAL FLAG: Set to true to enable chunking system
#define CHUNK_DURATION_MS (0.5 * 60 * 1000)  // 5 minutes in milliseconds for production

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
    
    res = fs_mkdir("/SD:/audio");

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
        // Use new chunking system - skip legacy file processing
        LOG_INF("Using chunking system");
        file_count = 1;  // Set to 1 for compatibility
    } else {
        // Use legacy file system - restore original logic
        LOG_INF("Using legacy file system");
        struct fs_dir_t audio_dir_entry;
        fs_dir_t_init(&audio_dir_entry);
        err = fs_opendir(&audio_dir_entry,"/SD:/audio");
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
    const char *info_path = "/SD:/info.txt";
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
    struct fs_dirent entry;  

	int rc = fs_open(&read_file, read_buffer, FS_O_READ | FS_O_RDWR);
    rc = fs_seek(&read_file,offset,FS_SEEK_SET);
    rc = fs_read(&read_file, temp_ptr, amount);
    // LOG_PRINTK("read data :");
    // for (int i = 0; i < amount;i++) {
    //     LOG_PRINTK("%d ",temp_ptr[i]);
    // }
    // LOG_PRINTK("\n");
  	fs_close(&read_file);

    return rc;
}

int write_to_file(uint8_t *data,uint32_t length)
{
    struct fs_file_t write_file;
	fs_file_t_init(&write_file);
    uint8_t *write_ptr = data;
   	fs_open(&write_file, write_buffer , FS_O_WRITE | FS_O_APPEND);
	fs_write(&write_file, write_ptr, length);
    fs_close(&write_file);
    return 0;
}
    
int initialize_audio_file(uint8_t num) 
{
    char *header = generate_new_audio_header(num);
    if (header == NULL) 
    {
        return -1;
    }
    k_free(header);
    create_file(header);
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
    res = fs_unlink("/SD:/audio");
    if (res) 
    {
        LOG_ERR("error deleting file");
        return -1;
    }
    res = fs_mkdir("/SD:/audio");
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
    int res = fs_open(&write_file, "/SD:/info.txt" , FS_O_WRITE | FS_O_CREATE);
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
    int rc = fs_open(&read_file, "/SD:/info.txt", FS_O_READ | FS_O_RDWR);
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
    int64_t current_time = k_uptime_get();
    
    // Simple timestamp based on uptime (in seconds since boot)
    // This avoids dependency on RTC but still provides unique filenames
    uint32_t uptime_seconds = current_time / 1000;
    uint32_t hours = (uptime_seconds / 3600) % 24;
    uint32_t minutes = (uptime_seconds / 60) % 60;
    uint32_t seconds = uptime_seconds % 60;
    
    char *filename = k_malloc(32);
    if (filename == NULL) {
        return NULL;
    }
    
    // Format: audio/Hhhmmsss.txt (H=hours, m=minutes, s=seconds since boot)
    snprintf(filename, 32, "audio/%03d%02d%02d.txt", 
             (int)hours, (int)minutes, (int)seconds);
    
    return filename;
}

int initialize_chunk_file(void)
{
    // Safety check - ensure chunking is enabled and SD is properly initialized
    if (!chunking_enabled || !sd_enabled) {
        LOG_ERR("Cannot initialize chunk - chunking disabled or SD not enabled");
        return -1;
    }
    
    char *filename = generate_timestamp_audio_filename();
    if (filename == NULL) {
        LOG_ERR("Failed to generate chunk filename");
        return -1;
    }
    
    // Copy to current chunk filename buffer
    strncpy(current_chunk_filename, filename, sizeof(current_chunk_filename) - 1);
    current_chunk_filename[sizeof(current_chunk_filename) - 1] = '\0';
    
    // Create the file
    int ret = create_file(filename);
    k_free(filename);
    
    if (ret == 0) {
        // Update write buffer to point to new file
        snprintf(write_buffer, sizeof(write_buffer), "%s%s", disk_mount_pt, current_chunk_filename);
        chunk_start_time = k_uptime_get();
        chunk_active = true;
        LOG_INF("NEW AUDIO CHUNK CREATED: %s", current_chunk_filename);
        LOG_INF("File path: %s", write_buffer);
        LOG_INF("Chunk will rotate in %d seconds", CHUNK_DURATION_MS / 1000);
    } else {
        LOG_ERR("Failed to create chunk file: %d", ret);
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
    
    int64_t current_time = k_uptime_get();
    int64_t elapsed_time = current_time - chunk_start_time;
    
    return elapsed_time >= CHUNK_DURATION_MS;
}

int start_new_chunk(void)
{
    if (chunk_active) {
        int64_t current_time = k_uptime_get();
        int64_t chunk_duration = current_time - chunk_start_time;
        LOG_INF("FINALIZING CHUNK: %s", current_chunk_filename);
        LOG_INF("Duration: %d seconds", (int)(chunk_duration / 1000));
        // Current chunk is automatically finalized when we stop writing to it
    }
    
    return initialize_chunk_file();
}

void set_system_boot_complete(void)
{
    system_boot_complete = true;
    LOG_INF("System boot marked as complete - chunking enabled");
}


