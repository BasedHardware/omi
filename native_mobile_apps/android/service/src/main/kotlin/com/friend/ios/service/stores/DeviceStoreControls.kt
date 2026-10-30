package com.friend.ios.service.stores

import com.friend.ios.device.OmiGATT

/*
 * Port of `DeviceStore+Controls.swift`: which of My Devices › Controls the connected firmware
 * offers, and one-shot requests to it.
 */

/** Whether the firmware has the haptic motor (assumed when it does not report features). */
val DeviceStore.canFind: Boolean
    get() = connection == DeviceStore.Connection.Connected && (features?.contains(OmiGATT.Features.haptic) ?: true)

/** Brightness slider: only once the firmware said it dims and the value was read. */
val DeviceStore.canDimLED: Boolean
    get() = connection == DeviceStore.Connection.Connected && features?.contains(OmiGATT.Features.ledDimming) == true && ledBrightness != null

val DeviceStore.canSetMicGain: Boolean
    get() = connection == DeviceStore.Connection.Connected && features?.contains(OmiGATT.Features.micGain) == true && micGain != null

/** Asks the connected Omi for its signal strength (Diagnostics polls it while on screen). */
fun DeviceStore.readSignal() {
    if (connection != DeviceStore.Connection.Connected) return
    driverInstance?.readRSSI()
}

/** One pulse on the Omi's motor (question started, answer arriving). */
fun DeviceStore.playHaptic(pulse: OmiGATT.Haptic) {
    if (connection != DeviceStore.Connection.Connected) return
    driverInstance?.write(OmiGATT.Control.Haptic, pulse.payload)
}
