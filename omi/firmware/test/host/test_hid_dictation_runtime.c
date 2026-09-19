// Execute the production GATT/workqueue glue with deterministic I/O failures.
// Including the translation unit gives tests access to registered callbacks;
// all production logic is unchanged. See hid_runtime_fakes.h for test boundaries.
// clang-format off
#include "hid_runtime_fakes.h"
#include "../../omi/src/lib/core/hid_dictation.c"
// clang-format on

static struct bt_conn phone;
static unsigned scenarios;
#define CHECK(c) assert(c)

static ssize_t command(uint8_t cmd)
{
    return dictation_control_write(&phone, NULL, &cmd, 1, 0, 0);
}
static ssize_t frame(uint8_t id, uint8_t flags, const char *text)
{
    size_t n = strlen(text);
    uint8_t bytes[247] = {id, flags, (uint8_t) n};
    CHECK(n <= 244);
    memcpy(bytes + 3, text, n);
    return dictation_text_write(&phone, NULL, bytes, n + 3, 0, 0);
}
static void run_work(struct k_work_delayable *w)
{
    CHECK(w->pending);
    if (fake_now < w->due)
        fake_now = w->due;
    w->pending = false;
    w->work.handler(&w->work);
}
static void drain(void)
{
    unsigned limit = 600;
    while (typing_work.pending && limit--)
        run_work(&typing_work);
    CHECK(!typing_work.pending);
}
static void reset(void)
{
    // Fresh process/BSS equivalent, not a claim about physical reset recovery.
    if (conn_ref)
        bt_conn_unref(conn_ref);
    conn_ref = NULL;
    hid_wanted = false;
    hid_registered = false;
    report_key_held = false;
    typing_work.pending = false;
    frame_timeout_work.pending = false;
    fake_init_error = fake_uninit_error = fake_send_error = 0;
    fake_failures_left = fake_send_attempts = fake_report_count = fake_disconnects = fake_notifications = fake_now = 0;
    CHECK(phone.refs == 0);
    CHECK(dictation_lock.depth == 0);
    CHECK(hid_dictation_service_register() == 0);
    hid_dictation_on_connected(&phone);
    scenarios++;
}
static void enable(void)
{
    CHECK(command(HID_DICTATION_CMD_ENABLE) == 1);
    CHECK(!hid_dictation_hid_active());
    CHECK(current_status().hid_pending);
    hid_dictation_on_disconnected(&phone);
    hid_dictation_on_connected(&phone);
    CHECK(hid_dictation_hid_active());
    CHECK(!current_status().hid_pending);
}
static void fail_sends(unsigned n, int error)
{
    fake_failures_left = n;
    fake_send_error = error;
}
static void released(void)
{
    const uint8_t zero[8] = {0};
    CHECK(fake_report_count > 0);
    CHECK(memcmp(fake_reports[fake_report_count - 1], zero, 8) == 0);
    CHECK(!report_key_held);
}
int main(void)
{
    reset();
    CHECK(!hid_dictation_hid_active());
    CHECK(frame(1, 1, "abc") < 0);
    CHECK(fake_send_attempts == 0);
    enable();
    CHECK(frame(1, 0, "a") == 4);
    CHECK(fake_send_attempts == 0);
    CHECK(frame(1, 1, "B") == 4);
    drain();
    CHECK(fake_report_count == 4);
    released();
    CHECK(fake_reports[0][2] == 4);
    CHECK(fake_reports[2][0] == 2);
    CHECK(fake_reports[2][2] == 5);
    CHECK(current_status().state == HID_DICTATION_STATE_DONE);
    CHECK(current_status().chars_typed == 2);

    reset();
    enable();
    CHECK(frame(2, 0, "abc") == 6);
    run_work(&frame_timeout_work);
    CHECK(current_status().last_error == HID_DICTATION_ERR_TIMEOUT);
    CHECK(!typing_work.pending);
    for (unsigned i = 0; i < fake_report_count; i++)
        CHECK(fake_reports[i][2] == 0);

    reset();
    enable();
    CHECK(frame(3, 1, "a\n") == 5);
    CHECK(current_status().last_error == HID_DICTATION_ERR_UNSUPPORTED_CHAR);
    for (unsigned i = 0; i < fake_report_count; i++)
        CHECK(fake_reports[i][2] == 0);

    // Every report boundary: cancellation and disconnect cannot replay a prefix.
    for (unsigned step = 0; step < 6; step++) {
        reset();
        enable();
        CHECK(frame(4, 1, "abc") == 6);
        for (unsigned i = 0; i < step; i++)
            run_work(&typing_work);
        hid_dictation_button_pressed();
        unsigned after = fake_report_count;
        drain();
        CHECK(fake_report_count == after);
        released();
        CHECK(current_status().last_error == HID_DICTATION_ERR_CANCELLED);
        CHECK(frame(4, 1, "abc") < 0);
    }
    for (unsigned step = 0; step < 6; step++) {
        reset();
        enable();
        CHECK(frame(5, 1, "abc") == 6);
        for (unsigned i = 0; i < step; i++)
            run_work(&typing_work);
        hid_dictation_on_disconnected(&phone);
        CHECK(phone.refs == 0);
        hid_dictation_on_connected(&phone);
        unsigned after = fake_report_count;
        drain();
        CHECK(fake_report_count == after);
        CHECK(current_status().active_session == 0);
        CHECK(current_status().state == HID_DICTATION_STATE_IDLE);
    }

    reset();
    enable();
    CHECK(frame(6, 1, "abc") == 6);
    run_work(&typing_work);
    CHECK(frame(7, HID_DICTATION_FLAG_CANCEL, "") < 0);
    CHECK(report_key_held);
    CHECK(current_status().active_session == 6);
    CHECK(frame(6, HID_DICTATION_FLAG_CANCEL, "") == 3);
    drain();
    released();

    reset();
    enable();
    CHECK(frame(8, 1, "abc") == 6);
    fail_sends(4, -EACCES);
    drain();
    CHECK(current_status().last_error == HID_DICTATION_ERR_NOT_SUBSCRIBED);
    CHECK(fake_report_count == 0);
    // Conservative fail-closed behavior when even the release cannot be queued.
    CHECK(fake_disconnects == 1);

    // A failed release must remember the accepted press even after core cursor advance.
    for (unsigned failures = 1; failures <= 4; failures++) {
        reset();
        enable();
        CHECK(frame(9, 1, "abc") == 6);
        run_work(&typing_work);
        CHECK(report_key_held);
        fail_sends(failures, -ENOMEM);
        drain();
        CHECK(current_status().last_error == HID_DICTATION_ERR_INTERNAL);
        if (failures < 4) {
            released();
            CHECK(fake_disconnects == 0);
        } else {
            CHECK(fake_disconnects == 1);
            CHECK(fake_report_count == 1);
        }
    }

    reset();
    enable();
    CHECK(frame(10, 1, "abc") == 6);
    run_work(&typing_work);
    fake_now += 30001;
    run_work(&typing_work);
    released();
    CHECK(current_status().last_error == HID_DICTATION_ERR_TIMEOUT);

    reset();
    enable();
    CHECK(frame(11, 1, "abc") == 6);
    run_work(&typing_work);
    CHECK(command(HID_DICTATION_CMD_DISABLE) == 1);
    released();
    CHECK(frame(12, 1, "x") < 0);
    hid_dictation_on_disconnected(&phone);
    hid_dictation_on_connected(&phone);
    CHECK(!hid_dictation_hid_active());

    reset();
    fake_init_error = -ENOMEM;
    CHECK(command(HID_DICTATION_CMD_ENABLE) == 1);
    hid_dictation_on_disconnected(&phone);
    hid_dictation_on_connected(&phone);
    CHECK(!hid_dictation_hid_active());
    CHECK(current_status().hid_pending);
    CHECK(frame(13, 1, "x") < 0);

    reset();
    enable();
    fake_uninit_error = -EBUSY;
    CHECK(command(HID_DICTATION_CMD_DISABLE) == 1);
    hid_dictation_on_disconnected(&phone);
    hid_dictation_on_connected(&phone);
    CHECK(hid_dictation_hid_active());
    CHECK(current_status().hid_pending);
    CHECK(frame(14, 1, "x") < 0);
    fake_uninit_error = 0;
    hid_dictation_on_disconnected(&phone);
    CHECK(!hid_dictation_hid_active());

    reset();
    CHECK(!hid_dictation_hid_active());
    CHECK(!hid_dictation_wants_adv_restart());
    hid_dictation_on_disconnected(&phone);
    CHECK(phone.refs == 0);
    printf("HID runtime fault harness: %u scenarios passed (mocked kernel/BLE, no hardware)\n", scenarios);
    return 0;
}
