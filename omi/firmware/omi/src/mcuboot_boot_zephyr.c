/*
 * Copyright (c) 2012-2014 Wind River Systems, Inc.
 * Copyright (c) 2020 Arm Limited
 * Copyright (c) 2021-2023 Nordic Semiconductor ASA
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <assert.h>
#include <zephyr/kernel.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/__assert.h>
#include <zephyr/drivers/flash.h>
#include <zephyr/drivers/timer/system_timer.h>
#include <zephyr/usb/usb_device.h>
#include <soc.h>
#include <zephyr/linker/linker-defs.h>

// OMI
#include <zephyr/storage/disk_access.h>
#include <zephyr/pm/device.h>
#define DISK_DRIVE_NAME "SDMMC"

#if defined(CONFIG_BOOT_DISABLE_CACHES)
#include <zephyr/cache.h>
#endif

#if defined(CONFIG_ARM)
#include <cmsis_core.h>
#endif

#include "io/io.h"
#include "target.h"

#include "bootutil/bootutil_log.h"
#include "bootutil/image.h"
#include "bootutil/bootutil.h"
#include "bootutil/fault_injection_hardening.h"
#include "bootutil/mcuboot_status.h"
#include "flash_map_backend/flash_map_backend.h"

/* Check if Espressif target is supported */
#ifdef CONFIG_SOC_FAMILY_ESPRESSIF_ESP32

#include <bootloader_init.h>
#include <esp_image_loader.h>

#define IMAGE_INDEX_0   0
#define IMAGE_INDEX_1   1

#define PRIMARY_SLOT    0
#define SECONDARY_SLOT  1

#define IMAGE0_PRIMARY_START_ADDRESS \
          DT_PROP_BY_IDX(DT_NODE_BY_FIXED_PARTITION_LABEL(image_0), reg, 0)
#define IMAGE0_PRIMARY_SIZE \
          DT_PROP_BY_IDX(DT_NODE_BY_FIXED_PARTITION_LABEL(image_0), reg, 1)

#define IMAGE1_PRIMARY_START_ADDRESS \
          DT_PROP_BY_IDX(DT_NODE_BY_FIXED_PARTITION_LABEL(image_1), reg, 0)
#define IMAGE1_PRIMARY_SIZE \
          DT_PROP_BY_IDX(DT_NODE_BY_FIXED_PARTITION_LABEL(image_1), reg, 1)

#endif /* CONFIG_SOC_FAMILY_ESPRESSIF_ESP32 */

#ifdef CONFIG_FW_INFO
#include <fw_info.h>
#endif

#ifdef CONFIG_MCUBOOT_SERIAL
#include "boot_serial/boot_serial.h"
#include "serial_adapter/serial_adapter.h"

const struct boot_uart_funcs boot_funcs = {
    .read = console_read,
    .write = console_write
};
#endif

#if defined(CONFIG_BOOT_USB_DFU_WAIT) || defined(CONFIG_BOOT_USB_DFU_GPIO)
#include <zephyr/usb/class/usb_dfu.h>
#endif

#if CONFIG_MCUBOOT_CLEANUP_ARM_CORE
#include <arm_cleanup.h>
#endif

#if defined(CONFIG_SOC_NRF5340_CPUAPP) && defined(PM_CPUNET_B0N_ADDRESS)
#include <dfu/pcd.h>
#endif

/* CONFIG_LOG_MINIMAL is the legacy Kconfig property,
 * replaced by CONFIG_LOG_MODE_MINIMAL.
 */
#if (defined(CONFIG_LOG_MODE_MINIMAL) || defined(CONFIG_LOG_MINIMAL))
#define ZEPHYR_LOG_MODE_MINIMAL 1
#endif

/* CONFIG_LOG_IMMEDIATE is the legacy Kconfig property,
 * replaced by CONFIG_LOG_MODE_IMMEDIATE.
 */
#if (defined(CONFIG_LOG_MODE_IMMEDIATE) || defined(CONFIG_LOG_IMMEDIATE))
#define ZEPHYR_LOG_MODE_IMMEDIATE 1
#endif

#if defined(CONFIG_LOG) && !defined(ZEPHYR_LOG_MODE_IMMEDIATE) && \
    !defined(ZEPHYR_LOG_MODE_MINIMAL)
#ifdef CONFIG_LOG_PROCESS_THREAD
#warning "The log internal thread for log processing can't transfer the log"\
         "well for MCUBoot."
