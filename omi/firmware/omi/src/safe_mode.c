#include "safe_mode.h"

#include <errno.h>
#include <stddef.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "boot_telemetry.h"
#if defined(CONFIG_MCUMGR)
#include <zephyr/mgmt/mcumgr/grp/img_mgmt/img_mgmt.h>
#include <zephyr/mgmt/mcumgr/grp/img_mgmt/img_mgmt_callbacks.h>
#include <zephyr/mgmt/mcumgr/mgmt/callbacks.h>
#else
#include "safe_mode_sim_mgmt.h"
#endif
#include <zephyr/settings/settings.h>
#if defined(CONFIG_MCUMGR)
#include <zephyr/storage/flash_map.h>
#endif

#include <hal/nrf_reset.h>
#ifndef OMI_SAFE_MODE_HOST
#include <zephyr/drivers/gpio.h>
#include <zephyr/fatal.h>
#include <zephyr/init.h>
#include <zephyr/sys/poweroff.h>

#include "lib/core/led.h"
#include "lib/core/transport.h"
#include "wdog_facade.h"
#endif

LOG_MODULE_REGISTER(safe_mode, CONFIG_LOG_DEFAULT_LEVEL);

#if defined(CONFIG_OMI_FAULT_INJECT) && !defined(OMI_FAULT_INJECT_ALLOWED)
#error "Fault injection is forbidden in release builds"
#endif

#define BOOT_MAGIC 0x53414633u
#define BOOT_COUNT_MAX 255u
#define FW CONFIG_BT_DIS_FW_REV_STR
#define STATE_SAFE 1
#define STATE_GOOD 2
#define STATE_TRIAL 3
#define SAFE_ENTRY_HOLD_MS 10000
#define SAFE_ENTRY_POLL_MS 50

/* Keep the original pending value (1). Every failed/hung resolve attempt is
 * followed by a boot without a read. Three reads max; values are retained ABI.
 */
enum dfu_resolve_state {
    DFU_IDLE = 0,
    DFU_PENDING = 1,
    DFU_WAIT_TWO = 2,
    DFU_RETRY_TWO = 3,
    DFU_WAIT_ONE = 4,
    DFU_RETRY_ONE = 5,
};

/* NOLOAD at a fixed DTS address: no driver or C startup may clear this. */
struct retained_boot {
    uint32_t magic;
    uint32_t count;
    uint32_t reset_reason;
    uint32_t latch_reason;
    uint32_t fatal;
    char fw[16];
    uint32_t dfu_pending;
    uint32_t persist_attempted;
    uint32_t telemetry_blocked; /* GUARD_* bits: set across a call that may hang */
    uint32_t total_boots;
    uint32_t telemetry_fatal;
    uint32_t total_seeded;
    uint32_t crc;
};
#ifndef CONFIG_OMI_NATIVE_SIM
static volatile struct retained_boot retained __attribute__((section(".omi_retained"), used));
#else
static volatile struct retained_boot retained;
#endif
#define GUARD_TELEMETRY 1u
#define GUARD_SD_INIT 2u

_Static_assert(sizeof(retained) <= 64, "retained boot record exceeds reservation");
_Static_assert(sizeof(retained) == 64 && offsetof(struct retained_boot, dfu_pending) == 36 &&
                   offsetof(struct retained_boot, crc) == 60,
               "retained boot layout changed");
_Static_assert(sizeof(FW) <= sizeof(retained.fw), "firmware version too long");

struct bootstate {
    uint32_t state;
    uint32_t reason;
    char fw[16];
};
static struct bootstate saved;
static bool active;
static bool previous_fatal;
static uint32_t boot_reset_reason;
static bool settings_ready;
static bool self_test_done;
static int64_t ready_at;
static bool trial_ready;
static bool resolve_dfu;
static bool image0_upload;
/* Main's SAFE/GOOD writes and the SMP worker's TRIAL write share authority.
 * Fatal/early hooks never acquire this lock or call settings.
 */
K_MUTEX_DEFINE(bootstate_lock);

/* CRC-32/ISO-HDLC, no driver, tables, locks or allocation (also used by fatal).
 * Volatile byte reads cover every field preceding crc, including the full FW.
 */
