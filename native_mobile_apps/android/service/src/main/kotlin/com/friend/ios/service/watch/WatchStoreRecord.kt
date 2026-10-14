package com.friend.ios.service.watch

import com.friend.ios.core.watch.WatchMessage

// Port of `WatchStore+Record.swift`. "Record with... > Watch": the phone asks the watch to start;
// the watch then opens the recording as if it was started on the wrist (`startRecording` back,
// then its microphone audio).

/** The watch app has reported in (battery or info) since launch. */
val WatchStore.isAvailable: Boolean
    get() = battery != null || info != null

fun WatchStore.startFromPhone() {
    link.send(WatchMessage.StartRecording)
}

val WatchStore.isWatchPaired: Boolean
    get() = link.isWatchPaired

val WatchStore.isWatchAppInstalled: Boolean
    get() = link.isWatchAppInstalled

/** Asks the watch for its battery and details, so `isAvailable` can turn true. */
fun WatchStore.ping() {
    link.send(WatchMessage.RequestBattery)
    link.send(WatchMessage.RequestWatchInfo)
}