#else
#include <zephyr/logging/log_ctrl.h>

#define BOOT_LOG_PROCESSING_INTERVAL K_MSEC(30) /* [ms] */

/* log are processing in custom routine */
K_THREAD_STACK_DEFINE(boot_log_stack, CONFIG_MCUBOOT_LOG_THREAD_STACK_SIZE);
struct k_thread boot_log_thread;
volatile bool boot_log_stop = false;
K_SEM_DEFINE(boot_log_sem, 1, 1);

/* log processing need to be initalized by the application */
#define ZEPHYR_BOOT_LOG_START() zephyr_boot_log_start()
#define ZEPHYR_BOOT_LOG_STOP() zephyr_boot_log_stop()
#endif /* CONFIG_LOG_PROCESS_THREAD */
#else
/* synchronous log mode doesn't need to be initalized by the application */
#define ZEPHYR_BOOT_LOG_START() do { } while (false)
#define ZEPHYR_BOOT_LOG_STOP() do { } while (false)
#endif /* defined(CONFIG_LOG) && !defined(ZEPHYR_LOG_MODE_IMMEDIATE) && \
        * !defined(ZEPHYR_LOG_MODE_MINIMAL)
	*/

#if USE_PARTITION_MANAGER && CONFIG_FPROTECT
#include <fprotect.h>
#include <pm_config.h>
#endif

#if CONFIG_MCUBOOT_NRF_CLEANUP_PERIPHERAL || CONFIG_MCUBOOT_NRF_CLEANUP_NONSECURE_RAM
#include <nrf_cleanup.h>
#endif

BOOT_LOG_MODULE_REGISTER(mcuboot);

void os_heap_init(void);

#if defined(CONFIG_ARM)

#ifdef CONFIG_SW_VECTOR_RELAY
extern void *_vector_table_pointer;
#endif

struct arm_vector_table {
    uint32_t msp;
    uint32_t reset;
};