static uint32_t retained_crc(void)
{
    const volatile uint8_t *bytes = (const volatile uint8_t *) &retained;
    uint32_t crc = 0xffffffffu;
    for (size_t i = 0; i < offsetof(struct retained_boot, crc); ++i) {
        crc ^= bytes[i];
        for (unsigned int bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
        }
    }
    return ~crc;
}

static void retained_seal(void)
{
    retained.crc = retained_crc();
}

static bool retained_valid(void)
{
    return retained.magic == BOOT_MAGIC && retained.count <= BOOT_COUNT_MAX && retained.latch_reason <= 3 &&
           retained.fatal <= 1 && retained.telemetry_blocked <= (GUARD_TELEMETRY | GUARD_SD_INIT) &&
           retained.telemetry_fatal <= 1 && retained.total_seeded <= 1 && retained.dfu_pending <= DFU_RETRY_ONE &&
           retained.persist_attempted <= 1 && memcmp((const void *) retained.fw, FW, sizeof(FW)) == 0 &&
           retained.crc == retained_crc();
}

static void new_trial(void)
{
    /* Recovery trials reset independently of lifetime diagnostics. */
    bool valid = retained_valid();
    uint32_t total_boots = valid ? retained.total_boots : 0;
    uint32_t fatal = valid ? retained.telemetry_fatal : 0;
    uint32_t seeded = valid ? retained.total_seeded : 0;
    memset((void *) &retained, 0, sizeof(retained));
    memcpy((void *) retained.fw, FW, sizeof(FW));
    retained.magic = BOOT_MAGIC;
    retained.total_boots = total_boots;
    retained.telemetry_fatal = fatal;
    retained.total_seeded = seeded;
    retained_seal();
}

static void record_fatal(void)
{
    /* Do not bless preexisting corruption by computing a new CRC over it. */
    if (!retained_valid()) {
        new_trial();
    }
    retained.fatal = 1;
    retained.telemetry_fatal = 1;
    retained_seal();
}
#ifdef CONFIG_OMI_NATIVE_SIM
/* Simulator power model: lets the sim persist this record across warm resets. */
volatile void *omi_sim_retained_ram(size_t *size)
{
    *size = sizeof(retained);
    return &retained;
}
#endif

void safe_mode_early_boot(void)
{
    uint32_t reason = 0;
    bool crash = false;
    reason = nrf_reset_resetreas_get(NRF_RESET);
    crash = (reason &
             (NRF_RESET_RESETREAS_DOG0_MASK | NRF_RESET_RESETREAS_DOG1_MASK | NRF_RESET_RESETREAS_LOCKUP_MASK)) != 0;
#ifdef RESET_RESETREAS_SGERR_Msk
    crash |= (reason & RESET_RESETREAS_SGERR_Msk) != 0;
#endif
#ifdef RESET_RESETREAS_SDERR_Msk
    crash |= (reason & RESET_RESETREAS_SDERR_Msk) != 0;
#endif
    nrf_reset_resetreas_clear(NRF_RESET, reason);
    bool valid = retained_valid();
    uint32_t total_before = valid ? retained.total_boots : 0;
    uint32_t seeded_before = valid ? retained.total_seeded : 0;
    boot_reset_reason = reason;
    /* 3.0.24: SAFE lives only in retained RAM and survives only the resets that
     * a crash loop or a recovery session produces (watchdog, lockup, fatal and
     * software resets). Power-on, OFF wake, pin reset and every other class
     * start a fresh normal trial, so a user power cycle always leaves SAFE.
     */
    bool keeps_latch = crash || (valid && retained.fatal != 0) || (reason & NRF_RESET_RESETREAS_SREQ_MASK) != 0;
    resolve_dfu = valid && keeps_latch &&
                  (retained.dfu_pending == DFU_PENDING || retained.dfu_pending == DFU_RETRY_TWO ||
                   retained.dfu_pending == DFU_RETRY_ONE);
    /* A waiting state guarantees this entire boot bypasses the backend read.
     * Arm the next attempt only for a later boot; resolve_dfu stays false.
     */
    if (valid && retained.dfu_pending == DFU_WAIT_TWO) {
        retained.dfu_pending = DFU_RETRY_TWO;
    } else if (valid && retained.dfu_pending == DFU_WAIT_ONE) {
        retained.dfu_pending = DFU_RETRY_ONE;
    }
    previous_fatal = valid && retained.telemetry_fatal != 0;
    crash = crash || (valid && retained.fatal != 0);
    /* RESETREAS=0 is POR; RAM contents on cold boot are not a contract. */
    if (!valid || !keeps_latch || (!crash && !retained.latch_reason)) {
        new_trial();
    }
    retained.fatal = 0;
    retained.total_boots = total_before;
    retained.telemetry_fatal = previous_fatal;
    retained.total_seeded = seeded_before;
    if (retained.total_boots != UINT32_MAX) {
        ++retained.total_boots;
    }
    retained.reset_reason = reason;
    if (retained.count < BOOT_COUNT_MAX) {
        retained.count++;
    }
    if (retained.count > CONFIG_OMI_SAFE_MODE_BOOT_LIMIT && !retained.latch_reason) {
        retained.latch_reason = 1;
    }
    retained_seal();
}

