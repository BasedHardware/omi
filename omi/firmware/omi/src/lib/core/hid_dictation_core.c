#include <string.h>

#include "hid_dictation.h"

// Pure protocol core: ASCII→HID mapping, frame parsing, session state machine.
// No Zephyr dependency — compiled into the firmware AND the host test harness.

// --- US ASCII (0x20..0x7E) → HID usage page 0x07, US keyboard layout ---

#define ASCII_FIRST 0x20
#define ASCII_LAST 0x7E

#define KEY_LEFT_SHIFT 0x02

// HID usage idents for keys we emit.
#define USAGE_A 0x04
#define USAGE_1 0x1E
#define USAGE_2 0x1F
#define USAGE_3 0x20
#define USAGE_4 0x21
#define USAGE_5 0x22
#define USAGE_6 0x23
#define USAGE_7 0x24
#define USAGE_8 0x25
#define USAGE_9 0x26
#define USAGE_0 0x27
#define USAGE_SPACE 0x2C
#define USAGE_MINUS 0x2D
#define USAGE_EQUAL 0x2E
#define USAGE_LBRACKET 0x2F
#define USAGE_RBRACKET 0x30
#define USAGE_BACKSLASH 0x31
#define USAGE_SEMICOLON 0x33
#define USAGE_APOSTROPHE 0x34
#define USAGE_GRAVE 0x35
#define USAGE_COMMA 0x36
#define USAGE_PERIOD 0x37
#define USAGE_SLASH 0x38

bool hid_dictation_char_to_key(uint8_t c, uint8_t *usage, bool *shift)
{
    if (usage == NULL || shift == NULL) {
        return false;
    }

    *shift = false;

    if (c >= 'a' && c <= 'z') {
        *usage = USAGE_A + (c - 'a');
        return true;
    }
    if (c >= 'A' && c <= 'Z') {
        *usage = USAGE_A + (c - 'A');
        *shift = true;
        return true;
    }
    if (c >= '1' && c <= '9') {
        *usage = USAGE_1 + (c - '1');
        return true;
    }

    switch (c) {
    case ' ':
        *usage = USAGE_SPACE;
        return true;
    case '0':
        *usage = USAGE_0;
        return true;
    case '!':
        *usage = USAGE_1;
        *shift = true;
        return true;
    case '@':
        *usage = USAGE_2;
        *shift = true;
        return true;
    case '#':
        *usage = USAGE_3;
        *shift = true;
        return true;
    case '$':
        *usage = USAGE_4;
        *shift = true;
        return true;
    case '%':
        *usage = USAGE_5;
        *shift = true;
        return true;
    case '^':
        *usage = USAGE_6;
        *shift = true;
        return true;
    case '&':
        *usage = USAGE_7;
        *shift = true;
        return true;
    case '*':
        *usage = USAGE_8;
        *shift = true;
        return true;
    case '(':
        *usage = USAGE_9;
        *shift = true;
        return true;
    case ')':
        *usage = USAGE_0;
        *shift = true;
        return true;
    case '-':
    case '_':
        *usage = USAGE_MINUS;
        *shift = (c == '_');
        return true;
    case '=':
    case '+':
        *usage = USAGE_EQUAL;
        *shift = (c == '+');
        return true;
    case '[':
    case '{':
        *usage = USAGE_LBRACKET;
        *shift = (c == '{');
        return true;
    case ']':
    case '}':
        *usage = USAGE_RBRACKET;
        *shift = (c == '}');
        return true;
    case '\\':
    case '|':
        *usage = USAGE_BACKSLASH;
        *shift = (c == '|');
        return true;
    case ';':
    case ':':
        *usage = USAGE_SEMICOLON;
        *shift = (c == ':');
        return true;
    case '\'':
    case '"':
        *usage = USAGE_APOSTROPHE;
        *shift = (c == '"');
        return true;
    case '`':
    case '~':
        *usage = USAGE_GRAVE;
        *shift = (c == '~');
        return true;
    case ',':
    case '<':
        *usage = USAGE_COMMA;
        *shift = (c == '<');
        return true;
    case '.':
    case '>':
        *usage = USAGE_PERIOD;
        *shift = (c == '>');
        return true;
    case '/':
    case '?':
        *usage = USAGE_SLASH;
        *shift = (c == '?');
        return true;
    default:
        // Controls (incl. \n, \t, Enter), DEL, and everything past 0x7E are
        // deliberately unsupported: rejected explicitly, never transliterated.
        return false;
    }
}

