/* Simulator power, reset, watchdog and pin model (embedded side).
 *
 * The scenario runner owns boot-to-boot state on disk; this file applies one
 * boot's pre-state before main(), drives the button/charger pins from the
 * scripted timeline through the real gpio_emul driver (so production GPIO
 * callbacks and polling run unmodified), enforces a watchdog in simulated
 * time, and ends the process on the same events that end a boot on hardware:
 *
 *   SIM EXIT: poweroff   sys_poweroff() (System OFF)
 *   SIM EXIT: watchdog   no feed for CONFIG_OMI_WATCHDOG_TIMEOUT_MS
 *   SIM EXIT: fatal      k_sys_fatal_error_handler() -> software reset
 *   SIM EXIT: stop       -stop_at reached (a scheduled power event or the end)
 *
 * Every exit writes retained RAM back (the runner decides whether the next
 * boot sees it) and prints one SIMSTATE line, the oracle's assertion surface.
 */
#include <hal/nrf_reset.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/gpio/gpio_emul.h>
#include <zephyr/init.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/poweroff.h>

#include "lib/core/capture_mute.h"
#include "lib/core/settings.h"
#include "posix_board_if.h"
#include "posix_native_task.h"
#include "safe_mode.h"
#include "safe_mode_sim_mgmt.h"
#include "sim_hw.h"
#include "sim_plan.h"
#include "wdog_facade.h"

#define WDT_TIMEOUT_MS CONFIG_OMI_WATCHDOG_TIMEOUT_MS

volatile void *omi_sim_retained_ram(size_t *size);

static const struct omi_sim_plan *plan;
static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(DT_NODELABEL(usr_btn), gpios);
static const struct gpio_dt_spec charger = GPIO_DT_SPEC_GET(DT_NODELABEL(bat_chg_pin), gpios);

static const char *exit_class = "stop";
static bool exiting;
static bool button_pressed;
static bool charging;
static atomic_t battery_mv;
static atomic_t connected;
static atomic_t sd_state;
static unsigned int feeds;
static int64_t last_feed_ms;
static bool wdt_started;
static int64_t poweroff_ms = -1;
static bool button_held_at_poweroff;
static struct omi_sim_fault faults[OMI_SIM_MAX_FAULTS];
static int n_faults;
static unsigned int settings_writes;

/* ---- reset register --------------------------------------------------- */

uint32_t nrf_reset_resetreas_get(int reg)
{
    ARG_UNUSED(reg);
    return plan ? plan->reset_reason : 0;
}

void nrf_reset_resetreas_clear(int reg, uint32_t mask)
{
    ARG_UNUSED(reg);
    ARG_UNUSED(mask);
}

/* ---- pins ------------------------------------------------------------- */

/* Physical level: usr_btn and the charger status pin are both active low. */
static void drive_pins(void)
{
    (void) gpio_emul_input_set(button.port, button.pin, button_pressed ? 0 : 1);
    (void) gpio_emul_input_set(charger.port, charger.pin, charging ? 0 : 1);
}

/* gpio_emul forces a pulled-up input high whenever production reconfigures
 * it; a real pull-up does not override a held button or an asserting charger.
 * Configure fires the pin's callbacks, so re-drive the scripted level there.
 */
static struct gpio_callback reassert_cb;
static bool reasserting;
static void reassert(const struct device *port, struct gpio_callback *cb, gpio_port_pins_t pins)
{
    ARG_UNUSED(port);
    ARG_UNUSED(cb);
    ARG_UNUSED(pins);
    if (reasserting || exiting) {
        return;
    }
    reasserting = true;
    drive_pins();
    reasserting = false;
}

bool omi_sim_button_pressed(void)
{
    return button_pressed;
}

bool omi_sim_charging(void)
{
    return charging;
}

int omi_sim_battery_mv(void)
{
    return (int) atomic_get(&battery_mv);
}

bool omi_sim_connected(void)
{
    return atomic_get(&connected) != 0;
}

int omi_sim_sd_state(void)
{
    return (int) atomic_get(&sd_state);
}

int omi_sim_sd_ready_ms(void)
{
    return plan ? plan->sd_ready_ms : 0;
}

/* ---- exits ------------------------------------------------------------ */

static void save_retained(void)
{
    size_t size = 0;
    volatile void *ram = omi_sim_retained_ram(&size);
    uint8_t copy[OMI_SIM_RETAINED_MAX];
    if (size > sizeof(copy)) {
        size = sizeof(copy);
    }
    memcpy(copy, (const void *) ram, size);
    (void) omi_sim_host_save_retained(copy, (uint32_t) size);
}

