// Host-side unit tests for the pendant HID dictation protocol core
// (omi/firmware/omi/src/lib/core/hid_dictation_core.c).
//
// Pure C, no Zephyr: compiled and run by scripts/test-host-hid-dictation.sh.
// Mirrors the firmware contract in hid_dictation.h.

#include <stdio.h>
#include <string.h>

#include "../../omi/src/lib/core/hid_dictation.h"

static int failures = 0;
static int checks = 0;

#define CHECK(cond)                                                                                                    \
    do {                                                                                                               \
        checks++;                                                                                                      \
        if (!(cond)) {                                                                                                 \
            failures++;                                                                                                \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                                                     \
        }                                                                                                              \
    } while (0)

static uint8_t text_buf[HID_DICTATION_FRAME_MAX_PAYLOAD * 2];
static struct hid_dictation_ctx ctx;
static struct hid_dictation_limits lim = {.max_text_len = sizeof(text_buf)};

static void fresh(void)
{
    static uint8_t session_clock = 0;
    // Test sessions use small ids (<=100); the clock stays in 201..250 so a
    // fresh context can never accidentally mark the next session a duplicate.
    session_clock = (session_clock % 50) + 201;
    hid_dictation_core_init(&ctx, text_buf, &lim);
    ctx.last_finished_session = session_clock;
}

static uint16_t frame(uint8_t *out, uint8_t session, uint8_t flags, const char *payload)
{
    size_t n = payload ? strlen(payload) : 0;
    out[0] = session;
    out[1] = flags;
    out[2] = (uint8_t) n;
    if (n) {
        memcpy(out + HID_DICTATION_FRAME_HDR_LEN, payload, n);
    }
    return HID_DICTATION_FRAME_HDR_LEN + (uint8_t) n;
}

// --- mapping ---

static void test_mapping_printables(void)
{
    for (int c = 0x20; c <= 0x7E; c++) {
        uint8_t usage = 0;
        bool shift = true;
        CHECK(hid_dictation_char_to_key((uint8_t) c, &usage, &shift));
        CHECK(usage >= 0x04 && usage <= 0x38);
        CHECK(usage != 0x28);                     // Enter is never emitted
        CHECK(!(usage >= 0x39 && usage <= 0x65)); // international keys unused
    }
}

static void test_mapping_rejections(void)
{
    uint8_t usage;
    bool shift;
    const uint8_t bad[] = {0x00, 0x01, '\n', '\r', '\t', 0x1F, 0x7F, 0x80, 0xC3, 0xFF};
    for (size_t i = 0; i < sizeof(bad); i++) {
        usage = 0xFF;
        shift = false;
        CHECK(!hid_dictation_char_to_key(bad[i], &usage, &shift));
        CHECK(!shift);
    }
}

static void test_mapping_known_pairs(void)
{
    struct {
        uint8_t c;
        uint8_t usage;
        bool shift;
    } const pairs[] = {
        {'a', 0x04, false},
        {'z', 0x1D, false},
        {'A', 0x04, true},
        {'1', 0x1E, false},
        {'!', 0x1E, true},
        {'0', 0x27, false},
        {' ', 0x2C, false},
        {'.', 0x37, false},
        {'?', 0x38, true},
        {'\'', 0x34, false},
        {'"', 0x34, true},
    };
    for (size_t i = 0; i < sizeof(pairs) / sizeof(pairs[0]); i++) {
        uint8_t usage = 0;
        bool shift = false;
        CHECK(hid_dictation_char_to_key(pairs[i].c, &usage, &shift));
        CHECK(usage == pairs[i].usage);
        CHECK(shift == pairs[i].shift);
    }
}

// --- validation ---

static void test_text_validation(void)
{
    uint16_t bad = 0xFFFF;
    CHECK(hid_dictation_text_supported((const uint8_t *) "Hello, world!", 13, &bad));
    CHECK(hid_dictation_text_supported((const uint8_t *) "", 0, &bad));

    const uint8_t with_newline[] = "hi\n";
    bad = 0xFFFF;
    CHECK(!hid_dictation_text_supported(with_newline, 3, &bad));
    CHECK(bad == 2);

    const uint8_t utf8[] = {'o', 'k', 0xC3, 0xA9}; // "oké"
    bad = 0xFFFF;
    CHECK(!hid_dictation_text_supported(utf8, 4, &bad));
    CHECK(bad == 2);
}