static void do_boot(struct boot_rsp *rsp)
{
    struct arm_vector_table *vt;

    /* The beginning of the image is the ARM vector table, containing
     * the initial stack pointer address and the reset vector
     * consecutively. Manually set the stack pointer and jump into the
     * reset vector
     */
#ifdef CONFIG_BOOT_RAM_LOAD
    /* Get ram address for image */
    vt = (struct arm_vector_table *)(rsp->br_hdr->ih_load_addr + rsp->br_hdr->ih_hdr_size);
#else
    uintptr_t flash_base;
    int rc;

    /* Jump to flash image */
    rc = flash_device_base(rsp->br_flash_dev_id, &flash_base);
    assert(rc == 0);

    vt = (struct arm_vector_table *)(flash_base +
                                     rsp->br_image_off +
                                     rsp->br_hdr->ih_hdr_size);
#endif

    if (IS_ENABLED(CONFIG_SYSTEM_TIMER_HAS_DISABLE_SUPPORT)) {
        sys_clock_disable();
    }

#ifdef CONFIG_USB_DEVICE_STACK
    /* Disable the USB to prevent it from firing interrupts */
    usb_disable();
#endif

#if defined(CONFIG_FW_INFO) && !defined(CONFIG_EXT_API_PROVIDE_EXT_API_UNUSED)
    uintptr_t fw_start_addr;

    rc = flash_device_base(rsp->br_flash_dev_id, &fw_start_addr);
    assert(rc == 0);

    fw_start_addr += rsp->br_image_off + rsp->br_hdr->ih_hdr_size;

    const struct fw_info *firmware_info = fw_info_find(fw_start_addr);
    bool provided = fw_info_ext_api_provide(firmware_info, true);

#ifdef PM_S0_ADDRESS
    /* Only fail if the immutable bootloader is present. */
    if (!provided) {
	if (firmware_info == NULL) {
            BOOT_LOG_WRN("Unable to find firmware info structure in %p", vt);
	}
        BOOT_LOG_ERR("Failed to provide EXT_APIs to %p", vt);
    }
#endif
#endif
#if CONFIG_MCUBOOT_NRF_CLEANUP_PERIPHERAL
    nrf_cleanup_peripheral();
#endif
#if CONFIG_MCUBOOT_NRF_CLEANUP_NONSECURE_RAM && defined(PM_SRAM_NONSECURE_NAME)
    nrf_cleanup_ns_ram();
#endif
#if CONFIG_MCUBOOT_CLEANUP_ARM_CORE
    cleanup_arm_nvic(); /* cleanup NVIC registers */

#if defined(CONFIG_BOOT_DISABLE_CACHES)
    /* Flush and disable instruction/data caches before chain-loading the application */
    (void)sys_cache_instr_flush_all();
    (void)sys_cache_data_flush_all();
    sys_cache_instr_disable();
    sys_cache_data_disable();
#endif

#if CONFIG_CPU_HAS_ARM_MPU || CONFIG_CPU_HAS_NXP_MPU
    z_arm_clear_arm_mpu_config();
#endif

#if defined(CONFIG_BUILTIN_STACK_GUARD) && \
    defined(CONFIG_CPU_CORTEX_M_HAS_SPLIM)
    /* Reset limit registers to avoid inflicting stack overflow on image
     * being booted.
     */
    __set_PSPLIM(0);
    __set_MSPLIM(0);
#endif

#else
    irq_lock();
#endif /* CONFIG_MCUBOOT_CLEANUP_ARM_CORE */

#ifdef CONFIG_BOOT_INTR_VEC_RELOC
#if defined(CONFIG_SW_VECTOR_RELAY)
    _vector_table_pointer = vt;
#ifdef CONFIG_CPU_CORTEX_M_HAS_VTOR
    SCB->VTOR = (uint32_t)__vector_relay_table;
#endif
#elif defined(CONFIG_CPU_CORTEX_M_HAS_VTOR)
    SCB->VTOR = (uint32_t)vt;
#endif /* CONFIG_SW_VECTOR_RELAY */
#else /* CONFIG_BOOT_INTR_VEC_RELOC */
#if defined(CONFIG_CPU_CORTEX_M_HAS_VTOR) && defined(CONFIG_SW_VECTOR_RELAY)
    _vector_table_pointer = _vector_start;
    SCB->VTOR = (uint32_t)__vector_relay_table;
#endif
#endif /* CONFIG_BOOT_INTR_VEC_RELOC */

    __set_MSP(vt->msp);
#if CONFIG_MCUBOOT_CLEANUP_ARM_CORE
    __set_CONTROL(0x00); /* application will configures core on its own */
    __ISB();
#endif
#if CONFIG_MCUBOOT_CLEANUP_RAM
    __asm__ volatile (
        /* vt->reset -> r0 */
        "   mov     r0, %0\n"
        /* base to write -> r1 */
        "   mov     r1, %1\n"
        /* size to write -> r2 */
        "   mov     r2, %2\n"
        /* value to write -> r3 */
        "   mov     r3, %3\n"
        "clear:\n"
        "   str     r3, [r1]\n"
        "   add     r1, r1, #4\n"
        "   sub     r2, r2, #4\n"
        "   cbz     r2, out\n"
        "   b       clear\n"
        "out:\n"
        "   dsb\n"
        /* jump to reset vector of an app */
        "   bx      r0\n"
        :
        : "r" (vt->reset), "i" (CONFIG_SRAM_BASE_ADDRESS),
          "i" (CONFIG_SRAM_SIZE * 1024), "i" (0)
        : "r0", "r1", "r2", "r3", "memory"
    );
#else
    ((void (*)(void))vt->reset)();
#endif
}

#elif defined(CONFIG_XTENSA) || defined(CONFIG_RISCV)

#ifndef CONFIG_SOC_FAMILY_ESPRESSIF_ESP32

#define SRAM_BASE_ADDRESS	0xBE030000

static void copy_img_to_SRAM(int slot, unsigned int hdr_offset)
{
    const struct flash_area *fap;
    int area_id;
    int rc;
    unsigned char *dst = (unsigned char *)(SRAM_BASE_ADDRESS + hdr_offset);

    BOOT_LOG_INF("Copying image to SRAM");

    area_id = flash_area_id_from_image_slot(slot);
    rc = flash_area_open(area_id, &fap);
    if (rc != 0) {
        BOOT_LOG_ERR("flash_area_open failed with %d\n", rc);
        goto done;
    }

    rc = flash_area_read(fap, hdr_offset, dst, fap->fa_size - hdr_offset);
    if (rc != 0) {
        BOOT_LOG_ERR("flash_area_read failed with %d\n", rc);
        goto done;
    }

done:
    flash_area_close(fap);
}
#endif /* !CONFIG_SOC_FAMILY_ESPRESSIF_ESP32 */

