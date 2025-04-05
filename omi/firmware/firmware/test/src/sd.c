#include <stdlib.h>
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/pm/device.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/logging/log.h>
#include <zephyr/fs/fs.h>
#include <zephyr/fs/ext2.h>
#include <zephyr/shell/shell.h>

#define DISK_DRIVE_NAME "SDMMC"
#define DISK_MOUNT_PT "/ext"

static const struct device *const sdcard = DEVICE_DT_GET(DT_NODELABEL(sdhc0));
static const struct gpio_dt_spec sd_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

static struct fs_mount_t mp = {
	.type = FS_EXT2,
	.flags = FS_MOUNT_FLAG_NO_FORMAT,
	.storage_dev = (void *)DISK_DRIVE_NAME,
	.mnt_point = "/ext",
};

#define FS_RET_OK 0

static const char *disk_mount_pt = DISK_MOUNT_PT;
static bool is_mounted = false;

static int sd_enable_power(bool enable)
{
	int ret;
	gpio_pin_configure_dt(&sd_en, GPIO_OUTPUT);
	if (enable)
	{
		ret = gpio_pin_set_dt(&sd_en, 1);
		pm_device_action_run(sdcard, PM_DEVICE_ACTION_RESUME);
	} 
	else
	{
		ret = pm_device_action_run(sdcard, PM_DEVICE_ACTION_SUSPEND);
		// gpio_pin_set_dt(&sd_en,	0);
	}
	return ret;
}

/* List dir entry by path
 *
 * @param path Absolute path to list
 *
 * @return Negative errno code on error, number of listed entries on
 *         success.
 */
static int cmd_lsdir(const struct shell *shell, size_t argc, char **argv)
{
	int res;
	struct fs_dir_t dirp;
	static struct fs_dirent entry;
	int count = 0;

	if (argc < 2)
	{
		return -ENOEXEC;
	}

	const char *path = argv[1];

	if (!is_mounted)
	{
		shell_error(shell, "Disk is not mounted.\n");
		return -ENOEXEC;
	}

	fs_dir_t_init(&dirp);

	/* Verify fs_opendir() */
	res = fs_opendir(&dirp, path);
	if (res)
	{
		shell_error(shell, "Error opening dir %s [%d]\n", path, res);
		return res;
	}

	shell_print(shell, "\nListing dir %s ...\n", path);
	for (;;)
	{
		/* Verify fs_readdir() */
		res = fs_readdir(&dirp, &entry);

		/* entry.name[0] == 0 means end-of-dir */
		if (res || entry.name[0] == 0)
		{
			break;
		}

		if (entry.type == FS_DIR_ENTRY_DIR)
		{
			shell_error(shell, "[DIR ] %s\n", entry.name);
		}
		else
		{
			shell_error(shell, "[FILE] %s (size = %zu)\n",
						entry.name, entry.size);
		}
		count++;
	}

	/* Verify fs_closedir() */
	fs_closedir(&dirp);
	if (res == 0)
	{
		res = count;
	}

	return res;
}

static int cmd_mount(const struct shell *shell, size_t argc, char **argv)
{
	int res;
	do
	{
		static const char *disk_pdrv = DISK_DRIVE_NAME;
		uint64_t memory_size_mb;
		uint32_t block_count;
		uint32_t block_size;

		res = sd_enable_power(true);
		if (res < 0) {
			shell_error(shell, "Failed to power on SD card (%d)", res);
			return res;
		}

		if (disk_access_ioctl(disk_pdrv,
							  DISK_IOCTL_CTRL_INIT, NULL) != 0)
		{
			shell_error(shell, "Storage init ERROR!");
			break;
		}

		if (disk_access_ioctl(disk_pdrv,
							  DISK_IOCTL_GET_SECTOR_COUNT, &block_count))
		{
			shell_error(shell, "Unable to get sector count");
			break;
		}
		shell_print(shell, "Block count %u", block_count);

		if (disk_access_ioctl(disk_pdrv,
							  DISK_IOCTL_GET_SECTOR_SIZE, &block_size))
		{
			shell_error(shell, "Unable to get sector size");
			break;
		}
		shell_print(shell, "Sector size %u\n", block_size);

		memory_size_mb = (uint64_t)block_count * block_size;
		shell_print(shell, "Memory Size(MB) %u\n", (uint32_t)(memory_size_mb >> 20));

		if (disk_access_ioctl(disk_pdrv,
							  DISK_IOCTL_CTRL_DEINIT, NULL) != 0)
		{
			shell_error(shell, "Storage deinit ERROR!");
			break;
		}
	} while (0);
	mp.mnt_point = disk_mount_pt;

	if (is_mounted)
	{
		shell_print(shell, "Disk already mounted.\n");
		return 0;
	}

	if (fs_mount(&mp) != FS_RET_OK)
	{
		shell_print(shell, "File system not found, creating file system...\n");
		res = fs_mkfs(FS_EXT2, (uintptr_t)mp.storage_dev, NULL, 0);
		if (res != 0)
		{
			shell_error(shell, "Error formatting filesystem [%d]", res);
			sd_enable_power(false);
			return res;
		}

		res = fs_mount(&mp);
		if (res != FS_RET_OK)
		{
			shell_print(shell, "Error mounting disk %d.\n", res);
			sd_enable_power(false);
			return res;
		}
	}

	shell_print(shell, "Disk mounted.\n");
	is_mounted = true;

	return res;
}

static int cmd_unmount(const struct shell *shell, size_t argc, char **argv)
{
	int res;
	res = fs_unmount(&mp);
	if (res == 0)
	{
		is_mounted = false;
		sd_enable_power(false);
		shell_print(shell, "Disk unmounted.\n");
	}
	else
	{
		shell_print(shell, "Error unmounting disk.\n");
	}
	return res;
}

