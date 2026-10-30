/* Native behavioral harness for the ring-custody pure helpers compiled into
 * the firmware image (src/lib/core/custody.c). Build: make -C tests run. */
#include <errno.h>
#include <stdio.h>
#include <string.h>

#include "../src/lib/core/custody.h"

static int failures;
static int checks;

#define CHECK(cond, msg)                                                                                               \
    do {                                                                                                               \
        checks++;                                                                                                      \
        if (!(cond)) {                                                                                                 \
            failures++;                                                                                                \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, msg);                                                       \
        }                                                                                                              \
    } while (0)

#define CAP 440U

static void test_timestamp(void)
{
    /* Valid RTC in range -> plain UTC. */
    CHECK(omi_record_timestamp(true, 1750000000U, 5000) == 1750000000U, "utc in range");
    CHECK(omi_record_timestamp(true, OMI_TS_MIN_UTC, 0) == OMI_TS_MIN_UTC, "utc min boundary");
    CHECK(omi_record_timestamp(true, OMI_TS_VALUE_MASK, 0) == OMI_TS_VALUE_MASK, "utc max boundary");

    /* RTC invalid / out-of-range -> flagged uptime seconds, never UTC. */
    uint32_t t = omi_record_timestamp(false, 1750000000U, 61234);
    CHECK(t == (OMI_TS_FLAG_UPTIME | 61U), "invalid rtc -> uptime flag");
    t = omi_record_timestamp(true, OMI_TS_MIN_UTC - 1U, 2000);
    CHECK((t & OMI_TS_FLAG_UPTIME) != 0U && (t & OMI_TS_VALUE_MASK) == 2U, "utc below min -> flag");
    t = omi_record_timestamp(true, OMI_TS_VALUE_MASK + 1U, 0);
    CHECK(t == OMI_TS_FLAG_UPTIME, "utc >2038 -> flag, not guessed");
}

static void fill_frame(uint8_t *frame, uint16_t size, uint8_t tag)
{
    for (uint16_t i = 0; i < size; i++) {
        frame[i] = (uint8_t) (tag + i);
    }
}

static void test_packing(void)
{
    uint8_t accum[CAP];
    uint8_t out[CAP];
    omi_live_pack_t p;
    uint32_t s;
    uint16_t b;
    uint8_t frame[300];

    /* Distinct-byte frames: overflow must emit the PREVIOUS record intact and
     * keep the current frame for the next record. */
    omi_live_pack_init(&p, accum, CAP);
    memset(out, 0xEE, sizeof(out));
    fill_frame(frame, 160, 0x10);
    CHECK(!omi_live_pack_frame(&p, frame, 160, 7, 100, out, &s, &b), "frame1 packs, no record yet");
    fill_frame(frame, 160, 0x20);
    CHECK(!omi_live_pack_frame(&p, frame, 160, 7, 200, out, &s, &b), "frame2 packs, no record yet");
    fill_frame(frame, 200, 0x30);
    CHECK(omi_live_pack_frame(&p, frame, 200, 7, 300, out, &s, &b), "overflow submits previous record");
    CHECK(s == 7U && b == 200U, "overflow boundary is previous frame, not current");
    /* out holds the first two frames byte-for-byte, zero-padded. */
    CHECK(out[0] == 160 && out[1] == 0x10 && out[160] == 0x10 + 159, "first frame bytes intact");
    CHECK(out[161] == 160 && out[162] == 0x20 && out[321] == 0x20 + 159, "second frame bytes intact");
    CHECK(out[322] == 0 && out[439] == 0, "padding zeroed");

    /* Flush: the third frame lands in a NEW record with its own bytes -- the
     * emitted record was a copy, not the live accumulation buffer. */
    memset(out, 0xEE, sizeof(out));
    CHECK(omi_live_pack_flush(&p, out, &s, &b), "flush emits pending record");
    CHECK(s == 7U && b == 300U, "flushed record carries current boundary");
    CHECK(out[0] == 200 && out[1] == 0x30 && out[200] == 0x30 + 199, "current frame in next record");
    CHECK(out[201] == 0 && out[439] == 0, "next record padded");

    /* Effective capacity is 439: the last byte is always a zero terminator so
     * the app parser (stops when a frame would reach byte 440) sees it. */
    omi_live_pack_init(&p, accum, CAP);
    omi_live_pack_frame(&p, frame, 160, 9, 50, out, &s, &b);
    omi_live_pack_frame(&p, frame, 160, 9, 60, out, &s, &b);
    fill_frame(frame, 116, 0x55); /* 161+161+117 = 439: exact fit */
    memset(out, 0xEE, sizeof(out));
    CHECK(omi_live_pack_frame(&p, frame, 116, 9, 77, out, &s, &b), "439 exact fit submits");
    CHECK(s == 9U && b == 77U, "exact fit boundary is current frame");
    CHECK(p.offset == 0U && out[439] == 0, "exact fit leaves zero terminator");

    /* One byte more must overflow, not squeeze to byte 440. */
    omi_live_pack_init(&p, accum, CAP);
    omi_live_pack_frame(&p, frame, 160, 9, 50, out, &s, &b);
    omi_live_pack_frame(&p, frame, 160, 9, 60, out, &s, &b);
    fill_frame(frame, 117, 0x66); /* would total 440 -> overflows at 439 */
    CHECK(omi_live_pack_frame(&p, frame, 117, 9, 88, out, &s, &b), "440-fit overflows");
    CHECK(b == 60U, "overflow emitted previous boundary");
    CHECK(p.offset == 118U, "overflowed frame pending, not skipped");

    /* Session mixing: second frame different session -> record session 0. */
    omi_live_pack_init(&p, accum, CAP);
    omi_live_pack_frame(&p, frame, 100, 5, 10, out, &s, &b);
    omi_live_pack_frame(&p, frame, 100, 6, 20, out, &s, &b);
    CHECK(omi_live_pack_flush(&p, out, &s, &b), "flush partial record");
    CHECK(s == 0U && b == 20U, "mixed-session record ineligible, boundary kept");

    /* Ineligible (session 0) frame poisons the whole record. */
    omi_live_pack_init(&p, accum, CAP);
    omi_live_pack_frame(&p, frame, 100, 5, 10, out, &s, &b);
    omi_live_pack_frame(&p, frame, 100, 0, 20, out, &s, &b);
    omi_live_pack_flush(&p, out, &s, &b);
    CHECK(s == 0U, "ineligible frame poisons record");

    /* invalidate_next marks the record containing the next frame. */
    omi_live_pack_init(&p, accum, CAP);
    p.invalidate_next = true;
    omi_live_pack_frame(&p, frame, 100, 5, 10, out, &s, &b);
    omi_live_pack_frame(&p, frame, 100, 5, 20, out, &s, &b);
    omi_live_pack_flush(&p, out, &s, &b);
    CHECK(s == 0U, "invalidate_next suppresses record");
    CHECK(!p.invalidate_next, "invalidate consumed once");

    /* Flush on empty pack produces nothing; frames >255 rejected. */
    CHECK(!omi_live_pack_flush(&p, out, &s, &b), "empty flush no-op");
    uint8_t big[256];
    memset(big, 1, sizeof(big));
    CHECK(!omi_live_pack_frame(&p, big, 256, 5, 10, out, &s, &b), "oversized frame rejected");
}