/* Entry point (.ResetVector) is at the very beginning of the image.
 * Simply copy the image to a suitable location and jump there.
 */
static void do_boot(struct boot_rsp *rsp)
{
#ifndef CONFIG_SOC_FAMILY_ESPRESSIF_ESP32
    void *start;
#endif /* CONFIG_SOC_FAMILY_ESPRESSIF_ESP32 */

    BOOT_LOG_INF("br_image_off = 0x%x\n", rsp->br_image_off);
    BOOT_LOG_INF("ih_hdr_size = 0x%x\n", rsp->br_hdr->ih_hdr_size);

#ifdef CONFIG_SOC_FAMILY_ESPRESSIF_ESP32
    int slot = (rsp->br_image_off == IMAGE0_PRIMARY_START_ADDRESS) ?
                PRIMARY_SLOT : SECONDARY_SLOT;
    /* Load memory segments and start from entry point */
    start_cpu0_image(IMAGE_INDEX_0, slot, rsp->br_hdr->ih_hdr_size);
#else
    /* Copy from the flash to HP SRAM */
    copy_img_to_SRAM(0, rsp->br_hdr->ih_hdr_size);

    /* Jump to entry point */
    start = (void *)(SRAM_BASE_ADDRESS + rsp->br_hdr->ih_hdr_size);
    ((void (*)(void))start)();
#endif /* CONFIG_SOC_FAMILY_ESPRESSIF_ESP32 */
}

#else
/* Default: Assume entry point is at the very beginning of the image. Simply
 * lock interrupts and jump there. This is the right thing to do for X86 and
 * possibly other platforms.
 */
static void do_boot(struct boot_rsp *rsp)
{
    void *start;

#if defined(MCUBOOT_RAM_LOAD)
    start = (void *)(rsp->br_hdr->ih_load_addr + rsp->br_hdr->ih_hdr_size);
#else
    uintptr_t flash_base;
    int rc;

    rc = flash_device_base(rsp->br_flash_dev_id, &flash_base);
    assert(rc == 0);

    start = (void *)(flash_base + rsp->br_image_off +
                     rsp->br_hdr->ih_hdr_size);
#endif

    /* Lock interrupts and dive into the entry point */
    irq_lock();
    ((void (*)(void))start)();
}
#endif

#if defined(CONFIG_LOG) && !defined(ZEPHYR_LOG_MODE_IMMEDIATE) && \
    !defined(CONFIG_LOG_PROCESS_THREAD) && !defined(ZEPHYR_LOG_MODE_MINIMAL)
/* The log internal thread for log processing can't transfer log well as has too
 * low priority.
 * Dedicated thread for log processing below uses highest application
 * priority. This allows to transmit all logs without adding k_sleep/k_yield
 * anywhere else int the code.
 */

/* most simple log processing theread */
void boot_log_thread_func(void *dummy1, void *dummy2, void *dummy3)
{
    (void)dummy1;
    (void)dummy2;
    (void)dummy3;

    log_init();

    while (1) {
#if defined(CONFIG_LOG1) || defined(CONFIG_LOG2)
        /* support Zephyr legacy logging implementation before commit c5f2cde */
        if (log_process(false) == false) {
#else
        if (log_process() == false) {
#endif
            if (boot_log_stop) {
                break;
            }
            k_sleep(BOOT_LOG_PROCESSING_INTERVAL);
        }
    }

    k_sem_give(&boot_log_sem);
}

void zephyr_boot_log_start(void)
{
    /* start logging thread */
    k_thread_create(&boot_log_thread, boot_log_stack,
                    K_THREAD_STACK_SIZEOF(boot_log_stack),
                    boot_log_thread_func, NULL, NULL, NULL,
                    K_HIGHEST_APPLICATION_THREAD_PRIO, 0,
                    BOOT_LOG_PROCESSING_INTERVAL);

    k_thread_name_set(&boot_log_thread, "logging");
}

void zephyr_boot_log_stop(void)
{
    boot_log_stop = true;

    /* wait until log procesing thread expired
     * This can be reworked using a thread_join() API once a such will be
     * available in zephyr.
     * see https://github.com/zephyrproject-rtos/zephyr/issues/21500
     */
    (void)k_sem_take(&boot_log_sem, K_FOREVER);
}
#endif /* defined(CONFIG_LOG) && !defined(ZEPHYR_LOG_MODE_IMMEDIATE) && \
        * !defined(CONFIG_LOG_PROCESS_THREAD) && !defined(ZEPHYR_LOG_MODE_MINIMAL)
        */

#ifdef CONFIG_MCUBOOT_SERIAL
static void boot_serial_enter()
{
    int rc;

#ifdef CONFIG_MCUBOOT_INDICATION_LED
    io_led_set(1);
#endif

    mcuboot_status_change(MCUBOOT_STATUS_SERIAL_DFU_ENTERED);

    BOOT_LOG_INF("Enter the serial recovery mode");
    rc = boot_console_init();
    __ASSERT(rc == 0, "Error initializing boot console.\n");
    boot_serial_start(&boot_funcs);
    __ASSERT(0, "Bootloader serial process was terminated unexpectedly.\n");
}
#endif

// OMI
static const struct gpio_dt_spec sd_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});
static const struct device *const sdcard = DEVICE_DT_GET(DT_NODELABEL(sdhc0));

