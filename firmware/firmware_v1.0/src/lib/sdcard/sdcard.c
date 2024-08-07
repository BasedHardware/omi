#include <zephyr/kernel.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/logging/log.h>
#include <zephyr/device.h>
#include <zephyr/fs/fs.h>
#include "sdcard.h"

static char current_full_path[MAX_PATH_SIZE];
static const char *disk_mount_pt = "/SD:/";
static const bool verbose = false;
bool mounted = false;


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
	uint64_t memory_size_mb;
	uint32_t block_count;
	uint32_t block_size;

	if (disk_access_init("SD") != 0) 
    {
		if(verbose) printf("Storage init ERROR!");
		return -1;
	}

	if (disk_access_ioctl("SD", DISK_IOCTL_GET_SECTOR_COUNT, &block_count)) 
    {
		if(verbose) printf("Unable to get sector count");
		return -1;
	}

	if(verbose) printf("Block count %u", block_count);

	if (disk_access_ioctl("SD", DISK_IOCTL_GET_SECTOR_SIZE, &block_size)) 
    {
		if(verbose) printf("Unable to get sector size");
		return -1;
	}
	if(verbose) printf("Sector size %u\n", block_size);

	memory_size_mb = (uint64_t)block_count * block_size;
	if(verbose) printf("Memory Size(MB) %u\n", (uint32_t)(memory_size_mb >> 20));
	
	mp.mnt_point = "/SD:";

	int res = fs_mount(&mp);

	if (res == FR_OK) 
	{
		if(verbose) printf("Disk mounted.\n");
		fs_mkdir("/SD:/audio");
	} else 
	{
		if(verbose) printf("Failed to mount disk - trying one more time\n");
		res = fs_mount(&mp);
		if (res != FR_OK) {
			if(verbose) printf("Error mounting disk.\n");
			return -1;
		}
	}
	return 0;
}

FileInfo file_info(const char *path)
{
	FileInfo fileInfo;
	fileInfo.res = -1;
	fileInfo.size = 0;

	struct fs_dirent entry;

	int res = set_path(path);

	if(res > -1)
	{
		int ret = fs_stat(current_full_path, &entry);
		if(ret < 0)
		{
			fileInfo.res = -1;
			return	fileInfo;
		}
		printk("Name1: %s, size1: %zu\n",entry.name,entry.size);
		fileInfo.name = entry.name;
		fileInfo.size = entry.size;
		fileInfo.res = ret;
	}

	return fileInfo;
}

//
//  This functios is for delete files o paths.
//
int delete_file(const char *file_path)
{

    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, file_path);

	int ret = fs_unlink(current_full_path);

    return ret;
}

//
//   If you want to create a file "test.txt" in folder "test", file_path must be look like this "test/test.txt"
//
int create_file(const char *file_path){

    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, file_path);

    int ret = 0;
	struct fs_file_t data_filp;
	fs_file_t_init(&data_filp);

	ret = fs_unlink(current_full_path);

	ret = fs_open(&data_filp, current_full_path, FS_O_WRITE | FS_O_CREATE);

	if (ret) 
	{
		if(verbose) printf("%s -- failed to create file (err = %d)\n", __func__, ret);
		return -2;
	} else 
	{
		if(verbose) printf("%s - successfully created file\n", __func__);
	}

    fs_close(&data_filp);

    return 0;
}

