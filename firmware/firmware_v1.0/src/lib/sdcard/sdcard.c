#include "sdcard.h"

static const char *disk_mount_pt0 = "/SD:";
static const char *disk_mount_pt = "/SD:/";
static const bool verbose = false;
char current_full_path[2048];
char current_path[2048];


static FATFS fat_fs;
static struct fs_mount_t mp = {
	.type = FS_FATFS,
	.fs_data = &fat_fs,
};

int set_path(const char *file_path)
{
	int ret = snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, file_path);
	if(!ret)
	{
		return -1;
	}
	return 0;
}

int mount_sd_card(void)
{
	static const char *disk_pdrv = "SD";
	uint64_t memory_size_mb;
	uint32_t block_count;
	uint32_t block_size;

	if (disk_access_init(disk_pdrv) != 0) 
    {
		printk("Storage init ERROR!");
		return -1;
	}

	if (disk_access_ioctl(disk_pdrv, DISK_IOCTL_GET_SECTOR_COUNT, &block_count)) 
    {
		printk("Unable to get sector count");
		return -1;
	}

	printk("Block count %u", block_count);

	if (disk_access_ioctl(disk_pdrv, DISK_IOCTL_GET_SECTOR_SIZE, &block_size)) 
    {
		printk("Unable to get sector size");
		return -1;
	}
	printk("Sector size %u\n", block_size);

	memory_size_mb = (uint64_t)block_count * block_size;
	printk("Memory Size(MB) %u\n", (uint32_t)(memory_size_mb >> 20));
	
	mp.mnt_point = disk_mount_pt0;

	int res = fs_mount(&mp);

	if (res == FR_OK) {
		printk("Disk mounted.\n");
		lsdir(disk_mount_pt0);
	} else {
		printk("Failed to mount disk - trying one more time\n");
		res = fs_mount(&mp);
		if (res != FR_OK) {
			printk("Error mounting disk.\n");
			return -1;
		}
	}

	return 0;
}

Result lsdir(const char *path)
{
	Result result;
	result.res = 0;

	int res;
	struct fs_dir_t dirp;
	static struct fs_dirent entry;

	fs_dir_t_init(&dirp);

	res = fs_opendir(&dirp, path);
	if (res) {
		printk("Error opening dir %s [%d]\n", path, res);
		result.files = "c";
		result.res = res;
		return result;
	}

	printk("\nListing dir %s ...\n", path);

	for (;;) {
		res = fs_readdir(&dirp, &entry);

		if (res || entry.name[0] == 0) {
			break;
		}

		if (entry.type == FS_DIR_ENTRY_DIR) {
			printk("[DIR ] %s\n", entry.name);

			snprintf(current_path, sizeof(current_path), "%s%s", disk_mount_pt, entry.name);

			lsdir(current_path);

			result.files = entry.name;
			result.res = 0;
			
		} else 
		{
			printk("[FILE] %s (size = %zu)\n", entry.name, entry.size);
			result.files = entry.name;
			result.res = 0;
		}
	}

	fs_closedir(&dirp);

	return result;
}

/*
*   If you want to create a file "test.txt" in folder "test", file_path must be look like this "test/test.txt"
*/
int create_file(const char *file_path){

    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, file_path);

    int ret = 0;
	struct fs_file_t data_filp;
	fs_file_t_init(&data_filp);

	ret = fs_unlink(current_full_path);

	ret = fs_open(&data_filp, current_full_path, FS_O_WRITE | FS_O_CREATE);

	if (ret) {
        if(verbose)
        {
		    printk("%s -- failed to create file (err = %d)\n", __func__, ret);
        }
		return -2;
	} else {
        if(verbose)
        {
		    printk("%s - successfully created file\n", __func__);
        }
	}

    fs_close(&data_filp);

    return 0;
}

int write_file(WriteParams params)
{
	size_t buffer_length = params.lenght;
    char data[DATA_SIZE];

	printk("Data lenght: %d\n",params.lenght);

    uint8_buffer_to_char_data(params.data, buffer_length, data, sizeof(data));

	if (!params.endBuffer) {
        if (strlen(data) < (sizeof(data) - 1)) {
            strcat(data, ",");
        } else {
            printk("Buffer overflow error: Not enough space to add comma.\n");
            return -1;
        }
    }
	
    int ret = 0;
    struct fs_file_t data_filp;
	fs_file_t_init(&data_filp);

    if(params.concat)
    {
        ret = fs_open(&data_filp, current_full_path, FS_O_WRITE | FS_O_APPEND);
        if(ret)
        {
            if(verbose)
            {
                printk("Error creating and writing file\n");
            }
            return -1;
        }
        if(verbose)
        {
            printk("File wrote successfully\n");
        }
    }
    else
    {
        ret = fs_open(&data_filp, current_full_path, FS_O_WRITE | FS_O_CREATE);
        if(ret)
        {
            if(verbose)
            {
                printk("Error creating and writing file\n");
            }
            return -1;
        }
        if(verbose)
        {
            printk("File wrote successfully\n");
        }
    }

	ret = fs_write(&data_filp, data, strlen(data));
	
    fs_close(&data_filp);

    return 0;
}

int write_info(const char *data)
{
    int ret = 0;
    struct fs_file_t data_filp;
	fs_file_t_init(&data_filp);

	ret = fs_unlink("/SD:/info.txt");

   	ret = fs_open(&data_filp, "/SD:/info.txt", FS_O_WRITE | FS_O_CREATE);
    if(ret)
    {
        if(verbose)
        {
            printk("Error creating and writing file\n");
        }
        return -1;
    }

    if(verbose)
    {
        printk("File wrote successfully\n");
    }

	ret = fs_write(&data_filp, data, strlen(data));
	
    fs_close(&data_filp);

    return 0;
}

ReadParams read_file(const char *file_path)
{
	ReadParams readParams;
	readParams.ret = 0;

    char boot_count[1000];
	struct fs_file_t file;
	int rc;

	int ret = set_path(file_path);

	if(ret)
	{
		readParams.data = "";
		readParams.ret = -1;
		return readParams;

	}

	fs_file_t_init(&file);

	rc = fs_open(&file, current_full_path, FS_O_READ | FS_O_RDWR);

	if (rc < 0) {
        if(verbose)
        {
		    printk("FAIL: open %s: %d", current_full_path, rc);
		}
        readParams.data = "";
		readParams.ret = rc;
		return readParams;
	}

	rc = fs_read(&file, &boot_count, sizeof(boot_count));

	if (rc < 0) {
        if(verbose)
        {
		    printk("FAIL: read %s: [rd:%d]", current_full_path, rc);
		}
	}

    boot_count[rc] = 0;

	readParams.data = boot_count;

    if(verbose)
    {
        printk("Data read:\"%s\"\n\n", boot_count);
    }

	fs_close(&file);

	return readParams;
}

//
//	Type convertions
//

void uint8_buffer_to_char_data(const uint8_t *buffer, size_t length, char *data, size_t data_size) {
    data[0] = '\0';

    size_t written = 0;

    for (size_t i = 0; i < length; i++) {
        int n = snprintf(data + written, data_size - written, "%u", buffer[i]);

        if (n < 0 || (size_t)n >= data_size - written) {
            break;
        }

        written += (size_t)n;

        if (i < length - 1) {
            n = snprintf(data + written, data_size - written, ",");
            if (n < 0 || (size_t)n >= data_size - written) {
                break;
            }
            written += (size_t)n;
        }
    }
}