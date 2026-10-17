package com.friend.ios.service.stores

import com.friend.ios.service.DebugLog

/**
 * Port of `TransferLease.swift`: the grant of background runtime the app holds while a transfer
 * runs.
 *
 * iOS asks for extra time when the app leaves the foreground (`beginBackgroundTask`). Android
 * keeps the process alive with a foreground service of type `dataSync` instead (the app's
 * `TransferForegroundService`), so reading a day of audio off the Omi, or uploading the files that
 * came out of it, is not cut in half when the screen goes off. The system can still take the time
 * back (Android 15's daily `dataSync` budget), which is what [begin]'s expiry callback reports.
 *
 * The app owns the two platform calls; this type owns the refcount, so a read and an upload
 * running at the same time hold one grant, and the grant ends when the last of them does. All
 * calls run on the main thread.
 */
class TransferLease(
    /** Asks for a grant and says whether it was given one; the system calls the callback when it is used up. */
    private val begin: (expire: () -> Unit) -> Boolean,
    /** Hands the grant back. */
    private val end: () -> Unit,
    private val log: DebugLog? = null,
) {
    private var refs = 0

    /** Whether a grant is held right now. */
    var isHeld = false
        private set

    /**
     * A transfer is about to run. The first caller takes the grant; without one the transfer still
     * runs, it is just the first thing the system stops.
     */
    fun acquire() {
        refs += 1
        if (refs != 1) return
        if (!begin { expire() }) {
            refs = 0
            log?.add(DebugLog.Entry.Level.Warning, "sync", "no background time left: the transfer stops if the app leaves")
            return
        }
        isHeld = true
    }

    /** One transfer finished; the last one hands the grant back. */
    fun release() {
        if (refs <= 0) return
        refs -= 1
        if (refs != 0 || !isHeld) return
        endGrant()
    }

    /**
     * The grant ran out. Whatever is running stops where it is; nothing is half-written, because
     * every batch of records is closed before the next one is asked for, and an upload that was
     * cut is still in the queue and goes again at the next launch.
     */
    private fun expire() {
        refs = 0
        if (!isHeld) return
        endGrant()
        log?.add(DebugLog.Entry.Level.Warning, "sync", "background time ran out: the transfer stops here, and resumes at the next launch")
    }

    private fun endGrant() {
        isHeld = false
        end()
    }
}