// --- frames & session machine ---

static void test_single_frame_complete(void)
{
    fresh();
    uint8_t f[HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD];
    uint16_t n = frame(f, 7, HID_DICTATION_FLAG_FINAL, "hi");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_COMPLETE);
    CHECK(ctx.typing_ready);

    uint8_t report[8];
    CHECK(hid_dictation_core_next_key(&ctx, report) == HID_DICTATION_KEY_PRESS);
    CHECK(report[0] == 0 && report[2] == 0x0B); // 'h'
    CHECK(hid_dictation_core_next_key(&ctx, report) == HID_DICTATION_KEY_RELEASE);
    for (int i = 0; i < 8; i++) {
        CHECK(report[i] == 0);
    }
    CHECK(hid_dictation_core_next_key(&ctx, report) == HID_DICTATION_KEY_PRESS);
    CHECK(report[2] == 0x0C); // 'i'
    CHECK(hid_dictation_core_next_key(&ctx, report) == HID_DICTATION_KEY_RELEASE);
    CHECK(hid_dictation_core_next_key(&ctx, report) == HID_DICTATION_KEY_DONE);
    CHECK(ctx.last_finished_session == 7);
    CHECK(ctx.active_session == 0);
}

static void test_multi_frame_then_final(void)
{
    fresh();
    uint8_t f[HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD];
    uint16_t n = frame(f, 9, 0, "one ");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_ACCEPTED);
    n = frame(f, 9, HID_DICTATION_FLAG_FINAL, "two");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_COMPLETE);
    CHECK(ctx.text_len == 7);
    CHECK(memcmp(ctx.text, "one two", 7) == 0);
}

static void test_unsupported_char_rejected_before_typing(void)
{
    fresh();
    uint8_t f[HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD];
    uint16_t n = frame(f, 3, HID_DICTATION_FLAG_FINAL, "ok\tx");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_ERROR);
    CHECK(ctx.last_error == HID_DICTATION_ERR_UNSUPPORTED_CHAR);
    CHECK(ctx.error_detail == 2);
    CHECK(!ctx.typing_ready);
    CHECK(ctx.active_session == 0);
    CHECK(ctx.last_finished_session == 3);

    uint8_t report[8] = {1, 2, 3};
    CHECK(hid_dictation_core_next_key(&ctx, report) == HID_DICTATION_KEY_DONE);
}

static void test_duplicate_session_rejected(void)
{
    fresh();
    uint8_t f[HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD];
    uint16_t n = frame(f, 5, HID_DICTATION_FLAG_FINAL, "again");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_COMPLETE);

    // Drain the typing plan.
    uint8_t report[8];
    while (hid_dictation_core_next_key(&ctx, report) != HID_DICTATION_KEY_DONE) {
        ;
    }
    CHECK(ctx.last_finished_session == 5);

    // Retrying the same session id is refused without state changes.
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_REJECTED);
    CHECK(ctx.last_error == HID_DICTATION_ERR_DUPLICATE_SESSION);
    CHECK(ctx.error_detail == 5);
}

static void test_busy_on_foreign_session(void)
{
    fresh();
    uint8_t f[HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD];
    uint16_t n = frame(f, 11, 0, "par");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_ACCEPTED);

    n = frame(f, 12, HID_DICTATION_FLAG_FINAL, "tial");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_REJECTED);
    CHECK(ctx.last_error == HID_DICTATION_ERR_BUSY);
    CHECK(ctx.error_detail == 11);
    CHECK(ctx.active_session == 11); // foreign frame must not disturb it
    // The live session still completes normally afterwards.
    n = frame(f, 11, HID_DICTATION_FLAG_FINAL, "tial");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_COMPLETE);
}