//
//   This function is only for uint8_t data input
//
int write_file(uint8_t *data, size_t lenght, bool concat, bool endBuffer)
{
	size_t buffer_length = lenght;
    struct fs_file_t data_filp;
	int ret = 0;

	fs_file_t_init(&data_filp);

	char *inner_data = uint8_array_to_string(data, buffer_length);

	char *formatted = format_values(inner_data);

	if (formatted == NULL) return -1;
	else strcpy(inner_data, formatted);
	
	if (!endBuffer) 
	{
		strcat(inner_data, ",");
	}

    if(concat)
    {
        ret = fs_open(&data_filp, current_full_path, FS_O_WRITE | FS_O_APPEND);
       	if(ret < -1)
		{
			ret = fs_open(&data_filp, current_full_path, FS_O_WRITE | FS_O_CREATE);
			if (ret > -1 && verbose) printf("File wrote successfully\n");
		}
    } else
    {
        ret = fs_open(&data_filp, current_full_path, FS_O_WRITE | FS_O_CREATE);
        if(ret < 0)
        {
            if(verbose) printf("Error creating and writing file\n");
            return -1;
        }
        if(verbose) printf("File wrote successfully\n");
    }
	
    if (formatted != NULL) {
		ret = fs_write(&data_filp, inner_data, strlen(inner_data));
    }
   	free(inner_data);
    fs_close(&data_filp);

    return 0;
}

//
//	This function is only for write in info.txt
//
int write_info(const char *data)
{
    int ret = 0;
    struct fs_file_t data_filp;
	fs_file_t_init(&data_filp);

	ret = fs_unlink("/SD:/info.txt");

   	ret = fs_open(&data_filp, "/SD:/info.txt", FS_O_WRITE | FS_O_CREATE);
    if(ret)
    {
        if(verbose) printf("Error creating and writing file\n");
        return -1;
    }

    if(verbose) printf("File wrote successfully\n");

	ret = fs_write(&data_filp, data, strlen(data));

	if(ret < 0)
	{
		return -1;
	}
	
    fs_close(&data_filp);

    return 0;
}

ReadParams read_file(const char *file_path)
{
	ReadParams readParams;
	readParams.ret = 0;
    char boot_count[MAX_DATA_SIZE];
	struct fs_file_t file;
	int rc;

	int ret = set_path(file_path);
	
	if(ret)
	{
		readParams.ret = -1;
		return readParams;
	}
	
	fs_file_t_init(&file);
	
	rc = fs_open(&file, current_full_path, FS_O_READ | FS_O_RDWR);
	
	if (rc < 0)
	{
		if(verbose) printf("FAIL: open %s: %d\n", current_full_path, rc);
		readParams.ret = rc;
		return readParams;
	}
	
	rc = fs_read(&file, &boot_count, sizeof(boot_count));
	
	if (rc < 0)
	{
		if(verbose) printf("FAIL: read %s: [rd:%d]", current_full_path, rc);
	}

    boot_count[rc] = 0;

	readParams.data = boot_count;

	fs_close(&file);

	return readParams;
}

ReadParams read_file_fragmment(const char *file_path, size_t buffer_size, size_t pointer)
{
	ReadParams readParams;
	readParams.ret = -1;

    char boot_count[buffer_size];
	struct fs_file_t file;
	int rc;

	int ret = set_path(file_path);

	if(ret)
	{
		readParams.ret = -1;

		return readParams;
	}

	fs_file_t_init(&file);

	rc = fs_open(&file, current_full_path, FS_O_READ | FS_O_RDWR);

	if (rc < 0) 
	{
		if(verbose) printf("FAIL: open %s: %d", current_full_path, rc);

		readParams.ret = rc;

		return readParams;
	}
	
	int rs = fs_seek(&file, pointer, FS_SEEK_SET);

	if(rs > -1)
	{
		rc = fs_read(&file, &boot_count, sizeof(boot_count));

		if (rc < 0)
		{
			if(verbose) printf("FAIL: read %s: [rd:%d]", current_full_path, rc);

			readParams.ret = -1;

			return readParams;
		}

		boot_count[rc] = 0;

		readParams.data = boot_count;
		readParams.ret = rc;
	}

	fs_close(&file);

	return readParams;
}

//
//	Type convertions
//

