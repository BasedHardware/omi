#include <zephyr/kernel.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/logging/log.h>
#include <zephyr/device.h>
#include <zephyr/fs/fs.h>
#include <ff.h>
#include <zephyr/fs/fs_sys.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/check.h>
#include "sdcard.h"

LOG_MODULE_REGISTER(sdcard, CONFIG_LOG_DEFAULT_LEVEL);

static FATFS fat_fs;

static struct fs_mount_t mount_point = {
	.type = FS_FATFS,
	.fs_data = &fat_fs,
};

struct gpio_dt_spec sd_en_gpio_pin = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio0)), .pin=19, .dt_flags = GPIO_INT_DISABLE};

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
    k_free(read_ptr);
    struct fs_dirent entry; 
    int res = fs_stat(&read_buffer,&entry);
    if (res) {
        LOG_ERR("invalid file\n");
        
    return -1;  
    }
   return 0;
}

int move_write_pointer(uint8_t num) {
    char *write_ptr = generate_new_audio_header(num);
    snprintf(write_buffer, sizeof(write_buffer), "%s%s", disk_mount_pt, write_ptr);
    k_free(write_ptr);
    struct fs_dirent entry;
    int res = fs_stat(&write_buffer,&entry);
    if (res) {
        LOG_ERR("invalid file\n");
        
    return -1;  
    }
    
    return 0;   
}

uint32_t file_num_array[40];

int mount_sd_card(void)
{

    if (gpio_is_ready_dt(&sd_en_gpio_pin)) {
		printk("Haptic Pin ready\n");
	}
    else {
		printk("Error setting up Haptic Pin\n");
        return 1;
	}

	if (gpio_pin_configure_dt(&sd_en_gpio_pin, GPIO_OUTPUT_ACTIVE) < 0) {
		printk("Error setting up Haptic Pin\n");
        return 1;
	}

    static const char *disk_pdrv = "SD";  
	int err = disk_access_init(disk_pdrv); 
    LOG_INF("disk_access_init: %d\n", err);
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
        LOG_INF("SD card mounted successfully");
    } else {
        LOG_ERR("f_mount failed: %d", res);
        return -1;
    }
    
    res = fs_mkdir("/SD:/audio");
    if (res == FR_OK) {
        LOG_INF("audio directory created successfully");
    }
    else if (res == FR_EXIST) {
        LOG_INF("audio directory already exists");
    }
     else {
        LOG_INF("audio directory creation failed: %d", res);
    }

    struct fs_dir_t zdp;
    fs_dir_t_init(&zdp);
    err = fs_opendir(&zdp,"/SD:/audio");
    if (err) {
        LOG_ERR("error while opening directory ",err);
        return -1;
    }
    LOG_INF("result of opendir: %d",err);
    
    struct fs_dirent entry_;
  
    file_count =get_next_item(&zdp, &entry_);
    if (file_count < 0) {
        LOG_ERR(" error getting file count");
        return -1;
    }

    fs_closedir(&zdp);
    LOG_INF("current num files: %d",file_count);
    file_count++;
    LOG_INF("new num files: %d",file_count);
    initialize_audio_file(file_count);
    err = move_write_pointer(file_count); 
    if (err) {
        LOG_ERR("erro while moving the write pointer");
        return -1;
    }
    move_read_pointer(file_count);
    if (err) {
        LOG_ERR("error while moving the reader pointer\n");
        return -1;
    }
    printk("file count: %d\n",file_count);
    clear_audio_directory();
    struct fs_dirent entry; //check if the info file exists. if not, generate new info file
    const char *info_path = "/SD:/info.txt";
    res = fs_stat(info_path,&entry);
    if (res) {
        res = create_file("info.txt");
        LOG_INF("result of info.txt creation: %d ",res);
   
    }
    LOG_INF("result of check: %d",res);


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
      LOG_ERR("File creation failed %d", ret);
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

    struct fs_file_t data_loc;
	fs_file_t_init(&data_loc);
    uint8_t *temp_ptr = data;
   	fs_open(&data_loc, write_buffer , FS_O_WRITE | FS_O_APPEND);
	fs_write(&data_loc, temp_ptr, length);
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
   LOG_INF("file numarray %d %d ",count,file_num_array[count]);
   LOG_INF("file name is %s ", entry->name);
   count++;
   while (zdp->mp->fs->readdir(zdp, entry) == 0 ) {
      if (entry->name[0] ==  0 ) {
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
int clear_audio_file(uint8_t num) {

    char *clear_header = generate_new_audio_header(num);
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, clear_header);
    k_free(clear_header);
    int res = fs_unlink(current_full_path);
    if (res) {
        LOG_ERR("error deleting file");
        return -1;
    }
    char *create_file_header = generate_new_audio_header(num);
    k_msleep(10);
    res = create_file(create_file_header);
    k_free(create_file_header);
    if (res) {
        LOG_ERR("error creating file");
        return -1;
    }

    return 0;
}

int delete_audio_file(uint8_t num) {

    char *ptr = generate_new_audio_header(num);
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, ptr);
    k_free(ptr);
    int res = fs_unlink(current_full_path);
    if (res) {
        printk("error deleting file in delete\n");
        return -1;
    }

    return 0;
}
//the nuclear option.
int clear_audio_directory() {
    if (file_count == 1) {
        return 0;
    }
    //check if all files are zero
    // char* path_ = "/SD:/audio";
    // clear_audio_file(file_count);
    int res=0;
    for (uint8_t i = file_count ; i > 0; i-- ) {
        res = delete_audio_file(i);
        k_msleep(10);
        if (res) {
        printk("error on %d\n",i);
            return -1;
        }  
    }
     res = fs_unlink("/SD:/audio");
    if (res) {
        printk("error deleting file\n");
        return -1;
    }
    res = fs_mkdir("/SD:/audio");
    if (res) {
        printk("failed to make directory \n");
        return -1;
    }
    res = create_file("audio/a01.txt");
     if (res) {
        printk("failed to make new file in directory files\n");
        return -1;
    }
    printk("done with clearing\n");
    file_count = 1;  
    move_write_pointer(1);
    return 0;
    //if files are cleared, then directory is oked for destrcution.
}