static void test_cancel(void)
{
    fresh();
    uint8_t f[HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD];
    uint16_t n = frame(f, 21, 0, "stop");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_ACCEPTED);

    n = frame(f, 21, HID_DICTATION_FLAG_CANCEL, NULL);
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_CANCELLED);
    CHECK(ctx.last_error == HID_DICTATION_ERR_CANCELLED);
    CHECK(ctx.active_session == 0);
    CHECK(ctx.last_finished_session == 21);
    CHECK(!ctx.typing_ready);

    // Cancelling with session 0 while idle stays a harmless no-op-style cancel.
    n = frame(f, 0, HID_DICTATION_FLAG_CANCEL, NULL);
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_CANCELLED);
}

static void test_cancel_wrong_session_is_busy(void)
{
    fresh();
    uint8_t f[HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD];
    uint16_t n = frame(f, 31, 0, "xx");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_ACCEPTED);

    n = frame(f, 32, HID_DICTATION_FLAG_CANCEL, NULL);
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_REJECTED);
    CHECK(ctx.last_error == HID_DICTATION_ERR_BUSY);
    CHECK(ctx.active_session == 31); // late cancel must not abort the live one
    // The live session still completes.
    n = frame(f, 31, HID_DICTATION_FLAG_FINAL, "xx");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_COMPLETE);
}

static void test_bad_frames(void)
{
    fresh();
    uint8_t f[HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD];

    // Truncated header.
    CHECK(hid_dictation_core_feed(&ctx, f, 2) == HID_DICTATION_FEED_REJECTED);
    CHECK(ctx.last_error == HID_DICTATION_ERR_BAD_FRAME);

    // len byte disagrees with actual length.
    uint16_t n = frame(f, 41, HID_DICTATION_FLAG_FINAL, "abc");
    f[2] = 9;
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_REJECTED);
    CHECK(ctx.last_error == HID_DICTATION_ERR_BAD_FRAME);

    // Unknown flag bits.
    n = frame(f, 42, HID_DICTATION_FLAG_FINAL, "abc");
    f[1] |= 0x80;
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_REJECTED);
    CHECK(ctx.last_error == HID_DICTATION_ERR_BAD_FRAME);

    // FINAL|CANCEL together.
    n = frame(f, 43, HID_DICTATION_FLAG_CANCEL, NULL);
    f[1] |= HID_DICTATION_FLAG_FINAL;
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_REJECTED);
    CHECK(ctx.last_error == HID_DICTATION_ERR_BAD_FRAME);

    // Data frame with session 0.
    n = frame(f, 0, HID_DICTATION_FLAG_FINAL, "x");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_REJECTED);
    CHECK(ctx.last_error == HID_DICTATION_ERR_BAD_FRAME);
}

static void test_too_long(void)
{
    static struct hid_dictation_limits small = {.max_text_len = 4};
    static uint8_t buf[4];
    hid_dictation_core_init(&ctx, buf, &small);
    ctx.last_finished_session = 60;

    uint8_t f[HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD];
    f[0] = 61;
    f[1] = 0;
    f[2] = 5;
    memset(f + HID_DICTATION_FRAME_HDR_LEN, 'a', 5);
    CHECK(hid_dictation_core_feed(&ctx, f, HID_DICTATION_FRAME_HDR_LEN + 5) == HID_DICTATION_FEED_ERROR);
    CHECK(ctx.last_error == HID_DICTATION_ERR_TOO_LONG);
    CHECK(ctx.active_session == 0);
}

static void test_no_frames_while_typing_ready(void)
{
    fresh();
    uint8_t f[HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD];
    uint16_t n = frame(f, 71, HID_DICTATION_FLAG_FINAL, "a");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_COMPLETE);

    n = frame(f, 72, HID_DICTATION_FLAG_FINAL, "b");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_REJECTED);
    CHECK(ctx.last_error == HID_DICTATION_ERR_BUSY);
    CHECK(ctx.error_detail == 71);
    CHECK(ctx.typing_ready); // the typing session is untouched

    // Even a cancel for the typing session is honoured: typing stops.
    n = frame(f, 71, HID_DICTATION_FLAG_CANCEL, NULL);
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_CANCELLED);
    CHECK(!ctx.typing_ready);
}