static void test_mark_floor(void)
{
    omi_live_mark_t m;
    uint64_t seq;
    uint16_t idx;
    uint32_t sess;

    /* Eligible run, but read_seq still below the floor (unread offline
     * backlog): mark must NOT be emitted even though committed. */
    omi_live_mark_reset(&m);
    omi_live_mark_note_record(&m, 10, 7, 100);
    omi_live_mark_note_record(&m, 11, 7, 200);
    CHECK(!omi_live_mark_eval(&m, 12, 5, &seq, &idx, &sess), "no mark while backlog unread");

    /* Once the backlog is advanced past the floor, the mark covers the run. */
    CHECK(omi_live_mark_eval(&m, 12, 10, &seq, &idx, &sess), "mark after floor advanced");
    CHECK(seq == 12U && idx == 200U && sess == 7U, "mark covers last eligible record");

    /* The candidate itself must be committed first. */
    omi_live_mark_reset(&m);
    omi_live_mark_note_record(&m, 0, 3, 8);
    CHECK(!omi_live_mark_eval(&m, 0, 0, &seq, &idx, &sess), "no mark before commit");

    /* Ineligible record breaks the run: floor restarts at next eligible. */
    omi_live_mark_reset(&m);
    omi_live_mark_note_record(&m, 10, 7, 100);
    omi_live_mark_note_record(&m, 11, 0, 150); /* failed send -> ineligible */
    omi_live_mark_note_record(&m, 12, 7, 200);
    CHECK(!omi_live_mark_eval(&m, 13, 10, &seq, &idx, &sess), "gap suppresses earlier mark");
    CHECK(omi_live_mark_eval(&m, 13, 12, &seq, &idx, &sess), "run restarts after gap");
    CHECK(seq == 13U && idx == 200U, "mark covers only post-gap record");

    /* Session change restarts the run at the new session's first record. */
    omi_live_mark_reset(&m);
    omi_live_mark_note_record(&m, 5, 7, 10);
    omi_live_mark_note_record(&m, 6, 8, 20);
    CHECK(!omi_live_mark_eval(&m, 7, 5, &seq, &idx, &sess), "session change resets floor");
    CHECK(omi_live_mark_eval(&m, 7, 6, &seq, &idx, &sess), "new session floor ok");
    CHECK(sess == 8U, "mark carries new session");
}

static void test_advance_eval(void)
{
    /* Legacy advance (no id check). */
    CHECK(omi_advance_eval(5, 10, 99, 0, false, 7) == 0, "advance in range");
    CHECK(omi_advance_eval(5, 10, 99, 0, false, 5) == 0, "advance == read no-op");
    CHECK(omi_advance_eval(5, 10, 99, 0, false, 3) == 0, "idempotent: below read ok");
    CHECK(omi_advance_eval(5, 10, 99, 0, false, 11) == -ERANGE, "above write rejected");

    /* Id-scoped advance. */
    CHECK(omi_advance_eval(5, 10, 99, 42, true, 7) == -ESTALE, "stale ring id rejected");
    CHECK(omi_advance_eval(5, 10, 99, 42, true, 5) == -ESTALE, "stale ring id rejected even for no-op seq");
    CHECK(omi_advance_eval(5, 10, 99, 99, true, 9) == 0, "matching id advances");
}

int main(void)
{
    test_timestamp();
    test_packing();
    test_mark_floor();
    test_advance_eval();

    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
