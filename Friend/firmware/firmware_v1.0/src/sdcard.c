#include <zephyr/kernel.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/logging/log.h>
#include <zephyr/device.h>
#include <zephyr/fs/fs.h>
#include <ff.h>
#include "sdcard.h"
static FATFS fat_fs;

static struct fs_mount_t mount_point = {
	.type = FS_FATFS,
	.fs_data = &fat_fs,
};
static bool mounted = false;
bool sd_card_mounted = false;

#define INFO_FILE "SD:/info.txt"

static char current_full_path[256];
static const char *disk_mount_pt = "/SD:/";

int mount_sd_card(void)
{
	uint64_t memory_size_mb;
	uint32_t block_count;
	uint32_t block_size;
    static const char *disk_pdrv = "SD";  
	int err = disk_access_init(disk_pdrv); 
    printk("disk_access_init: %d\n", err);
	if (disk_access_ioctl(disk_pdrv, DISK_IOCTL_GET_SECTOR_COUNT, &block_count)) 
    {
		printk("Unable to get sector count\n");
		return -1;
	}
    	if (disk_access_ioctl(disk_pdrv, DISK_IOCTL_GET_SECTOR_SIZE, &block_size)) 
    {
		printk("Unable to get sector count\n");
		return -1;
	}
    printk("Sector size is %u\n",block_size);

    memory_size_mb = (uint64_t)block_count * block_size;

    printk("Memory size: %u\n",memory_size_mb);

    mount_point.mnt_point = "/SD:";
    int res = fs_mount(&mount_point);

    if (res == FR_OK) {
        mounted = true;
        sd_card_mounted = true;
        printk("SD card mounted successfully\n");
    } else {
        printk("f_mount failed: %d\n", res);
        return -1;
    }

    res = fs_mkdir("/SD:/audio");
    if (res == FR_OK) {
        printk("audio directory created successfully\n");
    }
    else if (res == FR_EXIST) {
        printk("audio directory already exists\n");
    }
     else {
        printk("audio directory creation failed: %d\n", res);
        return -1;
    }

	return 0;
}

int create_file(const char *file_path){

    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, file_path);

    int ret = 0;
	struct fs_file_t data_filp;
	fs_file_t_init(&data_filp);

	ret = fs_open(&data_filp, current_full_path, FS_O_WRITE | FS_O_CREATE);

	if (ret) 
	{
      printk("File creation failed %d\n", ret);
		return -2;
	} 
    fs_close(&data_filp);

    return 0;
}

int write_info(const char *data)
{
    int ret = 0;
    struct fs_file_t data_filp;
	fs_file_t_init(&data_filp);

	// ret = fs_unlink("/SD:/info.txt");

   	ret = fs_open(&data_filp, "/SD:/info.txt", FS_O_WRITE | FS_O_APPEND);
    if(ret)
    {
        printk("Error creating and writing file\n");
        return -1;
    }

    printk("File wrote successfully\n");

	ret = fs_write(&data_filp, data, strlen(data));

	if(ret < 0)
	{
		return -1;
	}
	
    fs_close(&data_filp);

    return 0;
}
static struct fs_file_t data_filp_;
int write_to_file(const char *data,uint16_t length)
{
    int ret = 0;
    struct fs_file_t data_filp;
	fs_file_t_init(&data_filp);


   	ret = fs_open(&data_filp, "/SD:/audio/A1.txt", FS_O_WRITE | FS_O_APPEND);
    if(ret)
    {
        printk("Error opening file\n");
        return -1;
    }



	ret = fs_write(&data_filp, data, strlen(data));
    printk("File wrote successfully\n");
	if(ret < 0)
	{
		return -1;
	}
    fs_close(&data_filp);
    return 0;
}
#define MAX_INFO_FILE_LENGTH 256
char* get_info_file_data_() {
	struct fs_file_t file;
   	fs_file_t_init(&file); 
    printk("hello 3\n");
    k_msleep(10);
	char *boot_count = (char*)k_malloc(MAX_INFO_FILE_LENGTH);
    for (int i = 0; i < MAX_INFO_FILE_LENGTH; i++) {
        boot_count[i] = 0;
    }
    printk("hello 5\n");
    k_msleep(10);
	int rc = fs_open(&file, "/SD:/info.txt", FS_O_READ | FS_O_RDWR);
    printk("hello 4\n");
    k_msleep(10);
    printk("result of file open%d\n",rc);
    rc = fs_read(&file, boot_count, 256);
    printk("result of file read%d\n",rc);
  	fs_close(&file);
    return boot_count;
}
//this method will write to an already open file. we will enforce that the file is opened

static audio_info_t current_audio_file;
// fs_stat() check if dircetory exists
int initialize_audio_file() {
    current_audio_file.name = "A1.txt";
    char temp[16] = "a00 00000000000\n";
    current_audio_file.size = 0;
    struct fs_file_t *temp_file = malloc(sizeof(struct fs_file_t));
    fs_file_t_init(temp_file);
    int ret = fs_open(temp_file, "/SD:/audio/A1.txt", FS_O_WRITE | FS_O_APPEND);
    printk("result of audio open: %d\n",ret);
    current_audio_file.file = temp_file;
    

    return 0;
}

int close_audio_file() {
       fs_close(current_audio_file.file);
       k_free(current_audio_file.file);
       return 0;
}

int get_audio_file(const char *buf) {
    return 1;
}

int write_audio_file_unsafe(uint8_t *buf, int amount) {
    int amount_left = 0;
    int amount_ =0;
    while(amount >= amount_left) {
   	amount_ = fs_write(current_audio_file.file, buf+amount_left, amount);
    amount_left+=amount_;
    printk("amount_left: %d\n",amount_left);
    }
    
    printk("File wrote successfully\n");

    return 0;

}

int update_length_on_audio_file() {

}
