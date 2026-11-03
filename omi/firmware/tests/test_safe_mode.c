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
static unsigned loads;
static int init_error;
static unsigned init_calls;
static bool reset_after_trial;
static struct retained_boot before_ram_clear;
int settings_subsys_init(void)
{
    init_calls++;
    return init_error;
}

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
    assert(cb->event_id ==
           (MGMT_EVT_OP_IMG_MGMT_DFU_PENDING | MGMT_EVT_OP_IMG_MGMT_DFU_CHUNK | MGMT_EVT_OP_IMG_MGMT_DFU_STOPPED));
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
    if (reset_after_trial && disk.state == STATE_TRIAL) {
        memcpy(&before_ram_clear, (const void *) &retained, sizeof(retained));
    }
    return 0;
}
static ssize_t read_disk(void *arg, void *value, size_t len)
{
    (void) arg;
    memcpy(value, &disk, len);
    return len;
}
int settings_load_subtree_direct(const char *key, settings_load_direct_cb cb, void *param)
{
    assert(!strcmp(key, "omi/bootstate"));
    loads++;
    return disk.state ? cb(NULL, sizeof(disk), read_disk, NULL, param) : 0;
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
    image0_upload = false;
    if (load_settings) {
        safe_mode_restore();
    }
    safe_mode_boot();
    if (load_settings) {
        /* Mirror main: app settings only after normal mode was selected. */
        if (!active) {
            if (disk.state) {
                assert(!safe_mode_settings_set("bootstate", sizeof(disk), read_disk, NULL));
            }
            safe_mode_settings_ready(0);
        }
        safe_mode_persist();
    }
}
static void clean(void)
{
    memset((void *) &retained, 0, sizeof(retained));
    memset(&disk, 0, sizeof(disk));
    writes = 0;
    write_error = 0;
    init_error = 0;
    loads = 0;
    init_calls = 0;
    reset_after_trial = false;
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
static enum mgmt_cb_return chunk(uint32_t image, int area)
{
    struct img_mgmt_upload_req req = {.image = image};
    struct img_mgmt_upload_action action = {.area_id = area};
    struct img_mgmt_upload_check check = {.req = &req, .action = &action};
    int32_t rc = 0;
    bool abort_more = false;
    enum mgmt_cb_return result =
        registered->callback(MGMT_EVT_OP_IMG_MGMT_DFU_CHUNK, MGMT_CB_OK, &rc, NULL, &abort_more, &check, sizeof(check));
    if (result != MGMT_CB_OK) {
        assert(rc == MGMT_ERR_EINVAL && abort_more);
    }
    return result;
}
static void pending(enum mgmt_cb_return status)
{
    assert(registered);
    registered->callback(MGMT_EVT_OP_IMG_MGMT_DFU_PENDING, status, NULL, NULL, NULL, NULL, 0);
}
static void dfu(enum mgmt_cb_return status)
{
    assert(chunk(0, FIXED_PARTITION_ID(slot1_partition)) == MGMT_CB_OK);
    pending(status);
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
        record_fatal();
        boot(NRF_RESET_RESETREAS_SREQ_MASK, false);
    }
    assert(active);
    clean();
    boot(0, true);
    safe_mode_main_loop_ready(true);
    dfu(MGMT_CB_OK);                 /* Upload during normal trial must not certify the old boot. */
    safe_mode_main_loop_ready(true); /* Nor may late startup re-arm that old boot. */
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
    retained.count = BOOT_COUNT_MAX;
    retained.latch_reason = 1;
    retained_seal();
    boot(NRF_RESET_RESETREAS_DOG0_MASK, true);
    assert(retained.count == BOOT_COUNT_MAX); /* saturates */
    assert(safe_mode_settings_set("other", 0, read_disk, NULL) == -ENOENT);
    assert(safe_mode_settings_set("bootstate", 1, read_disk, NULL) == -EINVAL);
    /* Single-field damage, retaining a valid magic, must NEVER become a latch. */
    clean();
    boot(0, true);
    struct retained_boot intact;
    memcpy(&intact, (const void *) &retained, sizeof(intact));
    for (size_t byte = sizeof(retained.magic); byte < sizeof(retained); ++byte) {
        memcpy((void *) &retained, &intact, sizeof(intact));
        ((volatile uint8_t *) &retained)[byte] ^= 1;
        assert(retained.magic == BOOT_MAGIC && !retained_valid());
        boot(NRF_RESET_RESETREAS_DOG0_MASK, true);
        assert(!active && retained.count == 1 && retained_valid());
    }
    /* Fatal marking must not reseal corruption into a trusted latch either. */
    retained.latch_reason = 1;
    assert(!retained_valid());
    record_fatal();
    assert(retained_valid() && !retained.latch_reason && retained.fatal == 1);
    boot(NRF_RESET_RESETREAS_SREQ_MASK, true);
    assert(!active);
    /* Range validation is independent of CRC. */
    for (unsigned field = 0; field < 3; ++field) {
        new_trial();
        if (field == 0)
            retained.count = BOOT_COUNT_MAX + 1;
        if (field == 1)
            retained.latch_reason = 4;
        if (field == 2)
            retained.fatal = 2;
        retained_seal();
        assert(!retained_valid());
        boot(0, true);
        assert(!active);
    }

    clean();
    for (int i = 0; i <= CONFIG_OMI_SAFE_MODE_BOOT_LIMIT; ++i) {
        boot(NRF_RESET_RESETREAS_DOG0_MASK, true);
    }
    assert(active);
    unsigned old_writes = writes;
    pending(MGMT_CB_OK); /* no checked upload => cannot clear */
    assert(retained.latch_reason && writes == old_writes);
    assert(chunk(1, 2) == MGMT_CB_ERROR_RC);
    pending(MGMT_CB_OK);
    assert(retained.latch_reason && writes == old_writes);
    /* A resumed image-1 packet can omit image (defaults to 0); area still rejects. */
    assert(chunk(0, 2) == MGMT_CB_ERROR_RC);
    assert(chunk(1, FIXED_PARTITION_ID(slot1_partition)) == MGMT_CB_ERROR_RC);
    pending(MGMT_CB_OK);
    assert(retained.latch_reason && writes == old_writes);
    assert(chunk(0, FIXED_PARTITION_ID(slot1_partition)) == MGMT_CB_OK);
    registered->callback(MGMT_EVT_OP_IMG_MGMT_DFU_STOPPED, MGMT_CB_OK, NULL, NULL, NULL, NULL, 0);
    pending(MGMT_CB_OK);
    assert(retained.latch_reason && writes == old_writes);

    unsigned prior_loads = loads;
    int32_t reject_rc = 0;
    bool abort_more = false;
    assert(registered->callback(MGMT_EVT_OP_IMG_MGMT_DFU_CHUNK, MGMT_CB_OK, &reject_rc, NULL, &abort_more, NULL, 0) ==
           MGMT_CB_ERROR_RC);
    assert(reject_rc == MGMT_ERR_EINVAL && abort_more);
    pending(MGMT_CB_OK);
    assert(retained.latch_reason && writes == old_writes);
    reset_after_trial = true;
    dfu(MGMT_CB_OK);
    assert(disk.state == STATE_TRIAL && !retained.latch_reason);
    unsigned after_completion = writes;
    safe_mode_persist(); /* Advertising/persistence can finish after DFU. */
    assert(writes == after_completion && disk.state == STATE_TRIAL);
    /* Exact interleaving: durable NVS TRIAL, RAM still latched with intent. */
    memcpy((void *) &retained, &before_ram_clear, sizeof(retained));
    assert(retained.latch_reason && retained.dfu_pending && retained_valid());
    boot(NRF_RESET_RESETREAS_DOG0_MASK, false);
    safe_mode_restore();
    assert(loads == prior_loads + 1 && !retained.latch_reason && retained.count == 1);
    assert(!safe_mode_boot());
    /* A later real crash loop must not be erased by the old durable TRIAL. */
    for (int i = 0; i < CONFIG_OMI_SAFE_MODE_BOOT_LIMIT; ++i) {
        boot(NRF_RESET_RESETREAS_DOG0_MASK, false);
    }
    assert(active);
    safe_mode_restore();
    assert(loads == prior_loads + 1 && retained.latch_reason);

    /* Valid latched RAM skips ALL bootstate reads, even unavailable settings. */
    init_error = -EIO;
    unsigned prior_init_calls = init_calls;
    safe_mode_restore();
    assert(init_calls == prior_init_calls);
    assert(loads == prior_loads + 1 && safe_mode_boot());
    /* A pending upload whose NVS write did not commit must remain SAFE. */
    disk.state = STATE_SAFE;
    retained.dfu_pending = 1;
    retained_seal();
    boot(NRF_RESET_RESETREAS_DOG0_MASK, false);
    init_error = 0;
    safe_mode_restore();
    assert(loads == prior_loads + 2 && safe_mode_boot());

    clean();
    boot(0, true);
    assert(!active && retained.count == 1);
    /* Normal mode retains its policy, but an image-1 completion cannot reset
     * the application trial/count or write TRIAL for it. */
    assert(chunk(1, 2) == MGMT_CB_OK);
    pending(MGMT_CB_OK);
    assert(retained.count == 1 && writes == 0 && !retained.dfu_pending);

    puts("safe-mode: reset/uptime, persistence, CRC/ranges, image targeting and interrupted DFU tests passed");
}