int safe_mode_settings_set(const char *name, size_t len, settings_read_cb read_cb, void *arg)
{
    if (!strcmp(name, "boot_telemetry")) {
        /* The telemetry owner loads this key directly, after boot selection.
         * Broad normal app/BT loads must neither reject nor replay it.
         */
        return 0;
    }
    if (strcmp(name, "bootstate")) {
        return -ENOENT;
    }
    struct bootstate value;
    if (len != sizeof(value)) {
        return -EINVAL;
    }
    int rc = read_cb(arg, &value, sizeof(value));
    if (rc != sizeof(value)) {
        return rc < 0 ? rc : -EINVAL;
    }
    if (value.state < STATE_SAFE || value.state > STATE_TRIAL || value.reason > 3 ||
        !memchr(value.fw, 0, sizeof(value.fw))) {
        return -EINVAL;
    }
    saved = value;
    return 0;
}

static int save_state(uint32_t state, uint32_t reason)
{
    struct bootstate value = {.state = state, .reason = reason, .fw = FW};
    if (!memcmp(&saved, &value, sizeof(value))) {
        return 0;
    }
    if (!settings_ready) {
        printk("Bootstate write failed (%d); RAM latch retained\n", -EIO);
        return -EIO;
    }
    int err = settings_save_one("omi/bootstate", &value, sizeof(value));
    if (!err) {
        saved = value;
        printk("omi/bootstate=%s fw=%s\n", state == STATE_SAFE ? "SAFE" : state == STATE_GOOD ? "GOOD" : "TRIAL", FW);
    } else {
        printk("Bootstate write failed (%d); RAM latch retained\n", err);
    }
    return err;
}

/* NVS never restores SAFE (3.0.24): a stored SAFE from 3.0.23 is ignored and
 * replaced by GOOD after the next healthy trial. A pending DFU transaction is
 * the sole reader: NVS decides whether TRIAL committed before reset.
 */
void safe_mode_settings_ready(int status)
{
    settings_ready = status == 0;
    if (settings_ready && !strcmp(saved.fw, FW) && resolve_dfu && saved.state == STATE_TRIAL) {
        new_trial();
        retained.count = 1;
    }
    resolve_dfu = false;
    if (settings_ready) {
        retained.dfu_pending = DFU_IDLE;
    }
    retained_seal();
}

static int read_bootstate(const char *name, size_t len, settings_read_cb read_cb, void *cb_arg, void *param)
{
    ARG_UNUSED(param);
    /* Zephyr passes NULL for an exact subtree match, not an empty string. */
    if (name && *name) {
        return 0;
    }
    return safe_mode_settings_set("bootstate", len, read_cb, cb_arg);
}