static int cmd_write(const struct shell *shell, size_t argc, char **argv)
{
	int res;
	char path[256];

	if (!is_mounted)
	{
		shell_error(shell, "Disk is not mounted.\n");
		return -ENOEXEC;
	}
	if (argc < 3)
	{
		shell_error(shell, "Usage: write <file> <data>\n");
		return -ENOEXEC;
	}

	snprintf(path, sizeof(path), "%s/%s", DISK_MOUNT_PT, argv[1]);
	const char *data = argv[2];

	struct fs_file_t file_handle;
	fs_file_t_init(&file_handle);
	res = fs_open(&file_handle, path, FS_O_CREATE | FS_O_WRITE | FS_O_APPEND);
	if (res != 0) {
		shell_error(shell, "Error opening file %s\n", path);
		return res;
	}

	char *write_buffer;
	size_t data_len = strlen(data);
	write_buffer = k_malloc(data_len + 2); // +2 for \n and \0
	if (write_buffer == NULL) {
		fs_close(&file_handle);
		return -ENOMEM;
	}

	snprintf(write_buffer, data_len + 2, "%s\n", data);
	res = fs_write(&file_handle, write_buffer, strlen(write_buffer));
	k_free(write_buffer);
	fs_close(&file_handle);

	if (res >= 0) {
		shell_print(shell, "Write file %s success\n", path);
	}
	return res;
}

static int cmd_read(const struct shell *shell, size_t argc, char **argv)
{
	int res;
	char path[256];

	if (!is_mounted)
	{
		shell_error(shell, "Disk is not mounted.\n");
		return -ENOEXEC;
	}
	if (argc < 2)
	{
		shell_error(shell, "Usage: read <file>\n");
		return -ENOEXEC;
	}

	snprintf(path, sizeof(path), "%s/%s", DISK_MOUNT_PT, argv[1]);
	struct fs_file_t file;
	fs_file_t_init(&file);
	res = fs_open(&file, path, FS_O_READ);
	if (res != 0)
	{
		shell_error(shell, "Error opening file %s\n", path);
		return res;
	}

	char data[256];
	size_t bytes_read;
	while ((bytes_read = fs_read(&file, data, sizeof(data))) > 0)
	{
		shell_print(shell, "%s", data);
	}


	fs_close(&file);
	return 0;
}

static int cmd_rm(const struct shell *shell, size_t argc, char **argv)
{
	int res;
	char path[256];

	if (!is_mounted) {
		shell_error(shell, "Disk is not mounted.\n");
		return -ENOEXEC;
	}
	if (argc < 2) {
		shell_error(shell, "Usage: rm <file>\n");
		return -ENOEXEC;
	}

	snprintf(path, sizeof(path), "%s/%s", DISK_MOUNT_PT, argv[1]);
	res = fs_unlink(path);
	if (res != 0) {
		shell_error(shell, "Error removing file %s\n", path);
		return res;
	}
	shell_print(shell, "File %s removed\n", path);
	return 0;
}

static int cmd_readline(const struct shell *shell, size_t argc, char **argv)
{
	int res;
	char path[256];
	int line_number;

	if (!is_mounted) {
		shell_error(shell, "Disk is not mounted.\n");
		return -ENOEXEC;
	}
	if (argc < 3) {
		shell_error(shell, "Usage: readline <file> <line_number>\n");
		return -ENOEXEC;
	}

	snprintf(path, sizeof(path), "%s/%s", DISK_MOUNT_PT, argv[1]);
	line_number = atoi(argv[2]);

	struct fs_file_t file;
	fs_file_t_init(&file);
	res = fs_open(&file, path, FS_O_READ);
	if (res != 0) {
		shell_error(shell, "Error opening file %s\n", path);
		return res;
	}

	char buffer[256];
	int current_line = 1;
	char *pos = buffer;
	size_t bytes_read;

	while ((bytes_read = fs_read(&file, pos, 1)) > 0) {
		if (*pos == '\n') {
			if (current_line == line_number) {
				*pos = '\0';
				shell_print(shell, "Line %d: %s", line_number, buffer);
				fs_close(&file);
				return 0;
			}
			current_line++;
			pos = buffer;
		} else {
			pos++;
			if (pos - buffer >= sizeof(buffer) - 1) {
				shell_error(shell, "Line too long\n");
				fs_close(&file);
				return -ENOMEM;
			}
		}
	}

	fs_close(&file);
	if (current_line < line_number) {
		shell_error(shell, "Line number %d not found\n", line_number);
		return -EINVAL;
	}
	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_sd_cmds,
							   SHELL_CMD_ARG(ls, NULL, "list dir", cmd_lsdir, 2, 0),
							   SHELL_CMD_ARG(mount, NULL, "mount sd", cmd_mount, 1, 0),
							   SHELL_CMD_ARG(unmount, NULL, "unmount sd", cmd_unmount, 1, 0),
							   SHELL_CMD_ARG(write, NULL, "write to file", cmd_write, 3, 0),
							   SHELL_CMD_ARG(read, NULL, "read from file", cmd_read, 2, 0),
							   SHELL_CMD_ARG(rm, NULL, "remove file", cmd_rm, 2, 0),
							   SHELL_CMD_ARG(readline, NULL, "read specific line from file", cmd_readline, 3, 0),
							   SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(sd, &sub_sd_cmds, "sd", NULL);

int app_sd_init(void)
{
	shell_execute_cmd(NULL, "sd mount");
	shell_execute_cmd(NULL, "sd unmount");
	return 0;
}