static void print_state(void)
{
    struct safe_mode_snapshot snap;
    safe_mode_snapshot_get(&snap);
    extern bool is_off;
    static char line[1024];
    snprintk(line,
             sizeof(line),
             "SIMSTATE: {\"exit\":\"%s\",\"uptime_ms\":%lld,\"safe\":%s,\"latched\":%s,\"latch_reason\":%u,"
             "\"boot_count\":%u,\"bootstate\":%u,\"muted\":%u,\"should_capture\":%s,\"sd_paused\":%s,"
             "\"is_off\":%s,\"feeds\":%u,\"button_pressed\":%s,\"button_held_at_poweroff\":%s,"
             "\"charging\":%s,\"battery_mv\":%d,\"settings_writes\":%u,\"sd_mount_attempts\":%u,"
             "\"sd_ready\":%s,\"sd_written\":%u,\"sd_dropped\":%u,\"sd_gated\":%u,\"sd_io_errors\":%u}",
             exit_class,
             (long long) (poweroff_ms >= 0 ? poweroff_ms : k_uptime_get()),
             snap.active ? "true" : "false",
             snap.latched ? "true" : "false",
             snap.latch_reason,
             snap.boot_count,
             snap.bootstate,
             app_settings_get_muted(),
             capture_mute_should_capture() ? "true" : "false",
             omi_sim_sd_paused() ? "true" : "false",
             is_off ? "true" : "false",
             feeds,
             button_pressed ? "true" : "false",
             button_held_at_poweroff ? "true" : "false",
             charging ? "true" : "false",
             omi_sim_battery_mv(),
             settings_writes,
             omi_sim_sd_mount_attempts(),
             omi_sim_sd_ready() ? "true" : "false",
             omi_sim_sd_written(),
             omi_sim_sd_dropped(),
             omi_sim_sd_gated(),
             omi_sim_sd_io_errors());
    omi_sim_host_print(line);
}

static void on_exit(void)
{
    static char line[64];
    exiting = true;
    snprintk(line, sizeof(line), "SIM EXIT: %s", exit_class);
    omi_sim_host_print(line);
    save_retained();
    print_state();
}
NATIVE_TASK(on_exit, ON_EXIT, 0);

static FUNC_NORETURN void end_boot(const char *why, int code)
{
    exit_class = why;
    posix_exit(code);
    CODE_UNREACHABLE;
}

/* CONFIG_POWEROFF=n in the sim: this replaces the platform System OFF. */
FUNC_NORETURN void sys_poweroff(void)
{
    poweroff_ms = k_uptime_get();
    button_held_at_poweroff = button_pressed;
    end_boot("poweroff", 0);
}

FUNC_NORETURN void omi_sim_reset_fatal(void)
{
    end_boot("fatal", 0);
}

/* ---- watchdog (replaces wdog_facade.c) ------------------------------- */

static void wdt_check(struct k_timer *timer)
{
    ARG_UNUSED(timer);
    if (wdt_started && k_uptime_get() - last_feed_ms > WDT_TIMEOUT_MS) {
        end_boot("watchdog", 0);
    }
}
K_TIMER_DEFINE(wdt_timer, wdt_check, NULL);

static void wdt_start(void)
{
    if (!wdt_started) {
        wdt_started = true;
        last_feed_ms = k_uptime_get();
        k_timer_start(&wdt_timer, K_MSEC(100), K_MSEC(100));
    }
}

int watchdog_init(void)
{
    /* Production starts WDT0 in PRE_KERNEL_2; the sim starts it at POST_KERNEL. */
    wdt_start();
    watchdog_feed();
    printk("SIM: Watchdog initialized (simulated %u ms reset)\n", WDT_TIMEOUT_MS);
    return 0;
}

void watchdog_feed(void)
{
    last_feed_ms = k_uptime_get();
    if (++feeds == 2) {
        printk("SIM: main loop alive (2 watchdog feeds)\n");
    }
}

int watchdog_deinit(void)
{
    /* nRF5340 WDT cannot be stopped once started. */
    return -EPERM;
}

/* ---- settings fault injection (linker --wrap) ------------------------ */

static int fault_rc(int op, const char *key)
{
    for (int i = 0; i < n_faults; ++i) {
        struct omi_sim_fault *f = &faults[i];
        if (f->op != op || f->remaining == 0) {
            continue;
        }
        if (f->key[0] && (!key || strcmp(f->key, key))) {
            continue;
        }
        if (f->remaining > 0) {
            f->remaining--;
        }
        printk("SIM: injected fault op=%d key=%s rc=%d\n", op, key ? key : "-", f->rc);
        return f->rc;
    }
    return 0;
}

int __real_settings_subsys_init(void);
int __wrap_settings_subsys_init(void)
{
    int rc = fault_rc(OMI_SIM_FAULT_SETTINGS_INIT, NULL);
    return rc ? rc : __real_settings_subsys_init();
}

