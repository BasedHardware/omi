/* Compile the production state machine; only OS, reset peripheral, NVS and
 * mcumgr registration are doubled. Static state represents RAM per process. */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../omi/src/safe_mode.c"

static uint32_t reset;
static int64_t now;
static unsigned writes;
static int write_error;
static struct bootstate disk;
static struct mgmt_callback *registered;

int64_t k_uptime_get(void)
{
    return now;
}
uint32_t nrf_reset_resetreas_get(int unused)
{
    (void) unused;
    return reset;
}
void nrf_reset_resetreas_clear(int unused, uint32_t reason)
{
    (void) unused;
    assert(reason == reset);
    reset = 0;
}
void mgmt_callback_register(struct mgmt_callback *cb)
{
    registered = cb;
}
int settings_save_one(const char *key, const void *value, size_t len)
{
    assert(!strcmp(key, "omi/bootstate"));
    assert(len == sizeof(disk));
    writes++;
    if (write_error) {
        return write_error;
    }
    memcpy(&disk, value, len);
    return 0;
}
static ssize_t read_disk(void *arg, void *value, size_t len)
{
    (void) arg;
    memcpy(value, &disk, len);
    return len;
}
static void boot(uint32_t reason, bool load_settings)
{
    active = false;
    settings_ready = false;
    self_test_done = false;
    ready_at = 0;
    trial_ready = false;
    now = 0;
    memset(&saved, 0, sizeof(saved));
    reset = reason;
    safe_mode_early_boot();
    if (load_settings) {
        if (disk.state) {
            assert(!safe_mode_settings_set("bootstate", sizeof(disk), read_disk, NULL));
        }
        safe_mode_settings_ready(0);
    }
    safe_mode_boot();
}
static void clean(void)
{
    memset((void *) &retained, 0, sizeof(retained));
    memset(&disk, 0, sizeof(disk));
    writes = 0;
    write_error = 0;
}
static void good(void)
{
    safe_mode_main_loop_ready(true);
    now = CONFIG_OMI_SAFE_MODE_GOOD_UPTIME_S * 1000 - 1;
    safe_mode_poll();
    assert(retained.count != 0);
    now++;
    safe_mode_poll();
    assert(retained.count == 0);
}
static void dfu(enum mgmt_cb_return status)
{
    assert(registered && registered->event_id == MGMT_EVT_OP_IMG_MGMT_DFU_PENDING);
    registered->callback(registered->event_id, status, NULL, NULL, NULL, NULL, 0);
}
int main(void)
{
    clean();
    /* Even 100 failures before settings/main cause ZERO NVS writes. */
    for (int i = 0; i < 100; i++) {
        boot(NRF_RESET_RESETREAS_DOG0_MASK, false);
        assert(active == (i >= CONFIG_OMI_SAFE_MODE_BOOT_LIMIT));
    }
    assert(writes == 0 && retained.count == 100);
    boot(NRF_RESET_RESETREAS_LOCKUP_MASK, true);
    assert(active && disk.state == STATE_SAFE && writes == 1);
    for (int i = 0; i < 100; i++) {
        boot(NRF_RESET_RESETREAS_DOG1_MASK, true);
    }
    assert(writes == 1); /* SAFE once, never a per-reset counter write. */
    memset((void *) &retained, 0, sizeof(retained));
    boot(0, true);
    assert(active); /* durable SAFE survives total loss of RAM */
    dfu(MGMT_CB_ERROR_RC);
    assert(retained.latch_reason && writes == 1);
    write_error = -EIO;
    dfu(MGMT_CB_OK);
    assert(retained.latch_reason); /* failed persistence must not claim recovery */
    write_error = 0;
    dfu(MGMT_CB_OK);
    assert(!retained.latch_reason && !retained.count && disk.state == STATE_TRIAL);
    assert(active); /* current safe session stays safe until reset */
    boot(NRF_RESET_RESETREAS_SREQ_MASK, true);
    assert(!active && retained.count == 1); /* same-version DFU */
    good();
    assert(disk.state == STATE_GOOD);
    unsigned prior_writes = writes;
    for (int i = 0; i < 100; i++) {
        boot(NRF_RESET_RESETREAS_DOG0_MASK, true);
        assert(!active);
        good();
        for (int j = 0; j < 100; j++) {
            safe_mode_poll();
        }
    }
    assert(writes == prior_writes); /* no false latch, zero steady-state writes */

    clean();
    boot(0, true);
    safe_mode_main_loop_ready(false);
    now = 999999;
    safe_mode_poll();
    assert(retained.count == 1 && writes == 0); /* no advertising => never GOOD */
    for (int i = 0; i < 100; i++) {
        boot(NRF_RESET_RESETREAS_SREQ_MASK, false);
        assert(!active && retained.count == 1);
        boot(NRF_RESET_RESETREAS_RESETPIN_MASK, false);
        assert(!active && retained.count == 1);
        boot(0, false);
        assert(!active && retained.count == 1);
    }
    /* Fatal software resets must count despite SREQ being a normal reset. */
    for (int i = 0; i < CONFIG_OMI_SAFE_MODE_BOOT_LIMIT; i++) {
        retained.fatal = 1;
        boot(NRF_RESET_RESETREAS_SREQ_MASK, false);
    }
    assert(active);
    clean();
    boot(0, true);
    safe_mode_main_loop_ready(true);
    dfu(MGMT_CB_OK); /* Upload during normal trial must not certify the old boot. */
    now = CONFIG_OMI_SAFE_MODE_GOOD_UPTIME_S * 1000;
    safe_mode_poll();
    assert(disk.state == STATE_TRIAL && retained.count == 0);
    boot(NRF_RESET_RESETREAS_SREQ_MASK, true);
    good();
    assert(disk.state == STATE_GOOD);

    clean();
    boot(0, true);
    strcpy(disk.fw, "old-version");
    disk.state = STATE_SAFE;
    disk.reason = 1;
    boot(0, true);
    assert(!active); /* changed version gets its own trial */
    good();
    assert(!strcmp(disk.fw, FW) && disk.state == STATE_GOOD);
    retained.count = UINT32_MAX;
    retained.latch_reason = 1;
    boot(NRF_RESET_RESETREAS_DOG0_MASK, true);
    assert(retained.count == UINT32_MAX); /* saturates */
    assert(safe_mode_settings_set("other", 0, read_disk, NULL) == -ENOENT);
    assert(safe_mode_settings_set("bootstate", 1, read_disk, NULL) == -EINVAL);
    puts("safe-mode: threshold, reset classes, 100-crash zero-write loop, durable latch, DFU callback, self-test and "
         "version tests passed");
}
