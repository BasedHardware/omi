/* Host double of the public MCUboot image-header API; no bootloader implementation. */
#ifndef TEST_MCUBOOT_H
#define TEST_MCUBOOT_H
#include <stddef.h>
#include <stdint.h>
/* NCS 2.9.0 Zephyr v3.7.99-ncs2 public application API. */
struct mcuboot_img_sem_ver {
    uint8_t major;
    uint8_t minor;
    uint16_t revision;
    uint32_t build_num;
};
struct mcuboot_img_header {
    uint32_t mcuboot_version;
    union {
        struct {
            uint32_t image_size;
            struct mcuboot_img_sem_ver sem_ver;
        } v1;
    } h;
};
int boot_read_bank_header(uint8_t area_id, struct mcuboot_img_header *header, size_t header_size);
#endif
