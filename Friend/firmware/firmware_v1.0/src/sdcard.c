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

// read_params_t read_file(const char *file_path)
// {
// 	read_params_t readParams;
// 	readParams.ret = 0;
//     char boot_count[1000];
// 	struct fs_file_t file;
// 	int rc;

// 	int ret = set_path(file_path);
	
// 	if(ret)
// 	{
// 		readParams.ret = -1;
// 		return readParams;
// 	}
	
// 	fs_file_t_init(&file);
	
// 	rc = fs_open(&file, current_full_path, FS_O_READ | FS_O_RDWR);
	
// 	if (rc < 0)
// 	{
// 		printk("FAIL: open %s: %d\n", current_full_path, rc);
// 		readParams.ret = rc;
// 		return readParams;
// 	}
//     	rc = fs_read(&file, &boot_count, sizeof(boot_count));
	
// 	if (rc < 0)
// 	{
// 		printk("FAIL: read %s: [rd:%d]\n", current_full_path, rc);
// 	}

//     boot_count[rc] = 0;

// 	readParams.data = boot_count;

// 	fs_close(&file);

// 	return readParams;
// }
	