// function to convert uint8_t to char type
char* uint8_array_to_string(const uint8_t *array, size_t size) {

    size_t buffer_size = size * 4 + 1;
    char *result = (char *)malloc(buffer_size);

    if (result == NULL) {
        perror("Unable to allocate memory");
        return NULL;
    }

    char *ptr = result;
    for (size_t i = 0; i < size; i++) {
        int written = snprintf(ptr, buffer_size - (ptr - result), "%u", array[i]);
        if (written < 0) {
            free(result);
            perror("Error formatting the string");
            return NULL;
        }
        ptr += written;

        if (i < size - 1) {
            snprintf(ptr, buffer_size - (ptr - result), ",");
            ptr += 1;
        }
    }

    *ptr = '\0';

    return result;
}

// function to convert char to uint8_t type
uint8_t* convert_to_uint8_array(const char *str, size_t *out_size) {
    size_t count = 0;
    
    char buffer[MAX_INPUT_SIZE];
    strncpy(buffer, str, sizeof(buffer));
    buffer[sizeof(buffer) - 1] = '\0';

    char* token = strtok(buffer, ",");
    while (token != NULL) {
        count++;
        token = strtok(NULL, ",");
    }

    uint8_t* array = (uint8_t*)malloc(count * sizeof(uint8_t));
    if (array == NULL) {
        perror("Failed to allocate memory");
        exit(EXIT_FAILURE);
    }

    strncpy(buffer, str, sizeof(buffer));
    buffer[sizeof(buffer) - 1] = '\0';

    size_t index = 0;
    token = strtok(buffer, ",");
    while (token != NULL) {
        int value = atoi(token);
        if (value < 0 || value > 255) {
            fprintf(stderr, "Value %d is out of range for uint8_t\n", value);
            free(array);
            return NULL;
        }
        array[index++] = (uint8_t)value;
        token = strtok(NULL, ",");
    }

    if (out_size != NULL) {
        *out_size = count;
    }

    return array;
}

char* format_values(const char *input) 
{
    static char output[MAX_OUTPUT_SIZE];
    size_t output_length = 0;
    const char *start = input;
    char formatted[MAX_DIGITS + 2];

    output[0] = '\0';

    while (*start != '\0') 
    {
        const char *end = strchr(start, ',');
        if (end == NULL) 
        {
            end = start + strlen(start);
        }

        size_t len = end - start;
        char temp[MAX_DIGITS + 1];
        strncpy(temp, start, len);
        temp[len] = '\0';

        int number = atoi(temp);
        snprintf(formatted, sizeof(formatted), "%03d", number);

        if (output_length + strlen(formatted) + 1 < MAX_OUTPUT_SIZE) 
        {
            if (output_length > 0) 
            {
                output[output_length++] = DELIMITER;
            }
            strcpy(output + output_length, formatted);
            output_length += strlen(formatted);
        }

        if (*end == '\0') 
        {
            break;
        }

        start = end + 1;
    }

    return output;
}

char* revert_format(const char *formatted_input) 
{
    char temp[MAX_INPUT_SIZE];
    size_t output_length = 0;
    char *output;
    char *token;

    output = (char *)malloc(MAX_OUTPUT_SIZE * sizeof(char));
    if (output == NULL) 
	{
        if(verbose) fprintf(stderr, "Memory allocation failed\n");
        return NULL;
    }

    output[0] = '\0';

    strncpy(temp, formatted_input, MAX_INPUT_SIZE);

    token = strtok(temp, ",");
    
    while (token != NULL) {
        char original[MAX_DIGITS + 1];
        size_t length = strlen(token);
        size_t start_index = 0;

        while (start_index < length && token[start_index] == '0') 
		{
            start_index++;
        }

        if (start_index == length) 
		{
            start_index--;
        }

        snprintf(original, sizeof(original), "%s", token + start_index);

        if (output_length + strlen(original) + 1 < MAX_OUTPUT_SIZE) 
		{
            if (output_length > 0) 
			{
                output[output_length++] = DELIMITER;
            }
            strcpy(output + output_length, original);
            output_length += strlen(original);
        }
        token = strtok(NULL, ",");
    }

    return output;
}