bool hid_dictation_text_supported(const uint8_t *text, uint16_t len, uint16_t *bad_index)
{
    for (uint16_t i = 0; i < len; i++) {
        uint8_t usage;
        bool shift;
        if (!hid_dictation_char_to_key(text[i], &usage, &shift)) {
            if (bad_index != NULL) {
                *bad_index = i;
            }
            return false;
        }
    }
    return true;
}

// --- Session state machine ---

static void set_error(struct hid_dictation_ctx *ctx, uint8_t error, uint8_t detail)
{
    ctx->last_error = error;
    ctx->error_detail = detail;
}

static void finish_session(struct hid_dictation_ctx *ctx)
{
    if (ctx->active_session != HID_DICTATION_SESSION_NONE) {
        ctx->last_finished_session = ctx->active_session;
        ctx->active_session = HID_DICTATION_SESSION_NONE;
    }
}

static void abort_with_error(struct hid_dictation_ctx *ctx, uint8_t error, uint8_t detail)
{
    set_error(ctx, error, detail);
    finish_session(ctx);
    ctx->text_len = 0;
    ctx->pos = 0;
    ctx->key_down = false;
    ctx->typing_ready = false;
}

void hid_dictation_core_init(struct hid_dictation_ctx *ctx, uint8_t *text_buf, const struct hid_dictation_limits *lim)
{
    memset(ctx, 0, sizeof(*ctx));
    ctx->text = text_buf;
    ctx->max_text_len = lim->max_text_len;
    ctx->last_error = HID_DICTATION_ERR_NONE;
}

void hid_dictation_core_abort(struct hid_dictation_ctx *ctx)
{
    finish_session(ctx);
    ctx->text_len = 0;
    ctx->pos = 0;
    ctx->key_down = false;
    ctx->typing_ready = false;
}

static bool session_open_or_start(struct hid_dictation_ctx *ctx, uint8_t session)
{
    if (ctx->active_session == session) {
        return true; // continuing frame stream
    }
    if (ctx->active_session != HID_DICTATION_SESSION_NONE) {
        set_error(ctx, HID_DICTATION_ERR_BUSY, ctx->active_session);
        return false;
    }
    if (session == ctx->last_finished_session) {
        set_error(ctx, HID_DICTATION_ERR_DUPLICATE_SESSION, session);
        return false;
    }
    ctx->active_session = session;
    ctx->text_len = 0;
    return true;
}

static enum hid_dictation_feed_result feed_frame(struct hid_dictation_ctx *ctx, const uint8_t *frame, uint16_t len)
{
    ctx->last_error = HID_DICTATION_ERR_NONE;
    ctx->error_detail = 0;

    if (len < HID_DICTATION_FRAME_HDR_LEN) {
        set_error(ctx, HID_DICTATION_ERR_BAD_FRAME, 0);
        return HID_DICTATION_FEED_REJECTED;
    }

    uint8_t session = frame[0];
    uint8_t flags = frame[1];
    uint8_t payload_len = frame[2];

    if (payload_len > HID_DICTATION_FRAME_MAX_PAYLOAD || (uint16_t) payload_len + HID_DICTATION_FRAME_HDR_LEN != len) {
        set_error(ctx, HID_DICTATION_ERR_BAD_FRAME, 0);
        return HID_DICTATION_FEED_REJECTED;
    }
    if ((flags & ~(HID_DICTATION_FLAG_FINAL | HID_DICTATION_FLAG_CANCEL)) != 0) {
        set_error(ctx, HID_DICTATION_ERR_BAD_FRAME, 1);
        return HID_DICTATION_FEED_REJECTED;
    }
    bool is_final = (flags & HID_DICTATION_FLAG_FINAL) != 0;
    bool is_cancel = (flags & HID_DICTATION_FLAG_CANCEL) != 0;
    if (is_final && is_cancel) {
        set_error(ctx, HID_DICTATION_ERR_BAD_FRAME, 1);
        return HID_DICTATION_FEED_REJECTED;
    }

    if (is_cancel) {
        // Cancel targets the active session: exact id, or 0 = "whatever runs".
        // A cancel naming any OTHER session is a stale, late cancel from the
        // phone: it must not disturb the live session in any way.
        if (ctx->active_session != HID_DICTATION_SESSION_NONE && session != HID_DICTATION_SESSION_NONE &&
            session != ctx->active_session) {
            set_error(ctx, HID_DICTATION_ERR_BUSY, session);
            return HID_DICTATION_FEED_REJECTED;
        }
        uint8_t cancelled = ctx->active_session;
        set_error(ctx, HID_DICTATION_ERR_CANCELLED, cancelled);
        finish_session(ctx);
        ctx->text_len = 0;
        ctx->pos = 0;
        ctx->key_down = false;
        ctx->typing_ready = false;
        return HID_DICTATION_FEED_CANCELLED;
    }

