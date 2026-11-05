package com.friend.ios.phonemic

/**
 * The plain Kotlin stand-ins for the Pigeon types the Flutter app generated
 * (`PhoneMicPigeon.g.kt`): the capture states, the two modes and the start/stop error.
 * The controller, the emitter and the replay vectors use the same names and states.
 */
enum class PhoneMicCaptureState(val raw: Int) {
    IDLE(0),
    STARTING(1),
    RUNNING(2),
    INTERRUPTED(3),
    REBUILDING(4),
}

enum class PhoneMicCaptureMode(val raw: Int) {
    /** PCM16 frames go to the consumer (the listen socket). */
    STREAM(0),

    /** Transcribe later: opus written to a WAL file on the phone. */
    BATCH(1),
}

/** A start or stop that failed: `permission_denied`, `engine_start_failed`, `start_aborted`, ... */
class PhoneMicError(val code: String, override val message: String) : Exception("$code: $message")