void safe_mode_restore(void)
{
    if (!resolve_dfu) {
        return;
    }
    /* Spend an attempt BEFORE any backend access. A failed/hung read keeps
     * the remaining budget; the next WDT boot bypasses it and advertises SAFE.
     */
    if (resolve_dfu && retained.dfu_pending == DFU_PENDING) {
        retained.dfu_pending = DFU_WAIT_TWO;
    } else if (resolve_dfu && retained.dfu_pending == DFU_RETRY_TWO) {
        retained.dfu_pending = DFU_WAIT_ONE;
    } else {
        retained.dfu_pending = DFU_IDLE;
    }
    retained_seal();
    int err = settings_subsys_init();
    if (!err) {
        err = settings_load_subtree_direct("omi/bootstate", read_bootstate, NULL);
    }
    safe_mode_settings_ready(err);
}

/* Called after recovery advertising is up, never loads app or BT settings.
 * SAFE itself is never written to flash (3.0.24); only optional telemetry IO
 * runs here. Outstanding DFU resolution must preserve any committed TRIAL.
 */
void safe_mode_persist(void)
{
    k_mutex_lock(&bootstate_lock, K_FOREVER);
    /* Preserve the mandatory no-backend boot between DFU resolve attempts.
     */
    if (active && !(retained.telemetry_blocked & GUARD_TELEMETRY) && retained.dfu_pending == DFU_IDLE) {
        retained.telemetry_blocked |= GUARD_TELEMETRY;
        retained_seal();
        omi_boot_telemetry_open();
        /* Returned backend errors are nonfatal; only a hang keeps the guard. */
        retained.telemetry_blocked &= ~GUARD_TELEMETRY;
        retained_seal();
    }
    k_mutex_unlock(&bootstate_lock);
}

static enum mgmt_cb_return dfu_event(uint32_t event,
                                     enum mgmt_cb_return prev_status,
                                     int32_t *rc,
                                     uint16_t *group,
                                     bool *abort_more,
                                     void *data,
                                     size_t data_size)
{
    ARG_UNUSED(group);
    if (event == MGMT_EVT_OP_IMG_MGMT_DFU_CHUNK) {
        const struct img_mgmt_upload_check *check = data;
        /* PENDING has no payload in NCS 2.9.0. Remember the inspected target
         * on EVERY chunk (also handles resumption with an omitted image key).
         */
        image0_upload = false;
        if (prev_status != MGMT_CB_OK) {
            return MGMT_CB_OK;
        }
        bool valid = check && data_size == sizeof(*check) && check->req && check->action;
        bool app = valid && check->action->area_id == FIXED_PARTITION_ID(slot1_partition);
        if (active && (!app || check->req->image != 0)) {
            *rc = MGMT_ERR_EINVAL;
            *abort_more = true;
            return MGMT_CB_ERROR_RC;
        }
        image0_upload = app && check->req->image == 0;
    } else if (event == MGMT_EVT_OP_IMG_MGMT_DFU_STOPPED) {
        image0_upload = false;
    } else if (event == MGMT_EVT_OP_IMG_MGMT_DFU_PENDING) {
        bool completed_app = image0_upload && prev_status == MGMT_CB_OK;
        image0_upload = false;
        if (completed_app) {
            omi_boot_telemetry_upload_pending();
            k_mutex_lock(&bootstate_lock, K_FOREVER);
            if (!settings_ready) {
                settings_ready = settings_subsys_init() == 0;
            }
            /* Publish intent BEFORE NVS; a reset after its commit but before
             * new_trial must resolve persisted TRIAL, even for this version.
             */
            retained.dfu_pending = DFU_PENDING;
            retained_seal();
            if (!save_state(STATE_TRIAL, 0)) {
                new_trial();
                trial_ready = false;
                self_test_done = true; /* main-loop readiness may arrive after this callback. */
                printk("Safe mode DFU finished: fresh trial on next boot\n");
            } else {
                retained.dfu_pending = 0;
                retained_seal();
            }
            k_mutex_unlock(&bootstate_lock);
        }
    }
    return MGMT_CB_OK;
}
static struct mgmt_callback dfu_callback;