    if (ctx->typing_ready) {
        // A validated session is queued for/under typing; no preemption.
        // The frame belongs to neither the typing session nor a new one.
        set_error(ctx, HID_DICTATION_ERR_BUSY, ctx->active_session);
        return HID_DICTATION_FEED_REJECTED;
    }

    if (session == HID_DICTATION_SESSION_NONE) {
        set_error(ctx, HID_DICTATION_ERR_BAD_FRAME, 0);
        return HID_DICTATION_FEED_REJECTED;
    }

    if (!session_open_or_start(ctx, session)) {
        // Foreign or duplicate session: refused without touching whatever
        // the ctx currently owns (session_open_or_start only set the error).
        return HID_DICTATION_FEED_REJECTED;
    }

    if ((uint32_t) ctx->text_len + payload_len > ctx->max_text_len) {
        abort_with_error(ctx, HID_DICTATION_ERR_TOO_LONG, session);
        return HID_DICTATION_FEED_ERROR;
    }

    memcpy(ctx->text + ctx->text_len, frame + HID_DICTATION_FRAME_HDR_LEN, payload_len);
    ctx->text_len += payload_len;

    if (!is_final) {
        return HID_DICTATION_FEED_ACCEPTED;
    }

    uint16_t bad_index = 0;
    if (!hid_dictation_text_supported(ctx->text, ctx->text_len, &bad_index)) {
        abort_with_error(ctx, HID_DICTATION_ERR_UNSUPPORTED_CHAR, (uint8_t) bad_index);
        return HID_DICTATION_FEED_ERROR;
    }

    ctx->pos = 0;
    ctx->key_down = false;
    ctx->typing_ready = true;
    return HID_DICTATION_FEED_COMPLETE;
}

enum hid_dictation_feed_result
hid_dictation_core_feed(struct hid_dictation_ctx *ctx, const uint8_t *frame, uint16_t len)
{
    const uint8_t active = ctx->active_session;
    const uint8_t error = ctx->last_error;
    const uint8_t detail = ctx->error_detail;
    enum hid_dictation_feed_result result = feed_frame(ctx, frame, len);
    if (result == HID_DICTATION_FEED_REJECTED && active != HID_DICTATION_SESSION_NONE) {
        // A rejected foreign write must not turn the current session's DONE
        // status into an error, even when it arrives after the final frame.
        ctx->last_error = error;
        ctx->error_detail = detail;
    }
    return result;
}

enum hid_dictation_key_event hid_dictation_core_next_key(struct hid_dictation_ctx *ctx, uint8_t report[8])
{
    if (!ctx->typing_ready || report == NULL) {
        return HID_DICTATION_KEY_DONE;
    }

    if (ctx->pos >= ctx->text_len) {
        ctx->typing_ready = false;
        finish_session(ctx);
        return HID_DICTATION_KEY_DONE;
    }

    memset(report, 0, 8);
    uint8_t usage;
    bool shift;

    if (!ctx->key_down) {
        if (!hid_dictation_char_to_key(ctx->text[ctx->pos], &usage, &shift)) {
            // Buffer changed underneath us; stop typing, keys already released.
            ctx->typing_ready = false;
            finish_session(ctx);
            return HID_DICTATION_KEY_DONE;
        }
        report[0] = shift ? KEY_LEFT_SHIFT : 0;
        report[2] = usage;
        ctx->key_down = true;
        return HID_DICTATION_KEY_PRESS;
    }

    // Zero report releases everything pressed in the previous event.
    ctx->key_down = false;
    ctx->pos++;
    return HID_DICTATION_KEY_RELEASE;
}

int hid_dictation_core_release_all(hid_dictation_zero_report_sender_t send_zero,
                                   hid_dictation_retry_delay_t delay,
                                   bool key_held,
                                   uint8_t attempts)
{
    if (attempts == 0) {
        attempts = 1;
    }
    for (uint8_t i = 0; i < attempts; i++) {
        if (i > 0 && delay != NULL) {
            delay();
        }
        if (send_zero != NULL && send_zero() == 0) {
            return 0;
        }
    }
    // No key was held: a failed queue attempt cannot leave a stuck key.
    return key_held ? -1 : 0;
}
