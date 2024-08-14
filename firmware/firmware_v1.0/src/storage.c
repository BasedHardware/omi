#include "storage.h"

static char current_path[MAX_PATH_SIZE];
const size_t written_max_count = 1000; // number of frames per file
static char file_path[MAX_PATH_SIZE];
static bool written_concat = true;
static size_t written_count = 0;
static uint16_t file_count = 0;
static bool verbose = true; // set to true if you want to enable verbose output
int notification_value = 0;


int init_storage(void)
{
    if (mount_sd_card())
    {
        if (verbose) printf("Failed to mount SD card\n");
        mounted = false;
        return -1;
    }

    if (verbose) printf("Successfully mounted SD card\n");
    mounted = true;
    return 0;    
}

ReadInfo get_current_file(void)
{
    ReadInfo readInfo;
    readInfo.ret = -1;

    ReadParams info = read_file("info.txt");

    if (info.ret < 0)
    {
        readInfo.ret = -1;
        return readInfo;
    }

    if (info.data != NULL)
    {
        uint8_t number;
        char *file_name = extract_after(info.data);
        extract_number(info.data, &number);
        free(file_name);
        readInfo.name = number;
        readInfo.ret = 0;
    }
    return readInfo;
}

ReadParams verify_info(void)
{
    ReadParams res;
    res.data = '\0';
    int status = -1;
    res.ret = 0;

    if (written_count == 0) 
    {
        res = read_file("info.txt");

        if (strlen(res.data) == 0)
        {
            create_file("audio/1.txt");
            write_info("audio/1.txt,status:NO");

            res.data = "audio/1.txt";
            res.ret = 0;
            
            return res;
        }

        if (res.ret == 0 && res.data != NULL)
        {   
            uint8_t number;
            process_file(res.data, current_path, &status);
            
            if (extract_number(current_path, &number) == 0) 
            {
                notification_value = number;
                file_count = number;
            }

            res.ret = status;
            res.data = current_path;
        }
    }
    return res;
}

int if_file_exist(void)
{
    ReadParams ret = verify_info();
    
    if (ret.ret >= 0 && !written_concat)
    {
        char file_info[MAX_DATA_SIZE];
        char *result = extract_after(current_path);
        if (result == NULL)
        {
            if(verbose) printf("Failed to extract after\n");
            return -1;
        }

        char *new_filename = generate_next_filename(result);

        free(result);

        if (new_filename != NULL)
        {
            snprintf(file_path, sizeof(file_path), "audio/%s", new_filename);
            snprintf(file_info, sizeof(file_info), "audio/%s,status:NO", new_filename);
            
            create_file(file_path);
            write_info(file_info);

            written_concat = true;
            
            free(new_filename);

            return 0;
        }
    }

    if (written_concat && ret.data != NULL)
    {
        strncpy(file_path, ret.data, sizeof(file_path) - 1);
        set_path(file_path);
    }

    return 0;
}

int save_audio_in_storage(uint8_t *buffer, size_t lenght)
{
    if (!mounted) return -2;

    int ret = if_file_exist();

    if (ret > -1)
    {
        bool endBuffer = false;
        
        if (written_count < written_max_count)
        {
            if (written_count == written_max_count - 1)
            {
                endBuffer = true;
            }
            int res = write_file(buffer, lenght, true, endBuffer);
            if(res > -1) written_count++;
        }

        if (written_count == written_max_count)
        {
            written_concat = false;
            written_count = 0;
        }

        return 0;
    }
    return -1;
}

char *generate_next_filename(const char *input_filename) 
{
    char result[MAX_PATH_SIZE];

    size_t input_length = strlen(input_filename);
    if (input_length < 5) 
    {
        return NULL;
    }

    char number_part[MAX_PATH_SIZE];
    strncpy(number_part, input_filename, input_length - 4);
    number_part[input_length - 4] = '\0';

    uint8_t number = (uint8_t)atoi(number_part);
    number++;

    snprintf(result, sizeof(result), "%d.txt", number);

    char *static_result = strdup(result);
    return static_result;
}

void process_file(const char *file, char *path, int *status) 
{
    if (file == NULL || path == NULL || status == NULL) 
    {
        return;
    }
    
    size_t trunc_length = 10;
    size_t file_len = strlen(file);

    if (file_len > trunc_length) 
    {
        if (file_len - trunc_length > 4)
        {
            strncpy(path, file, file_len - trunc_length);
            path[file_len - trunc_length] = '\0';
        } 
        else
        {
            path[0] = '\0';
        }
    } 
    else 
    {
        path[0] = '\0';
    }

    const char *status_str = file + file_len - 2;
    if (strcmp(status_str, "OK") == 0) 
    {
        *status = 0;
    } 
    else if (strcmp(status_str, "NO") == 0) 
    {
        *status = 1;
    } 
    else 
    {
        *status = -1;
    }
}

char *extract_after(const char *data) 
{
    if (data == NULL)
    {
        return NULL;
    }

    const char *prefix = "audio/";
    const char *prefix_position = strstr(data, prefix);
    char *result = NULL;

    if (prefix_position != NULL) 
    {
        prefix_position += strlen(prefix);

        size_t result_length = strlen(prefix_position) + 1;
        result = (char *)malloc(result_length);

        if (result != NULL) 
        {
            strcpy(result, prefix_position);
        }
    } 
    else 
    {
        result = (char *)malloc(1);
        if (result != NULL) 
        {
            result[0] = '\0';
        }
    }

    return result;
}

int extract_number(const char *input, uint8_t *number) 
{
    if (input == NULL || number == NULL) 
    {
        return -1;
    }

    const char *start = strchr(input, '/');
    if (start == NULL) 
    {
        return -1;
    }

    start++;

    const char *end = strchr(start, '.');
    if (end == NULL) 
    {
        return -1;
    }
    
    size_t length = end - start;
    char num_str[10];

    if (length >= sizeof(num_str)) 
    {
        return -1;
    }
    
    strncpy(num_str, start, length);
    num_str[length] = '\0';

    int value = atoi(num_str);
    if (value < 0 || value > 255) 
    {
        return -1;
    }
    
    *number = (uint8_t)value;
    return 0;
}