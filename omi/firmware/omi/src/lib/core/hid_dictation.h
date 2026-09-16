#ifndef HID_DICTATION_H
#define HID_DICTATION_H

// Pendant HID dictation prototype — shared protocol definitions.
//
// Wire contract (mirrored by the mobile app):
//
//   Service 19B10040-E8F2-537E-4F6C-D104768A1214 "Dictation"
//     - Control  19B10041: read/notify = struct hid_dictation_status (LE),
//                 write = 1-byte command (HID_DICTATION_CMD_*).
//     - Text     19B10042: write-with-response = frame
//                 [session:1][flags:1][len:1][payload:len].
//
//   Committed text is typed by the pendant into the host's focused field via
//   the standard BLE HID keyboard service. Only printable US ASCII plus space
//   is supported; anything else is rejected whole, before any key is sent.
//   No Enter/Return is ever typed. All keys are released on completion,
//   cancellation, error, and disconnect.

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define HID_DICTATION_PROTOCOL_VERSION 1

// --- Text frame (written to 19B10042) ---

#define HID_DICTATION_FRAME_HDR_LEN 3 // session, flags, len
#define HID_DICTATION_FRAME_MAX_PAYLOAD 244
#define HID_DICTATION_FLAG_FINAL 0x01  // last frame of this session
#define HID_DICTATION_FLAG_CANCEL 0x02 // abort active session (payload empty)

// Session id 0 is never a valid data session; it means "none".
#define HID_DICTATION_SESSION_NONE 0

// --- Control commands (written to 19B10041) ---

#define HID_DICTATION_CMD_ENABLE 0x01  // opt in to the HID prototype (RAM only, applies on reconnect)
#define HID_DICTATION_CMD_DISABLE 0x02 // opt out (applies on reconnect)

// --- Status (read/notify from 19B10041) ---

enum hid_dictation_state {
    HID_DICTATION_STATE_DISABLED = 0,  // feature not active for this connection
    HID_DICTATION_STATE_IDLE = 1,      // enabled, no session
    HID_DICTATION_STATE_RECEIVING = 2, // frames buffered for active_session
    HID_DICTATION_STATE_TYPING = 3,    // key reports in flight
    HID_DICTATION_STATE_DONE = 4,      // last session completed
    HID_DICTATION_STATE_ERROR = 5,     // last session failed (see last_error)
};

enum hid_dictation_error {
    HID_DICTATION_ERR_NONE = 0,
    HID_DICTATION_ERR_UNSUPPORTED_CHAR = 1,  // error_detail = index in text
    HID_DICTATION_ERR_BUSY = 2,              // session already active (error_detail = active session)
    HID_DICTATION_ERR_BAD_FRAME = 3,         // malformed frame
    HID_DICTATION_ERR_TOO_LONG = 4,          // text exceeds max length
    HID_DICTATION_ERR_TIMEOUT = 5,           // inter-frame or typing-budget timeout
    HID_DICTATION_ERR_NOT_ENABLED = 6,       // HID prototype not active
    HID_DICTATION_ERR_DUPLICATE_SESSION = 7, // session id already used (error_detail = id)
    HID_DICTATION_ERR_NOT_SUBSCRIBED = 8,    // no HID host subscribed to input reports
    HID_DICTATION_ERR_CANCELLED = 9,         // cancelled by app or button
    HID_DICTATION_ERR_INTERNAL = 10,
};

// 10 bytes on the wire, little-endian; chars_typed is the only multi-byte field.
struct hid_dictation_status {
    uint8_t version;               // HID_DICTATION_PROTOCOL_VERSION
    uint8_t state;                 // enum hid_dictation_state
    uint8_t hid_active;            // HID service registered for this connection
    uint8_t hid_pending;           // requested state differs; reconnect to apply
    uint8_t last_error;            // enum hid_dictation_error
    uint8_t error_detail;          // index or session the error refers to
    uint8_t active_session;        // 0 when none
    uint8_t last_finished_session; // last session that ended (any way)
    uint16_t chars_typed;
};