static void test_abort_clears_session(void)
{
    fresh();
    uint8_t f[HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD];
    uint16_t n = frame(f, 81, 0, "zz");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_ACCEPTED);

    hid_dictation_core_abort(&ctx);
    CHECK(ctx.active_session == 0);
    CHECK(!ctx.typing_ready);

    // Abort ends the session like any other: replaying its id is refused.
    n = frame(f, 81, HID_DICTATION_FLAG_FINAL, "ok");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_REJECTED);
    CHECK(ctx.last_error == HID_DICTATION_ERR_DUPLICATE_SESSION);

    // A new id works after the abort.
    n = frame(f, 82, HID_DICTATION_FLAG_FINAL, "ok");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_COMPLETE);
}

// A late cancel for a finished session must not disturb the NEXT session.
static void test_late_cancel_does_not_kill_next_session(void)
{
    fresh();
    uint8_t f[HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD];
    uint16_t n = frame(f, 5, HID_DICTATION_FLAG_FINAL, "one");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_COMPLETE);
    uint8_t report[8];
    while (hid_dictation_core_next_key(&ctx, report) != HID_DICTATION_KEY_DONE) {
        ;
    }

    // Session 6 is now mid-flight (receiving).
    n = frame(f, 6, 0, "two");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_ACCEPTED);

    // Stale cancel for session 5 arrives late.
    n = frame(f, 5, HID_DICTATION_FLAG_CANCEL, NULL);
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_REJECTED);
    CHECK(ctx.active_session == 6);
    CHECK(ctx.last_error == HID_DICTATION_ERR_BUSY);

    // Session 6 completes normally.
    n = frame(f, 6, HID_DICTATION_FLAG_FINAL, "two");
    CHECK(hid_dictation_core_feed(&ctx, f, n) == HID_DICTATION_FEED_COMPLETE);
    while (hid_dictation_core_next_key(&ctx, report) != HID_DICTATION_KEY_DONE) {
        ;
    }
    CHECK(ctx.last_finished_session == 6);
}

// Injected-sender tests for the bounded release-all retry policy.
static int release_send_result;
static int release_send_calls;
static int release_sender(void)
{
    release_send_calls++;
    return release_send_result;
}
static int release_delay_calls;
static void release_delay(void)
{
    release_delay_calls++;
}

static void test_release_all_policy(void)
{
    release_send_calls = 0;
    release_delay_calls = 0;
    release_send_result = 0;
    CHECK(hid_dictation_core_release_all(release_sender, release_delay, true, 3) == 0);
    CHECK(release_send_calls == 1);

    // Fails twice, succeeds third: credible release, delays between attempts.
    release_send_calls = 0;
    release_delay_calls = 0;
    int results[] = {0, 0, 0};
    release_send_result = -1;
    CHECK(hid_dictation_core_release_all(release_sender, release_delay, true, 3) == -1);
    CHECK(release_send_calls == 3);
    CHECK(release_delay_calls == 2);

    // Key held + every attempt failed: caller must fail closed.
    CHECK(hid_dictation_core_release_all(NULL, NULL, true, 2) == -1);

    // No key held: a failed send cannot strand anything.
    release_send_calls = 0;
    release_send_result = -12;
    CHECK(hid_dictation_core_release_all(release_sender, release_delay, false, 2) == 0);
    CHECK(release_send_calls == 2);
    (void) results;
}

int main(void)
{
    test_mapping_printables();
    test_mapping_rejections();
    test_mapping_known_pairs();
    test_text_validation();
    test_single_frame_complete();
    test_multi_frame_then_final();
    test_unsupported_char_rejected_before_typing();
    test_duplicate_session_rejected();
    test_busy_on_foreign_session();
    test_cancel();
    test_cancel_wrong_session_is_busy();
    test_bad_frames();
    test_too_long();
    test_no_frames_while_typing_ready();
    test_abort_clears_session();
    test_late_cancel_does_not_kill_next_session();
    test_release_all_policy();

    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