bool safe_mode_boot(void)
{
    dfu_callback.callback = dfu_event;
    dfu_callback.event_id =
        MGMT_EVT_OP_IMG_MGMT_DFU_PENDING | MGMT_EVT_OP_IMG_MGMT_DFU_CHUNK | MGMT_EVT_OP_IMG_MGMT_DFU_STOPPED;
    mgmt_callback_register(&dfu_callback);
#ifndef OMI_SAFE_MODE_HOST
    /* Manual entry is a support gesture: hold the button for 10 s at power-on
     * while on the charger. The charger requirement keeps an ordinary long
     * press (wake, or a held power-off) from ever reaching SAFE. button.c is
     * not running yet, so its 3 s power-off cannot fire during this hold.
     * The status pin reads 0 while the charge IC is active (see battery.c).
     */
    const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(DT_NODELABEL(usr_btn), gpios);
    const struct gpio_dt_spec charger = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(bat_chg_pin), gpios, {0});
    if (gpio_is_ready_dt(&button) && gpio_is_ready_dt(&charger) && !gpio_pin_configure_dt(&button, GPIO_INPUT) &&
        !gpio_pin_configure_dt(&charger, GPIO_INPUT | GPIO_PULL_UP)) {
        int held = 0;
        while (gpio_pin_get_dt(&button) > 0 && gpio_pin_get_dt(&charger) == 0) {
            if (held >= SAFE_ENTRY_HOLD_MS) {
                retained.latch_reason = 2;
                break;
            }
            k_msleep(SAFE_ENTRY_POLL_MS);
            held += SAFE_ENTRY_POLL_MS;
        }
    }
#endif
#ifdef CONFIG_OMI_SIM_FORCE_SAFE_MODE
    retained.latch_reason = 3;
#endif
    retained_seal();
    active = retained.latch_reason != 0;
    omi_boot_telemetry_start(boot_reset_reason, previous_fatal, active, retained.latch_reason);
    printk("BOOTSTATE: active=%u count=%u reason=%u reset=0x%08x state=%u\n",
           active,
           retained.count,
           retained.latch_reason,
           retained.reset_reason,
           saved.state);
    return active;
}

bool safe_mode_active(void)
{
    return active;
}

void safe_mode_main_loop_ready(bool advertising)
{
    k_mutex_lock(&bootstate_lock, K_FOREVER);
    if (!active && advertising) {
        ready_at = k_uptime_get();
        trial_ready = true;
    }
    k_mutex_unlock(&bootstate_lock);
}

void safe_mode_poll(void)
{
    if (!active) {
        omi_boot_telemetry_poll();
    }
    k_mutex_lock(&bootstate_lock, K_FOREVER);
    if (!active && !self_test_done && trial_ready &&
        k_uptime_get() - ready_at >= (int64_t) CONFIG_OMI_SAFE_MODE_GOOD_UPTIME_S * 1000) {
        retained.count = 0;
        retained_seal();
        /* One attempt per boot; never turn a failing NVS into a 1 Hz write loop. */
        self_test_done = true;
        (void) save_state(STATE_GOOD, 0);
        printk("Safe mode self-test passed\n");
    }
    k_mutex_unlock(&bootstate_lock);
}

uint32_t safe_mode_total_boots(void)
{
    return retained.total_boots;
}

uint32_t safe_mode_restore_total_boots(uint32_t persisted_count)
{
    /* Called before normal BLE, or under recovery's bootstate lock. Before
     * seeding, total_boots is the delta since cold/invalid RAM, including all
     * pre-settings failures. Afterwards it is an absolute lifetime count.
     */
    if (!retained.total_seeded) {
        retained.total_boots =
            UINT32_MAX - persisted_count < retained.total_boots ? UINT32_MAX : persisted_count + retained.total_boots;
        retained.total_seeded = 1;
    } else {
        uint32_t minimum = persisted_count == UINT32_MAX ? UINT32_MAX : persisted_count + 1;
        if (retained.total_boots < minimum) {
            retained.total_boots = minimum;
        }
    }
    retained_seal();
    return retained.total_boots;
}

void safe_mode_snapshot_get(struct safe_mode_snapshot *out)
{
    *out = (struct safe_mode_snapshot){.boot_count = retained.count,
                                       .reset_reason = retained.reset_reason,
                                       .latch_reason = retained.latch_reason,
                                       .active = active,
                                       .latched = retained.latch_reason != 0,
                                       .bootstate = saved.state};
}

