package com.friend.ios.batch

import java.util.ArrayDeque

/**
 * Pure session/queue guard used by [OmiBackgroundAudioStreamer]. Callback
 * session tokens make stale WebSocket callbacks testable without an Android
 * device or a live WebSocket; the streamer still revalidates persisted policy
 * while holding its monitor before touching this guard.
 */
internal class OmiBackgroundAudioStreamingLifecycle(private val maxPendingFrames: Int) {
    class Session internal constructor(val generation: Long)

    private val pendingFrames = ArrayDeque<ByteArray>()
    private var nextSessionId = 0L
    private var invalidationGeneration = 0L
    private var activeSession: Session? = null

    val pendingFrameCount: Int
        get() = pendingFrames.size

    fun beginSession(): Session {
        val session = Session(++nextSessionId)
        activeSession = session
        return session
    }

    fun isCurrent(session: Session): Boolean = activeSession == session

    fun currentSession(): Session? = activeSession

    fun currentGeneration(): Long = invalidationGeneration

    fun isGenerationCurrent(generation: Long): Boolean = invalidationGeneration == generation

    fun queueFrame(frame: ByteArray) {
        if (pendingFrames.size >= maxPendingFrames) pendingFrames.removeFirst()
        pendingFrames.addLast(frame.copyOf())
    }

    /** Queue only for the caller's live session; stale callbacks cannot add audio to a later session. */
    fun queueFrameIfCurrent(session: Session, frame: ByteArray): Boolean {
        if (!isCurrent(session)) return false
        queueFrame(frame)
        return true
    }

    /**
     * Drains only for the live session and after the caller has revalidated the
     * current policy. A denied or stale open clears the queue and invalidates
     * the session, so it cannot leak audio captured before the transition.
     */
    fun drainOnOpen(session: Session, policyAllowsStreaming: Boolean): List<ByteArray> {
        if (!policyAllowsStreaming || !isCurrent(session)) {
            invalidateSession()
            return emptyList()
        }

        val queued = pendingFrames.toList()
        pendingFrames.clear()
        return queued
    }

    fun clear() {
        pendingFrames.clear()
    }

    fun invalidateSession() {
        invalidationGeneration += 1
        activeSession = null
        pendingFrames.clear()
    }
}
