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
#define AUDIO_DIRECTORY "/SD:/audio/"
#define MAX_PATH_LENGTH 32
#define MAX_INFO_ENTRY_LENGTH 2
static char current_full_path[MAX_PATH_LENGTH];
static const char *disk_mount_pt = "/SD:/";

//hehe...
char* generate_new_audio_header(uint8_t num) {
    if (num > 9 ) return NULL;
    char *ptr_ = k_malloc(14);
    ptr_[0] = 'a';
    ptr_[1] = 'u';
    ptr_[2] = 'd';
    ptr_[3] = 'i';
    ptr_[4] = 'o';
    ptr_[5] = '/';
    ptr_[6] = 'a';
    ptr_[7] = '0';
    ptr_[8] = 48 + num;
    ptr_[9] = '.';
    ptr_[10] = 't';
    ptr_[11] = 'x';
    ptr_[12] = 't';
    ptr_[13] = '\0';

    return ptr_;
}

uint8_t get_info_file_length() {
 	struct fs_file_t file;
   	fs_file_t_init(&file); 
	uint8_t length[2];
	int rc = fs_open(&file, "/SD:/info.txt", FS_O_READ | FS_O_RDWR);
    rc = fs_seek(&file,0,FS_SEEK_SET);
    rc = fs_read(&file, length, 1);
  	fs_close(&file);
    printk("length is %d\n",length[0]);
    return length[0];
}

uint8_t update_info_file_length(uint8_t num) {
 	struct fs_file_t file;
   	fs_file_t_init(&file);

	uint8_t length[16] = {num+'0'};
    for (int i =1; i < 15; i++) {
        length[i] = ' ';
    }
    length[15] = '\n';
	int rc = fs_open(&file, "/SD:/info.txt", FS_O_WRITE);
    rc = fs_seek(&file,0,FS_SEEK_SET);

    printk("result of file open%d\n",rc);
    rc = fs_write(&file, length, 16);
    printk("result of file read%d\n",rc);
  	fs_close(&file);
    printk("length is %d\n",length[0]);
    return length[0];
}

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
    // res = fs_unlink("/SD:/info.txt");

    res = fs_mkdir("/SD:/audio");
    if (res == FR_OK) {
        printk("audio directory created successfully\n");
    }
    else if (res == FR_EXIST) {
        printk("audio directory already exists\n");
    }
     else {
        printk("audio directory creation failed: %d\n", res);
    }

    struct fs_dirent entry; //check if the info file exists. if not, generate new info file
    const char *info_path = "/SD:/info.txt";
    res = fs_stat(info_path,&entry);
    if (res) {
        res = create_file("info.txt");
        printk("result of info.txt creation: %d\n ",res);
        update_info_file_length(0);
    }

    printk("info file size is %d\n",entry.size);
    printk("result of check: %d\n",res);

    // snprintf(current_full_path, sizeof(current_full_path), "%s%s%s", disk_mount_pt, disk_mount_pt,disk_mount_pt);
    // printk("%s\n",current_full_path);

    //attempt to create new audio file per reset
    uint8_t current_file_num = get_info_file_length();
    
    uint8_t next_file_num = current_file_num + 1;
    printk("current number of audio files is%d\n ", current_file_num);
    char *ptr_ = generate_new_audio_header(next_file_num); // will return (audio/axx.txt)
    update_info_file_length(next_file_num);

    if(ptr_ != NULL) {
    res = create_file(ptr_);
    k_free(ptr_);
    }
    else {
        printk("bad header\n");
    }

    //generate new entry in info file
    


    // res = create_file("audio/a01.txt");
    // printk("result of audio text creation: %d\n ",res);

	return 0;
}

int create_file(const char *file_path){
    //MAGIC STRING CAT!!!!!!!
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

#define INFO_ENTRY_SIZE 16
//need length,name
//a01 00000000000\n
int write_entry_info(uint8_t entry_num,uint32_t size)
{
    if (entry_num == 0) return -1;
    int ret = 0;
    uint8_t *result = malloc(16 * sizeof(uint8_t));
    result[0] = 'a';
    result[1] = '0';
    result[2] = '0'+entry_num;
    result[3] = ' ';
    result[4] = '0';
    result[5] = '0';
    result[6] = '0';
    result[7] = '0';
    result[8] = '0';
    result[9] = '0';
    result[10] = (size % 100000)  / 10000 +'0';
    result[11] = (size % 10000)  / 1000 +'0';
    result[12] = (size % 1000) / 100 + '0';
    result[13] = (size % 100) / 10 + '0';
    result[14] = (size % 10) + '0';
    result[15] = '\n';

    struct fs_file_t data_filp;
	fs_file_t_init(&data_filp);

    printk("\n");
   	ret = fs_open(&data_filp, "/SD:/info.txt", FS_O_WRITE);

    if(ret)
    {
        printk("Error creating and writing file\n");
        return -1;
    }
    fs_seek(&data_filp,0+ 16 * entry_num,FS_SEEK_SET);
	ret = fs_write(&data_filp, result, INFO_ENTRY_SIZE);

    printk("total written %d\n",ret);
    free(result);

	if(ret < 0)
	{
		return -1;
	}
	
    fs_close(&data_filp);
    return 0;
}


int write_to_file(uint8_t *data,uint32_t length)
{
    int ret = 0;
    struct fs_file_t data_filp;
	fs_file_t_init(&data_filp);
    uint8_t *temp_ptr = data;

   	ret = fs_open(&data_filp, "/SD:/audio/a01.txt", FS_O_WRITE | FS_O_APPEND);
    if(ret)
    {
        printk("Error opening file\n");
        return -1;
    }

	ret = fs_write(&data_filp, temp_ptr, length);
    printk("File wrote successfully, wrote %d\n",ret);
	if(ret < 0)
	{
		return -1;
	}
    fs_close(&data_filp);
    return 0;
}

int update_length_on_audio_file() {

        
}


#define MAX_INFO_FILE_LENGTH 256
char* get_info_file_data_() {
	struct fs_file_t file;
   	fs_file_t_init(&file); 
	char *boot_count = (char*)k_malloc(MAX_INFO_FILE_LENGTH);
    for (int i = 0; i < MAX_INFO_FILE_LENGTH; i++) {
        boot_count[i] = 0;
    }
	int rc = fs_open(&file, "/SD:/info.txt", FS_O_READ | FS_O_RDWR);
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
    printk("about to close\n");
    k_msleep(10); 
       fs_close(current_audio_file.file);
       k_free(current_audio_file.file);
       return 0;
}
static int pos_ = 0;
int read_audio_data(uint8_t *buf, int amount,int offset) {
    struct fs_file_t file;
    uint8_t *temp_ptr = buf;
    printk("about to f\n");
    k_msleep(10);
   	fs_file_t_init(&file); 
	int rc = fs_open(&file, "/SD:/audio/a01.txt", FS_O_READ | FS_O_RDWR);

    printk("result of file open%d\n",rc);
    k_msleep(10);
    rc = fs_seek(&file,offset,FS_SEEK_SET);
    printk("result of file seek: %d\n",rc);
    rc = fs_read(&file, temp_ptr, amount);
    printk("result of file read%d\n",rc);
  	fs_close(&file);
    return rc;
}

int get_file_size(){
    struct fs_dirent entry; 
    const char *audio_path = "/SD:/audio/a01.txt";
    fs_stat(audio_path,&entry);
    return entry.size;
 }