int __real_settings_load_subtree(const char *subtree);
int __wrap_settings_load_subtree(const char *subtree)
{
    int rc = fault_rc(OMI_SIM_FAULT_SETTINGS_LOAD, subtree);
    return rc ? rc : __real_settings_load_subtree(subtree);
}

int __real_settings_save_one(const char *name, const void *value, size_t val_len);
int __wrap_settings_save_one(const char *name, const void *value, size_t val_len)
{
    int rc = fault_rc(OMI_SIM_FAULT_SETTINGS_SAVE, name);
    if (rc) {
        return rc;
    }
    rc = __real_settings_save_one(name, value, val_len);
    if (!rc) {
        settings_writes++;
        printk("SIM: settings write %s\n", name);
    }
    return rc;
}

/* ---- scripted timeline ------------------------------------------------ */

static void apply(const struct omi_sim_event *ev)
{
    switch (ev->kind) {
    case OMI_SIM_EV_BUTTON:
        button_pressed = ev->value != 0;
        printk("SIM: button %s\n", button_pressed ? "press" : "release");
        drive_pins();
        break;
    case OMI_SIM_EV_CHARGER:
        charging = ev->value != 0;
        printk("SIM: charger %s\n", charging ? "on" : "off");
        drive_pins();
        break;
    case OMI_SIM_EV_BATTERY_MV:
        atomic_set(&battery_mv, ev->value);
        printk("SIM: battery %d mV\n", ev->value);
        break;
    case OMI_SIM_EV_CONNECTED:
        atomic_set(&connected, ev->value);
        printk("SIM: central %s\n", ev->value ? "connected" : "disconnected");
        break;
    case OMI_SIM_EV_SD:
        atomic_set(&sd_state, ev->value);
        printk("SIM: sd state %d\n", ev->value);
        break;
    case OMI_SIM_EV_APP_MUTE:
        /* The app can only write the mute characteristic once normal BLE is up;
         * SAFE registers no application GATT services. */
        if (safe_mode_active() || !omi_sim_transport_up()) {
            printk("SIM: app mute write not delivered (no application GATT)\n");
        } else {
            printk("SIM: app writes mute=%d (rc=%d)\n", ev->value, capture_mute_set(ev->value != 0));
        }
        break;
    case OMI_SIM_EV_DFU:
        omi_sim_dfu(ev->value);
        break;
    case OMI_SIM_EV_PANIC:
        printk("SIM: injected kernel panic\n");
        k_panic();
        break;
    default:
        printk("SIM: unknown event kind %d\n", ev->kind);
        break;
    }
}

static void timeline(void *a, void *b, void *c)
{
    ARG_UNUSED(a);
    ARG_UNUSED(b);
    ARG_UNUSED(c);
    for (int i = 0; i < plan->n_events; ++i) {
        const struct omi_sim_event *ev = &plan->events[i];
        int64_t wait = ev->t_ms - k_uptime_get();
        if (wait > 0) {
            k_msleep((int32_t) wait);
        }
        apply(ev);
    }
}
K_THREAD_STACK_DEFINE(timeline_stack, 2048);
static struct k_thread timeline_thread;

static int sim_hw_init(void)
{
    plan = omi_sim_host_plan();
    button_pressed = plan->button_pressed != 0;
    charging = plan->charging != 0;
    atomic_set(&battery_mv, plan->battery_mv);
    atomic_set(&connected, plan->connected);
    atomic_set(&sd_state, plan->sd_state);
    n_faults = plan->n_faults;
    memcpy(faults, plan->faults, sizeof(faults));

    size_t size = 0;
    volatile void *ram = omi_sim_retained_ram(&size);
    memset((void *) ram, 0, size);
    if (plan->retained_loaded && plan->retained_len == size) {
        memcpy((void *) ram, plan->retained, size);
    }
    printk("SIM: boot reset=0x%08x retained=%s button=%d charging=%d battery=%d\n",
           plan->reset_reason,
           plan->retained_loaded ? "warm" : "cold",
           button_pressed,
           charging,
           plan->battery_mv);

    /* Inputs without pull flags: the scripted level is the electrical level. */
    (void) gpio_pin_configure(button.port, button.pin, GPIO_INPUT);
    (void) gpio_pin_configure(charger.port, charger.pin, GPIO_INPUT);
    gpio_init_callback(&reassert_cb, reassert, BIT(button.pin) | BIT(charger.pin));
    (void) gpio_add_callback(button.port, &reassert_cb);
    drive_pins();
    wdt_start();

    k_thread_create(&timeline_thread,
                    timeline_stack,
                    K_THREAD_STACK_SIZEOF(timeline_stack),
                    timeline,
                    NULL,
                    NULL,
                    NULL,
                    K_PRIO_COOP(1),
                    0,
                    K_NO_WAIT);
    k_thread_name_set(&timeline_thread, "sim_timeline");
    return 0;
}
SYS_INIT(sim_hw_init, POST_KERNEL, 99);
