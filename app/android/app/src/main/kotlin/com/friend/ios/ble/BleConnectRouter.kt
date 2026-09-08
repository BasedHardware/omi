package com.friend.ios.ble

/**
 * What a "please connect this device" request must do, given the current native link state.
 *
 * Requests arrive from Dart (`manageDevice` on app start / user reconnect), from
 * CompanionDeviceManager appear events, and from the sticky-service restore after a
 * process kill. Background Mode keeps OmiBleForegroundService — and the GATT link —
 * alive after the Flutter engine dies, so a request routinely arrives for a peripheral
 * that is *already* connected. That case owns the only path a fresh Flutter engine has
 * to learn it is connected, so it must re-emit device-ready rather than be treated as
 * "nothing to do".
 */
internal enum class ConnectRequestAction {
    /** No service instance yet — start it; onStartCommand runs the full manage flow. */
    StartService,

    /** Link is already up: re-emit device-ready so Dart adopts the live connection. */
    ResyncReady,

    /** Link is down: abandon any stuck passive scan and open a fresh GATT connection. */
    Reconnect,
}

internal fun routeConnectRequest(serviceRunning: Boolean, peripheralConnected: Boolean): ConnectRequestAction =
    when {
        !serviceRunning -> ConnectRequestAction.StartService
        peripheralConnected -> ConnectRequestAction.ResyncReady
        else -> ConnectRequestAction.Reconnect
    }
