#include <zephyr/kernel.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/logging/log.h>
#include <zephyr/device.h>
#include <zephyr/fs/fs.h>
#include <ff.h>
#include <zephyr/fs/fs_sys.h>
#include <zephyr/sys/check.h>
#include "sdcard.h"

LOG_MODULE_REGISTER(sdcard, CONFIG_LOG_DEFAULT_LEVEL);

static FATFS fat_fs;

static struct fs_mount_t mount_point = {
	.type = FS_FATFS,
	.fs_data = &fat_fs,
};

static char *current_header;
#define MAX_PATH_LENGTH 32

uint8_t file_count = 0;

static char current_full_path[MAX_PATH_LENGTH];
static char read_buffer[MAX_PATH_LENGTH];
static char write_buffer[MAX_PATH_LENGTH];
static const char *disk_mount_pt = "/SD:/";

uint32_t get_file_size(uint8_t num){
    char *ptr = generate_new_audio_header(num);
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, ptr);
    k_free(ptr);
    struct fs_dirent entry;
    fs_stat(&current_full_path,&entry);
    return (uint32_t)entry.size;
 }

int move_read_pointer(uint8_t num) {
   char *read_ptr = generate_new_audio_header(num);
   snprintf(read_buffer, sizeof(read_buffer), "%s%s", disk_mount_pt, read_ptr);
//    free(read_ptr);
    struct fs_dirent entry; 
    int res = fs_stat(&read_buffer,&entry);
    if (res) {
        printk("invalid file\n");
        
    return -1;  
    }
   return 0;
}

int move_write_pointer(uint8_t num) {
    char *write_ptr = generate_new_audio_header(num);
    snprintf(write_buffer, sizeof(write_buffer), "%s%s", disk_mount_pt, write_ptr);
    struct fs_dirent entry;
    int res = fs_stat(&write_buffer,&entry);
    if (res) {
        printk("invalid file\n");
        
    return -1;  
    }
    k_free(write_ptr);
    return 0;   
}

uint32_t file_num_array[20];

int mount_sd_card(void)
{
	uint64_t memory_size_mb;
	uint32_t block_count;
	uint32_t block_size;
    static const char *disk_pdrv = "SD";  
	int err = disk_access_init(disk_pdrv); 
    printk("disk_access_init: %d\n", err);
    if (err) {
        k_msleep(2000);
        err = disk_access_init(disk_pdrv); 
        if (err) {
            return -1;
        }
    }
    mount_point.mnt_point = "/SD:";
    int res = fs_mount(&mount_point);

    if (res == FR_OK) {
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
    }

    struct fs_dir_t zdp;
    fs_dir_t_init(&zdp);
    err = fs_opendir(&zdp,"/SD:/audio");
    if (err) {
        printk("error while opening directory \n",err);
        return -1;
    }
    printk("result of opendir: %d\n",err);
    
    struct fs_dirent entry_;
  
    file_count =get_next_item(&zdp, &entry_);
    if (file_count < 0) {
        printk(" error getting file count\n");
        return -1;
    }

    fs_closedir(&zdp);
    printk("current num files: %d\n",file_count);
    file_count++;
    printk("new num files: %d\n",file_count);
    initialize_audio_file(file_count);
    err = move_write_pointer(file_count); 
    if (err) {
        printk("erro while moving the write pointer\n");
        return -1;
    }
    move_read_pointer(file_count);
    if (err) {
        printk("error while moving the reader pointer\n");
        return -1;
    }

    struct fs_dirent entry; //check if the info file exists. if not, generate new info file
    const char *info_path = "/SD:/info.txt";
    res = fs_stat(info_path,&entry);
    if (res) {
        res = create_file("info.txt");
        printk("result of info.txt creation: %d\n ",res);
   
    }
    printk("result of check: %d\n",res);


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

int read_audio_data(uint8_t *buf, int amount,int offset) {
    struct fs_file_t file;
   	fs_file_t_init(&file); 
    uint8_t *temp_ptr = buf;
    struct fs_dirent entry;  


	int rc = fs_open(&file, read_buffer, FS_O_READ | FS_O_RDWR);
    rc = fs_seek(&file,offset,FS_SEEK_SET);
    rc = fs_read(&file, temp_ptr, amount);
    // printk("read data :");
    // for (int i = 0; i < amount;i++) {
    //     printk("%d ",temp_ptr[i]);
    // }
    // printk("\n");
  	fs_close(&file);

    return rc;
}

int write_to_file(uint8_t *data,uint32_t length)
{

    int ret = 0;
    struct fs_file_t data_loc;
	fs_file_t_init(&data_loc);
    uint8_t *temp_ptr = data;
   	ret = fs_open(&data_loc, write_buffer , FS_O_WRITE | FS_O_APPEND);
    if(ret)
    {
        printk("Error opening file\n");
  
        return -1;
    }
	ret = fs_write(&data_loc, temp_ptr, length);
    // // printk("length is %d\n", length);
    // printk("write data: ");
    // for (int i = 0; i < length; i++) {
    //     printk("%d ",temp_ptr[i]);
    // }
    // printk("\n");

	if(ret < 0)
	{
        printk("er %d\n",ret);

		return -1;
	}
    fs_close(&data_loc);

    return 0;
}
    
int initialize_audio_file(uint8_t num) {
    char *header = generate_new_audio_header(num);
    if (header == NULL) {
        return -1;
    }
    k_free(header);
    create_file(header);
    return 0;
}

void print_directory_contents(struct fs_dir_t *zdp, struct fs_dirent *entry) {

   int rc = zdp->mp->fs->readdir(zdp, entry);
    printk("%s %d ",entry->name,entry->size);
		while (true) {
			rc = zdp->mp->fs->readdir(zdp, entry);

			if (rc < 0) {
				break;
			}
			if (entry->name[0] == 0) {
				break;
			}
               printk("%s %d ",entry->name,entry->size);                     
		}
        		if (rc < 0) {
		}
        printk("\n");

}



char* generate_new_audio_header(uint8_t num) {
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

int get_next_item(struct fs_dir_t *zdp, struct fs_dirent *entry) {
   if (zdp->mp->fs->readdir(zdp, entry) ) {
    return -1;
   }
   if (entry->name[0] == 0) {
    return 0;
   }
   int count = 0;  
   file_num_array[count] = entry->size;
   printk("file numarray %d %d \n",count,file_num_array[count]);
   printk("file name is %s \n", entry->name);
   count++;
   while (zdp->mp->fs->readdir(zdp, entry) == 0 ) {
      if (entry->name[0] ==  0 ) {
        break;
      }
      file_num_array[count] = entry->size;
      printk("file numarray %d %d \n",count,file_num_array[count]);
      printk("file name is %s \n", entry->name);
      count++;
   }
   return count;
}