#ifndef OMI_SAFE_MODE_HOST
/* No logging, settings, locks or device calls in a possibly corrupted context. */
void k_sys_fatal_error_handler(unsigned int reason, const struct arch_esf *esf)
{
    ARG_UNUSED(reason);
    ARG_UNUSED(esf);
    record_fatal();
#ifdef CONFIG_OMI_NATIVE_SIM
    omi_sim_reset_fatal();
#else
    __DSB();
    NVIC_SystemReset();
#endif
    CODE_UNREACHABLE;
}

static const struct gpio_dt_spec safe_button = GPIO_DT_SPEC_GET(DT_NODELABEL(usr_btn), gpios);

/* DFU stages into the external NOR; prove SAFE can reach it before advertising. */
static bool secondary_readable(void)
{
    const struct flash_area *area;
    uint8_t first[32], second[32];
    if (flash_area_open(FIXED_PARTITION_ID(slot1_partition), &area)) {
        omi_boot_telemetry_nor_failure();
        return false;
    }
    int rc = flash_area_read(area, 0, first, sizeof(first));
    if (!rc) {
        watchdog_feed();
        rc = flash_area_read(area, 0, second, sizeof(second));
        if (!rc && memcmp(first, second, sizeof(first))) {
            rc = -EIO;
        }
    }
    if (rc) {
        omi_boot_telemetry_nor_failure();
    }
    flash_area_close(area);
    return rc == 0;
}

void safe_mode_run(void)
{
    /* A hung SD init is cut by the watchdog; skip it on later SAFE boots so the
     * same hang cannot keep recovery from advertising. NOR reads may then be
     * noisy, but MCUboot still validates any staged image.
     */
    bool guarded = retained_valid();
    if (!guarded || !(retained.telemetry_blocked & GUARD_SD_INIT)) {
        if (guarded) {
            retained.telemetry_blocked |= GUARD_SD_INIT;
            retained_seal();
        }
        safe_mode_sd_bus_init();
        if (guarded) {
            retained.telemetry_blocked &= ~GUARD_SD_INIT;
            retained_seal();
        }
    } else {
        omi_boot_telemetry_sd_failure();
        printk("Safe SD init skipped after an earlier hang\n");
    }
    /* Keep the SD rail as the boot hog and MCUboot leave it (ON): with it off the
     * shared SPI3 bus times out and the DFU secondary slot in the external NOR is
     * unreachable, so SAFE could never stage an image. NOR shares SPI3, so never
     * suspend the bus here either.
     */
    const struct gpio_dt_spec mic = GPIO_DT_SPEC_GET(DT_NODELABEL(pdm_en_pin), gpios);
    (void) gpio_pin_configure_dt(&mic, GPIO_OUTPUT_INACTIVE);
    (void) led_start();
    printk("Safe mode initialized: BLE DFU only\n");
    printk("Safe mode secondary slot: %s\n", secondary_readable() ? "readable" : "UNREADABLE");
    if (transport_start_safe()) {
        /* Do not feed: retry recovery after the watchdog resets us. */
        for (;;) {
            k_msleep(1000);
        }
    }
    printk("Safe mode feed loop started\n");
    safe_mode_persist();
    unsigned int held = 0;
    bool released = false;
    for (;;) {
        watchdog_feed();
        set_led_red(true);
        k_msleep(50);
        led_off();
        k_msleep(950);
        int pressed = gpio_pin_get_dt(&safe_button);
        if (pressed == 0) {
            released = true;
            held = 0;
        }
        if (released && pressed > 0 && ++held >= 3) {
            /* Wait for release so level-sensitive wake won't immediately reboot. */
            while (gpio_pin_get_dt(&safe_button) > 0) {
                watchdog_feed();
                k_msleep(50);
            }
            if (!gpio_pin_interrupt_configure_dt(&safe_button, GPIO_INT_LEVEL_ACTIVE)) {
                /* A user power-off always leaves SAFE, even if System OFF
                 * retains RAM: the wake is a fresh normal trial. */
                new_trial();
                printk("Safe mode entering system off\n");
                sys_poweroff();
            }
        }
    }
}

#endif