int main(void)
{
    struct boot_rsp rsp;
    int rc;

    // OMI
    static const char *disk_pdrv = DISK_DRIVE_NAME;

    FIH_DECLARE(fih_rc, FIH_FAILURE);

    MCUBOOT_WATCHDOG_SETUP();
    MCUBOOT_WATCHDOG_FEED();

    // OMI
    // delay 100ms to stabilize the system
    gpio_pin_configure_dt(&sd_en, GPIO_OUTPUT);
    gpio_pin_set_dt(&sd_en, 1);
    k_sleep(K_MSEC(1000));

    pm_device_action_run(sdcard, PM_DEVICE_ACTION_RESUME);
    disk_access_ioctl(disk_pdrv, DISK_IOCTL_CTRL_INIT, NULL);
    k_sleep(K_MSEC(1000));

    disk_access_ioctl(disk_pdrv, DISK_IOCTL_CTRL_DEINIT, NULL);
    pm_device_action_run(sdcard, PM_DEVICE_ACTION_SUSPEND);
    // #

#if !defined(MCUBOOT_DIRECT_XIP)
    BOOT_LOG_INF("Starting bootloader");
#else
    BOOT_LOG_INF("Starting Direct-XIP bootloader");
#endif

#ifdef CONFIG_MCUBOOT_INDICATION_LED
    /* LED init */
    io_led_init();
#endif

    os_heap_init();

    ZEPHYR_BOOT_LOG_START();

    (void)rc;

    mcuboot_status_change(MCUBOOT_STATUS_STARTUP);

#ifdef CONFIG_BOOT_SERIAL_ENTRANCE_GPIO
    if (io_detect_pin() &&
            !io_boot_skip_serial_recovery()) {
        boot_serial_enter();
    }
#endif

#ifdef CONFIG_BOOT_SERIAL_PIN_RESET
    if (io_detect_pin_reset()) {
        boot_serial_enter();
    }
#endif

#if defined(CONFIG_BOOT_USB_DFU_GPIO)
    if (io_detect_pin()) {
#ifdef CONFIG_MCUBOOT_INDICATION_LED
        io_led_set(1);
#endif

        mcuboot_status_change(MCUBOOT_STATUS_USB_DFU_ENTERED);

        rc = usb_enable(NULL);
        if (rc) {
            BOOT_LOG_ERR("Cannot enable USB");
        } else {
            BOOT_LOG_INF("Waiting for USB DFU");
            wait_for_usb_dfu(K_FOREVER);
            BOOT_LOG_INF("USB DFU wait time elapsed");
        }
    }
#elif defined(CONFIG_BOOT_USB_DFU_WAIT)
    rc = usb_enable(NULL);
    if (rc) {
        BOOT_LOG_ERR("Cannot enable USB");
    } else {
        BOOT_LOG_INF("Waiting for USB DFU");

        mcuboot_status_change(MCUBOOT_STATUS_USB_DFU_WAITING);

        wait_for_usb_dfu(K_MSEC(CONFIG_BOOT_USB_DFU_WAIT_DELAY_MS));
        BOOT_LOG_INF("USB DFU wait time elapsed");

        mcuboot_status_change(MCUBOOT_STATUS_USB_DFU_TIMED_OUT);
    }
#endif

#ifdef CONFIG_BOOT_SERIAL_WAIT_FOR_DFU
    /* Initialize the boot console, so we can already fill up our buffers while
     * waiting for the boot image check to finish. This image check, can take
     * some time, so it's better to reuse thistime to already receive the
     * initial mcumgr command(s) into our buffers
     */
    rc = boot_console_init();
    int timeout_in_ms = CONFIG_BOOT_SERIAL_WAIT_FOR_DFU_TIMEOUT;
    uint32_t start = k_uptime_get_32();

#ifdef CONFIG_MCUBOOT_INDICATION_LED
    io_led_set(1);
#endif
#endif

    FIH_CALL(boot_go, fih_rc, &rsp);

#ifdef CONFIG_BOOT_SERIAL_BOOT_MODE
    if (io_detect_boot_mode()) {
        /* Boot mode to stay in bootloader, clear status and enter serial
         * recovery mode
         */
        boot_serial_enter();
    }
#endif

#ifdef CONFIG_BOOT_SERIAL_WAIT_FOR_DFU
    timeout_in_ms -= (k_uptime_get_32() - start);
    if( timeout_in_ms <= 0 ) {
        /* at least one check if time was expired */
        timeout_in_ms = 1;
    }
    boot_serial_check_start(&boot_funcs,timeout_in_ms);

#ifdef CONFIG_MCUBOOT_INDICATION_LED
    io_led_set(0);
#endif
#endif

    if (FIH_NOT_EQ(fih_rc, FIH_SUCCESS)) {
        BOOT_LOG_ERR("Unable to find bootable image");

        mcuboot_status_change(MCUBOOT_STATUS_NO_BOOTABLE_IMAGE_FOUND);

#ifdef CONFIG_BOOT_SERIAL_NO_APPLICATION
        /* No bootable image and configuration set to remain in serial
         * recovery mode
         */
        boot_serial_enter();
#elif defined(CONFIG_BOOT_USB_DFU_NO_APPLICATION)
        rc = usb_enable(NULL);
        if (rc && rc != -EALREADY) {
            BOOT_LOG_ERR("Cannot enable USB");
        } else {
            BOOT_LOG_INF("Waiting for USB DFU");
            wait_for_usb_dfu(K_FOREVER);
        }
#endif

        FIH_PANIC;
    }

#ifdef CONFIG_BOOT_RAM_LOAD
    BOOT_LOG_INF("Bootloader chainload address offset: 0x%x",
                 rsp.br_hdr->ih_load_addr);
#else
    BOOT_LOG_INF("Bootloader chainload address offset: 0x%x",
                 rsp.br_image_off);
#endif

#if defined(MCUBOOT_DIRECT_XIP)
    BOOT_LOG_INF("Jumping to the image slot");
#else
    BOOT_LOG_INF("Jumping to the first image slot");
#endif

    mcuboot_status_change(MCUBOOT_STATUS_BOOTABLE_IMAGE_FOUND);

#if USE_PARTITION_MANAGER && CONFIG_FPROTECT

#ifdef PM_S1_ADDRESS
/* MCUBoot is stored in either S0 or S1, protect both */
#define PROTECT_SIZE (PM_MCUBOOT_PRIMARY_ADDRESS - PM_S0_ADDRESS)
#define PROTECT_ADDR PM_S0_ADDRESS
#else
/* There is only one instance of MCUBoot */
#define PROTECT_SIZE (PM_MCUBOOT_PRIMARY_ADDRESS - PM_MCUBOOT_ADDRESS)
#define PROTECT_ADDR PM_MCUBOOT_ADDRESS
#endif

    rc = fprotect_area(PROTECT_ADDR, PROTECT_SIZE);

    if (rc != 0) {
        BOOT_LOG_ERR("Protect mcuboot flash failed, cancel startup.");
        while (1)
            ;
    }

#if defined(CONFIG_SOC_NRF5340_CPUAPP) && defined(PM_CPUNET_B0N_ADDRESS) && defined(CONFIG_PCD_APP)
#if defined(PM_TFM_SECURE_ADDRESS)
    pcd_lock_ram(false);
#else
    pcd_lock_ram(true);
#endif
#endif
#endif /* USE_PARTITION_MANAGER && CONFIG_FPROTECT */

    ZEPHYR_BOOT_LOG_STOP();

    do_boot(&rsp);

    mcuboot_status_change(MCUBOOT_STATUS_BOOT_FAILED);

    BOOT_LOG_ERR("Never should get here");
    while (1)
        ;
}
