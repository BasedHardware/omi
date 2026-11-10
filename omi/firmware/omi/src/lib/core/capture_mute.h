#ifndef CAPTURE_MUTE_H
#define CAPTURE_MUTE_H

#include <stdbool.h>

/**
 * Pause/mute contract for CV1 (issue #5054).
 *
 * The pendant is the source of truth. BLE disconnect must not resume
 * capture. Only an explicit unmute from the app resumes it. Mute fails
 * closed: an unreadable or unloadable setting, or a mute whose NVS write
 * fails, leaves capture off (3.0.24).
 */

/** Persist mute and apply runtime side effects (SD write pause). */
int capture_mute_set(bool muted);

/** True when the persisted mute flag is set. */
bool capture_mute_is_set(void);

/**
 * True when the pusher may TX or store a packet.
 * Connection state is intentionally ignored — muted stays muted.
 */
bool capture_mute_should_capture(void);

/** Re-apply persisted mute after SD init (boot) or remount. */
void capture_mute_apply_runtime(void);

#endif /* CAPTURE_MUTE_H */
