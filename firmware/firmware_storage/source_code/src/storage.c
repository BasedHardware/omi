#include "lib/sdcard/sdcard.h"
#include "storage.h"

static const uint8_t written_max_count = 3000; // number of frames per file
static bool written_concat = true;
static uint8_t written_count = 0;
static char file_path[2048];
static bool verbose = true; // set to true if you want to enable verbose output

static uint8_t file_count = 0;


int init_storage(void)
{
    if(mount_sd_card())
    {
        if(verbose)
        {
            printk("Failed to mount SD card\n");
        }
		return -1;
    }

    if(verbose)
    {
        printk("Successfully mounted SD card\n");
    }
    return 0;    
}

ReadParams verify_info(void)
{
    int status;
    char path[1024];

    ReadParams res = read_file("info.txt");

    if(res.ret < -1)
    {
        create_file("info.txt");
        return res;
    }

    process_file(res.data, path, &status);

    if(status > -1)
    {   
        uint8_t number;
        
        if (extract_number(path, &number) == 0) {
            file_count = number;
        }

        res.ret = status;
        res.data = path;
    }

    return res;
}

int if_file_exist(void)
{
    ReadParams ret = verify_info();

    printk("Ret.data: %s\n",ret.data);

    if(ret.ret < 0)
    {
        create_file("audio/0.txt");
        write_info("audio/0.txt,status:NO");
        return -1;    
    }

    if(written_concat)
    {
        set_path(file_path);
    }
    
    if(ret.ret > -1 && written_concat == false)
    {
        char result[512];
        char new_filename[512];
        static char file_info[2048];

        extract_after(ret.data, result);
        generate_next_filename(result, new_filename, sizeof(new_filename));
        snprintf(file_path, sizeof(file_path), "audio/%s", new_filename);
        snprintf(file_info, sizeof(file_info), "audio/%s,status:NO", new_filename);
        
        create_file(file_path);
        write_info(file_info);

        written_concat = true;

        return 0;
    }

    return 0;
}

int save_audio_in_storage(uint8_t *buffer, uint32_t lenght)
{
    int ret = if_file_exist();

    if(ret > -1)
    {
        bool endBuffer = false;
        
        if(written_count < written_max_count)
        {
            if(written_count == written_max_count - 1)
            {
                endBuffer = true;
            }

            WriteParams params = {buffer, lenght, endBuffer, true};

            write_file(params);

        }
	    
        written_count += 1;

        if(written_count == written_max_count+1)
        {
            char file_info[4096];
            snprintf(file_info, sizeof(file_info), "%s,status:OK", file_path);
            write_info(file_info);

            written_concat = false;
            written_count = 0;
        }

        return 0;
    }

    return -1;
}

//
// Auxiliar fucntions
//

void generate_next_filename(const char *current_filename, char *new_filename, size_t new_filename_size) {
    uint8_t number = file_count;
    file_count = number+1;

    snprintf(new_filename, new_filename_size, "%d.txt", number+1);
}

void process_file(const char *file, char *path, int *status) {
    if (file == NULL || path == NULL || status == NULL) {
        return;
    }
    
    size_t trunc_length = 10;
    size_t file_len = strlen(file);

    if (file_len > trunc_length) {
        if(file_len - trunc_length > 4)
        {
            strncpy(path, file, file_len - trunc_length);
            path[file_len - trunc_length] = '\0';
        } else
        {
            path[0] = '\0';
        }
    } else 
    {
        path[0] = '\0';
    }

    const char *status_str = file + file_len - 2;
    if (strcmp(status_str, "OK") == 0) {
        *status = 0;
    } else if (strcmp(status_str, "NO") == 0) {
        *status = 1;
    } else {
        *status = -1;
    }
}

void extract_after(const char *data, char *result) {
    const char *prefix = "audio/";
    const char *prefix_position = strstr(data, prefix);

    if (prefix_position != NULL) {
        prefix_position += strlen(prefix);

        strcpy(result, prefix_position);
    } else {
        result[0] = '\0';
    }
}

int extract_number(const char *input, uint8_t *number) {
    if (input == NULL || number == NULL) {
        return -1;
    }

    const char *start = strchr(input, '/');
    if (start == NULL) {
        return -1;
    }

    start++;

    const char *end = strchr(start, '.');
    if (end == NULL) {
        return -1;
    }
    
    size_t length = end - start;
    char num_str[10];
    if (length >= sizeof(num_str)) {
        return -1;
    }
    
    strncpy(num_str, start, length);
    num_str[length] = '\0';

    int value = atoi(num_str);
    if (value < 0 || value > 255) {
        return -1;
    }
    
    *number = (uint8_t)value;
    return 0;
}