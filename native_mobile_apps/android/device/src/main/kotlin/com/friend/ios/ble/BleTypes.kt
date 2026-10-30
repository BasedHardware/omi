package com.friend.ios.ble

/** A scan result (was Pigeon's `BlePeripheral`); `uuid` is the uppercase Bluetooth address. */
data class BlePeripheral(
    val uuid: String,
    val name: String,
    val rssi: Int,
    val serviceUuids: List<String>,
)

/** One discovered GATT service and its characteristics, lowercase UUIDs (was Pigeon's `BleService`). */
data class BleService(
    val uuid: String,
    val characteristicUuids: List<String>,
)

/**
 * What `OmiBleManager` reports outside a GATT link (was Pigeon's `BleFlutterApi`). Called on the
 * main thread.
 */
interface BleEventListener {
    fun onPeripheralDiscovered(peripheral: BlePeripheral)

    /** `on`, `off`, `resetting`, `unknown` or `unsupported` (`OmiBleManager.getBluetoothState`). */
    fun onBluetoothStateChanged(state: String)

    fun onRssiUpdate(address: String, rssi: Int)

    /** A CCCD write stalled (`detail`) or recovered (`null`). */
    fun onCaptureHealth(address: String, detail: String?) {}
}