// --- Pure core (host-testable: no Zephyr dependency) ---

struct hid_dictation_limits {
    uint16_t max_text_len;
};

enum hid_dictation_feed_result {
    HID_DICTATION_FEED_ACCEPTED = 0,  // frame buffered, keep receiving
    HID_DICTATION_FEED_COMPLETE = 1,  // final frame validated; typing plan ready
    HID_DICTATION_FEED_CANCELLED = 2, // session cancelled, nothing typed further
    HID_DICTATION_FEED_ERROR = 3,     // ctx->last_error/error_detail set; session aborted
    HID_DICTATION_FEED_REJECTED = 4,  // frame invalid or foreign; last_error set; active session untouched
};

enum hid_dictation_key_event {
    HID_DICTATION_KEY_PRESS = 0,
    HID_DICTATION_KEY_RELEASE = 1,
    HID_DICTATION_KEY_DONE = 2,
};

struct hid_dictation_ctx {
    // configuration (set at init)
    uint16_t max_text_len;
    uint8_t *text; // caller-owned buffer of max_text_len bytes
    // session state
    uint8_t active_session;
    uint8_t last_finished_session;
    uint16_t text_len;
    uint16_t pos;      // typing cursor
    bool key_down;     // next event for current char is a release
    bool typing_ready; // COMPLETE delivered, not yet exhausted
    // error reporting
    uint8_t last_error;
    uint8_t error_detail;
};

void hid_dictation_core_init(struct hid_dictation_ctx *ctx, uint8_t *text_buf, const struct hid_dictation_limits *lim);
void hid_dictation_core_abort(struct hid_dictation_ctx *ctx); // drop session, keep last_finished
enum hid_dictation_feed_result
hid_dictation_core_feed(struct hid_dictation_ctx *ctx, const uint8_t *frame, uint16_t len);
enum hid_dictation_key_event hid_dictation_core_next_key(struct hid_dictation_ctx *ctx, uint8_t report[8]);

// US ASCII (0x20..0x7E) -> HID usage page 0x07 keycode + left-shift modifier.
// Returns false for every byte outside printable ASCII (controls, DEL, >0x7F).

bool hid_dictation_char_to_key(uint8_t c, uint8_t *usage, bool *shift);
// Whole-text variant used for all-or-nothing validation; bad_index = first offender.
bool hid_dictation_text_supported(const uint8_t *text, uint16_t len, uint16_t *bad_index);

// Bounded retry of the zero (release-all) report via an injected sender.
// Returns 0 when the release is credible (a send succeeded, or no key was
// held anyway); -1 when a key may still be held and every attempt failed —
// the caller must then fail closed (drop the link so the host releases keys).
typedef int (*hid_dictation_zero_report_sender_t)(void);
typedef void (*hid_dictation_retry_delay_t)(void);
int hid_dictation_core_release_all(hid_dictation_zero_report_sender_t send_zero,
                                   hid_dictation_retry_delay_t delay,
                                   bool key_held,
                                   uint8_t attempts);
// --- Zephyr runtime API (called from transport.c / button.c) ---
// Only meaningful when CONFIG_OMI_ENABLE_HID_DICTATION=y; the callers guard
// with #ifdef so builds without the feature stay byte-for-byte stock.

struct bt_conn;

int hid_dictation_service_register(void); // after bt_enable(): GATT control plane
void hid_dictation_bt_ready(void);        // post-bt_enable setup (bond reload)
void hid_dictation_on_connected(struct bt_conn *conn);
void hid_dictation_on_disconnected(struct bt_conn *conn); // applies pending enable/disable
bool hid_dictation_hid_active(void);                      // HID service in the GATT table now
bool hid_dictation_wants_adv_restart(void);               // reconnect flow needs fresh advertising
void hid_dictation_button_pressed(void);                  // panic stop: release keys, cancel session

#ifdef __cplusplus
}
#endif

#endif // HID_DICTATION_H
