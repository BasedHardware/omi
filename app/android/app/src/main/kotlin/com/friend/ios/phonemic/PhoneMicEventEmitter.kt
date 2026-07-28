package com.friend.ios.phonemic

import android.os.Handler

/**
 * Monotonic capture epoch shared between the controller (writer) and the event
 * emitter (reader). Every frame carries the epoch it was captured under; the
 * emitter drops any frame whose epoch is no longer the active one. This is what
 * guarantees no frame is delivered after stop() and none crosses a rebuild.
 *
 * All three methods AND the emitter's read of the epoch run on the main thread
 * only, so the fields are plain `Long` — no atomics or locks (simpler than the
 * iOS side's os_unfair_lock, which it needs only because its tap runs off-main).
 */
class PhoneMicGeneration {
    private var counter: Long = 0L
    private var active: Long = 0L

    /** Starts a new capture epoch and returns it. */
    fun advance(): Long {
        counter += 1L
        active = counter
        return counter
    }

    /** Ends the current epoch: every in-flight frame becomes droppable. */
    fun invalidate() {
        active = 0L
    }

    fun matches(epoch: Long): Boolean = epoch != 0L && active == epoch
}

/**
 * The only object that touches [PhoneMicFlutterApi]. Serializes every outbound
 * call onto the main thread and epoch-gates frames. Because frames and state
 * events funnel FIFO through the main [Handler], an epoch invalidation that
 * happens-before a state emission means no frame can arrive after that state.
 *
 * Invariants (load-bearing — an "optimization" here breaks the no-frame-after-stop
 * guarantee):
 *
 *  (a) The frame epoch-gate is evaluated ON MAIN at emit time: [emitFrame] posts a
 *      runnable that checks [generation] INSIDE the posted block, never at call
 *      time — otherwise a frame that passed the gate could still be queued behind
 *      the invalidation.
 *  (b) EVERY emission (frames, all states including IDLE, errors, progress) is an
 *      unconditional `mainHandler.post` — there is NO "already on main, call inline"
 *      fast-path. Posted order is delivery order; an inline state would jump the
 *      queue ahead of already-posted frames. Separately, Pigeon FlutterApi sends
 *      off the main thread throw in FlutterJNI, so posting is correctness, not style.
 *  (c) [PhoneMicGeneration]'s fields are touched only on main, hence plain (no atomics).
 *
 * Every send is null-guarded via [api], read inside the posted runnable: [unbind]
 * nulls it on main, so any runnable posted before unbind but run after it drops
 * harmlessly (the engine-death path).
 */
class PhoneMicEventEmitter(private val mainHandler: Handler) {
    val generation = PhoneMicGeneration()

    /** Touched on main only (bind/unbind and every posted runnable run on main). */
    private var api: PhoneMicFlutterApi? = null

    fun bind(api: PhoneMicFlutterApi) {
        this.api = api
    }

    fun unbind() {
        this.api = null
    }

    fun emitFrame(data: ByteArray, epoch: Long, sessionId: Long) {
        mainHandler.post {
            if (!generation.matches(epoch)) return@post
            api?.onAudioFrame(data, sessionId) {}
        }
    }

    fun emitState(state: PhoneMicCaptureState, sessionId: Long) {
        mainHandler.post { api?.onStateChanged(state, sessionId) {} }
    }

    fun emitError(code: String, message: String, sessionId: Long) {
        mainHandler.post { api?.onCaptureError(code, message, sessionId) {} }
    }

    fun emitBatchProgress(seconds: Double, sessionId: Long) {
        mainHandler.post { api?.onBatchProgress(seconds, sessionId) {} }
    }
}
