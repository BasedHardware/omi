#ifndef Z_STUB_DISK_ACCESS_H
#define Z_STUB_DISK_ACCESS_H

#include <stdint.h>

#define DISK_IOCTL_CTRL_SYNC 1
#define DISK_IOCTL_GET_SECTOR_COUNT 2
#define DISK_IOCTL_GET_SECTOR_SIZE 3
#define DISK_IOCTL_CTRL_INIT 4
#define DISK_IOCTL_CTRL_DEINIT 5

int disk_access_read(const char *pdrv, uint8_t *data_buf, uint32_t start_sector, uint32_t num_sector);
int disk_access_write(const char *pdrv, const uint8_t *data_buf, uint32_t start_sector, uint32_t num_sector);
int disk_access_ioctl(const char *pdrv, uint8_t cmd, void *buff);

#endif
