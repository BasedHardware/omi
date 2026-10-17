package com.friend.ios.device

import android.Manifest
import android.annotation.SuppressLint
import android.app.Application
import android.bluetooth.BluetoothGatt
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.core.content.ContextCompat
import com.friend.ios.ble.BleDisconnectReason
import com.friend.ios.ble.BleEventListener
import com.friend.ios.ble.BlePeripheral
import com.friend.ios.ble.BleService
import com.friend.ios.ble.BondPolicy
import com.friend.ios.ble.OmiBleForegroundService
import com.friend.ios.ble.OmiBleManager
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.flow.receiveAsFlow
import java.util.UUID

/**
 * Port of `OmiDeviceManager.swift`: Bluetooth for the Omi wearable (scan, connect, battery, codec,
 * audio, button), speaking the Omi protocol directly on top of the Flutter app's `OmiBleManager`
 * GATT queue. Events arrive through [events]; reconnecting is the caller's decision (`DeviceStore`).
 *
 * Android's `connectGatt(autoConnect = true)` is CoreBluetooth's pending connect: it completes
 * whenever the Omi comes into range. A device just seen in a scan is connected directly (fast).
 * While an Omi is connected (or awaited after a drop) `OmiBleForegroundService` keeps the process.
 */
@SuppressLint("MissingPermission")
class OmiDeviceManager(context: Context) : DeviceDriving {
    enum class BluetoothState { Unknown, PoweredOff, Unauthorized, Unsupported, Ready }

    data class Discovery(val id: String, val name: String, val rssi: Int)

    sealed interface Event {
        data class Bluetooth(val state: BluetoothState) : Event
        data class Discovered(val discovery: Discovery) : Event
        data class Connecting(val id: String) : Event
        data class Connected(val id: String, val name: String) : Event
        data class Disconnected(val id: String, val error: String?) : Event
        data class Battery(val level: Int) : Event
        data class Codec(val codec: OmiGATT.Codec) : Event
        data class Info(val model: String?, val firmware: String?, val manufacturer: String?, val hardware: String? = null) : Event

        /** One codec frame with the 3-byte header removed. */
        class Audio(val frame: ByteArray) : Event
        class Button(val value: ByteArray) : Event

        /** What the firmware supports (features service); old firmware never sends it. */
        data class Features(val features: OmiGATT.Features) : Event
        data class Charging(val charging: Boolean) : Event
        data class LedBrightness(val level: Int) : Event
        data class MicGain(val level: Int) : Event
        data class SerialNumber(val serial: String) : Event

        /** Signal strength of the connected Omi in dBm (answers `readRSSI`). */
        data class Rssi(val rssi: Int) : Event
    }

    private val application = context.applicationContext as Application
    private val eventChannel = Channel<Event>(2048, BufferOverflow.DROP_OLDEST)
    override val events: Flow<Event> = eventChannel.receiveAsFlow()

    /** Offline storage, unbounded: a dropped data notification would corrupt the transfer. */
    private val storageChannel = Channel<OmiStorage.Event>(Channel.UNLIMITED)
    override val storageEvents: Flow<OmiStorage.Event> = storageChannel.receiveAsFlow()

    private val ble: OmiBleManager
    private val main = Handler(Looper.getMainLooper())
    /** The Omi being connected or connected (uppercase address). */
    private var address: String? = null
    private val discovered = mutableMapOf<String, BlePeripheral>()
    private var wantsScan = false
    private var wanted: String? = null
    private var bluetooth = BluetoothState.Unknown
    private val deviceInfo = mutableMapOf<UUID, String>()
    /** The device to connect bonds first (`BondPolicy`); kept for the service's background start. */
    private var requiresBond = false

    init {
        OmiBleManager.initialize(application)
        ble = OmiBleManager.instance
        ble.eventListener = object : BleEventListener {
            override fun onPeripheralDiscovered(peripheral: BlePeripheral) = discovered(peripheral)
            override fun onBluetoothStateChanged(state: String) = bluetoothChanged()
            override fun onRssiUpdate(address: String, rssi: Int) {
                if (address == this@OmiDeviceManager.address) send(Event.Rssi(rssi))
            }
        }
        ble.connectionListener = object : OmiBleManager.BleConnectionListener {
            override fun onGattConnected(address: String, gatt: BluetoothGatt) = connected(address, gatt)
            override fun onGattDisconnected(address: String, gattHash: Int, status: Int) = disconnected(address, status)
            override fun onGattServicesDiscovered(address: String, services: List<BleService>) = servicesDiscovered(address, services)
            override fun onMtuChanged(address: String, mtu: Int, status: Int) = Unit
        }
        ble.characteristicValueListener = object : OmiBleManager.CharacteristicValueListener {
            // Binder thread: audio goes straight to the channel; the rest is ordered there too.
            override fun onCharacteristicValue(address: String, serviceUuid: String, characteristicUuid: String, value: ByteArray) {
                if (address == this@OmiDeviceManager.address) valueUpdated(UUID.fromString(characteristicUuid), value)
            }
        }
        main.post { bluetoothChanged() }
    }

    override fun startScan() {
        wantsScan = true
        if (bluetooth != BluetoothState.Ready) return
        // Foreground scan without a service filter: Omi firmware variants differ in what they advertise.
        ble.startScan(timeout = 0, serviceUuids = emptyList())
    }

    override fun stopScan() {
        wantsScan = false
        ble.stopScan()
    }

    /**
     * Connects `id`, waiting as long as it takes for it to come into range. Ignored until
     * Bluetooth is ready (the caller connects again on `Bluetooth(Ready)`).
     */
    override fun connect(id: String) {
        if (bluetooth != BluetoothState.Ready) return
        val target = id.uppercase()
        wanted = null
        stopScan()
        address?.takeIf { it != target }?.let { previous ->
            ble.disconnectGatt(previous)
            ble.closeGatt(previous)
        }
        address = target
        if (ble.isPeripheralConnected(target)) {
            // Still linked (the process outlived the screen): only the services are missing.
            ble.connectedGatts[target]?.let { connected(target, it) }
            return
        }
        ble.connectedGatts[target]?.let { ble.closeGatt(target) }
        send(Event.Connecting(target))
        // Just seen nearby: a direct connect is fast. Otherwise wait for it in the background.
        val autoConnect = !discovered.containsKey(target)
        if (ble.connectGatt(target, autoConnect) == null) send(Event.Disconnected(target, "connectGatt failed"))
    }

    override fun disconnect() {
        wanted = null
        val current = address ?: return
        address = null
        ble.disconnectGatt(current)
        ble.closeGatt(current)
        // Closing skips the disconnect callback: report it like CoreBluetooth does.
        send(Event.Disconnected(current, null))
        OmiBleForegroundService.stopService(application)
    }

    override fun readBattery() = read(OmiGATT.batteryService, OmiGATT.batteryLevel)

    /** Asks for the connected Omi's signal strength; the answer arrives as `Rssi`. */
    override fun readRSSI() {
        address?.let { ble.sampleRssi(it) }
    }

    /** A storage command (`OmiStorage.Command.bytes`); replies arrive on [storageEvents]. */
    override fun writeStorage(command: ByteArray) = write(OmiGATT.storageService, OmiGATT.storageControl, command)

    override fun readStorageStatus() = read(OmiGATT.storageService, OmiGATT.storageStatus)

    /** Writes a setting or a haptic pulse (no-op when the firmware lacks the characteristic). */
    override fun write(control: OmiGATT.Control, payload: ByteArray) {
        val service = if (control == OmiGATT.Control.Haptic) OmiGATT.hapticService else OmiGATT.settingsService
        write(service, control.characteristic, payload)
    }

    /** Runtime permissions changed (granted from the device screen): Bluetooth may be usable now. */
    override fun permissionsChanged() = bluetoothChanged()

    // ── GATT ──

    private fun read(service: UUID, characteristic: UUID) {
        val current = address ?: return
        ble.readCharacteristic(current, service.toString(), characteristic.toString()) { result ->
            result.getOrNull()?.let { value -> main.post { if (current == address) valueUpdated(characteristic, value) } }
        }
    }

    private fun write(service: UUID, characteristic: UUID, payload: ByteArray) {
        val current = address ?: return
        ble.writeCharacteristic(current, service.toString(), characteristic.toString(), payload) { result ->
            result.exceptionOrNull()?.let { Log.w(TAG, "write $characteristic failed: ${it.message}") }
        }
    }

    private fun subscribe(service: UUID, characteristic: UUID, done: (Boolean) -> Unit = {}) {
        val current = address ?: return
        ble.subscribeCharacteristic(current, service.toString(), characteristic.toString()) { result ->
            main.post { done(result.isSuccess) }
        }
    }

    private fun discovered(peripheral: BlePeripheral) {
        val services = peripheral.serviceUuids.mapNotNull { runCatching { UUID.fromString(it) }.getOrNull() }
        val name = peripheral.name.ifEmpty { null }
        if (!OmiGATT.isOmi(name, services)) return
        discovered[peripheral.uuid] = peripheral
        send(Event.Discovered(Discovery(peripheral.uuid, name ?: "Omi", peripheral.rssi)))
        if (peripheral.uuid == wanted) connect(peripheral.uuid)
    }

    private fun connected(address: String, gatt: BluetoothGatt) {
        if (address != this.address) return
        // Read fresh on every connection: after a firmware update the revision differs.
        deviceInfo.clear()
        val name = runCatching { gatt.device.name }.getOrNull()?.takeIf { it.isNotEmpty() } ?: "Omi"
        send(Event.Connected(address, name))
        OmiBleForegroundService.startService(application, address, requiresBond = requiresBond, caller = "OmiDeviceManager.connected")
        // Services discovered before (a link that outlived the screen) are not reported again.
        if (ble.connectedGatts[address]?.services?.isNotEmpty() == true && !gatt.services.isNullOrEmpty()) {
            setUp(address, gatt.services.map { svc -> BleService(svc.uuid.toString(), svc.characteristics.map { it.uuid.toString() }) })
        }
    }

    override fun setRequiresBond(requiresBond: Boolean) {
        this.requiresBond = requiresBond
    }

    /**
     * A device that requires a bond (or started pairing itself) bonds first, as the Flutter
     * service did (`onGattServicesDiscovered` -> `requestBond`); the set-up follows either way.
     */
    private fun servicesDiscovered(address: String, services: List<BleService>) {
        if (address != this.address) return
        val gatt = ble.connectedGatts[address] ?: return
        val bondState = runCatching { gatt.device.bondState }.getOrDefault(android.bluetooth.BluetoothDevice.BOND_NONE)
        if (!BondPolicy.bondsBeforeSetUp(requiresBond, bondState)) return prepare(address, services)
        ble.requestBond(address) { result ->
            main.post {
                val bonded = result.getOrDefault(false)
                Log.i(TAG, "bond result for $address: $bonded")
                // Bonded once: the next connects need no pairing.
                if (bonded && requiresBond) {
                    requiresBond = false
                    OmiBleForegroundService.startService(application, address, requiresBond = false, caller = "OmiDeviceManager.bonded")
                }
                prepare(address, services)
            }
        }
    }

    /** Audio needs more than the default 23-byte MTU; the Flutter app asks for 512 first too. */
    private fun prepare(address: String, services: List<BleService>) {
        if (address != this.address) return
        val gatt = ble.connectedGatts[address] ?: return
        ble.enqueueCommand {
            val requested = runCatching { gatt.requestMtu(MTU_SIZE) }.getOrDefault(false)
            if (!requested) ble.completeCommand()
        }
        setUp(address, services)
    }

    /** `didDiscoverCharacteristicsFor`: what to read, what to subscribe, the time sync write. */
    private fun setUp(address: String, services: List<BleService>) {
        if (address != this.address) return
        for (service in services) {
            val serviceUUID = UUID.fromString(service.uuid)
            for (raw in service.characteristicUuids) {
                when (val uuid = UUID.fromString(raw)) {
                    OmiGATT.audioCodec, OmiGATT.modelNumber, OmiGATT.firmwareRevision, OmiGATT.manufacturerName,
                    OmiGATT.hardwareRevision,
                    -> read(serviceUUID, uuid)
                    OmiGATT.batteryLevel, OmiGATT.chargingStatus -> {
                        read(serviceUUID, uuid)
                        subscribe(serviceUUID, uuid)
                    }
                    OmiGATT.audioData, OmiGATT.buttonData -> subscribe(serviceUUID, uuid)
                    OmiGATT.storageControl -> subscribe(serviceUUID, uuid) { ok -> if (ok) storageChannel.trySend(OmiStorage.Event.Ready) }
                    OmiGATT.storageStatus, OmiGATT.features, OmiGATT.ledDimRatio, OmiGATT.micGain, OmiGATT.serialNumber ->
                        read(serviceUUID, uuid)
                    // Every connect, like the Flutter app: offline recordings carry this clock.
                    OmiGATT.timeSyncWrite -> write(serviceUUID, uuid, OmiStorage.timeSyncPayload(System.currentTimeMillis()))
                    else -> Unit
                }
            }
        }
    }

    private fun disconnected(address: String, status: Int) {
        ble.closeGatt(address)
        if (address != this.address) return
        send(Event.Disconnected(address, BleDisconnectReason.connectionErrorFromStatus(status)))
    }

    private fun valueUpdated(characteristic: UUID, value: ByteArray) {
        when (characteristic) {
            OmiGATT.storageControl -> OmiStorage.Notification.from(value)?.let { storageChannel.trySend(OmiStorage.Event.NotificationReceived(it)) }
            OmiGATT.storageStatus -> OmiStorage.Status.from(value)?.let { storageChannel.trySend(OmiStorage.Event.StatusRead(it)) }
            OmiGATT.audioData -> OmiGATT.audioPayload(value)?.let { send(Event.Audio(it.payload)) }
            // An empty read means the oldest firmware: pcm8.
            OmiGATT.audioCodec -> send(Event.Codec(value.firstOrNull()?.let { OmiGATT.Codec.fromRaw(it.toInt() and 0xFF) } ?: OmiGATT.Codec.Pcm8))
            OmiGATT.batteryLevel -> value.firstOrNull()?.let { send(Event.Battery(it.toInt() and 0xFF)) }
            OmiGATT.buttonData -> send(Event.Button(value))
            OmiGATT.features -> send(Event.Features(OmiGATT.Features.from(value)))
            OmiGATT.chargingStatus -> OmiGATT.isCharging(value)?.let { send(Event.Charging(it)) }
            OmiGATT.ledDimRatio -> OmiGATT.settingValue(value)?.let { send(Event.LedBrightness(it)) }
            OmiGATT.micGain -> OmiGATT.settingValue(value)?.let { send(Event.MicGain(it)) }
            OmiGATT.serialNumber -> OmiGATT.serialNumber(value)?.let { send(Event.SerialNumber(it)) }
            OmiGATT.modelNumber, OmiGATT.firmwareRevision, OmiGATT.manufacturerName, OmiGATT.hardwareRevision -> {
                deviceInfo[characteristic] = value.toString(Charsets.UTF_8).trim { it.isISOControl() }
                send(
                    Event.Info(
                        model = deviceInfo[OmiGATT.modelNumber],
                        firmware = deviceInfo[OmiGATT.firmwareRevision],
                        manufacturer = deviceInfo[OmiGATT.manufacturerName],
                        hardware = deviceInfo[OmiGATT.hardwareRevision],
                    ),
                )
            }
            else -> Unit
        }
    }

    private fun bluetoothChanged() {
        val state = state()
        bluetooth = state
        if (state == BluetoothState.Ready && wantsScan) startScan()
        send(Event.Bluetooth(state))
    }

    private fun state(): BluetoothState {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val granted = listOf(Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_SCAN).all {
                ContextCompat.checkSelfPermission(application, it) == PackageManager.PERMISSION_GRANTED
            }
            if (!granted) return BluetoothState.Unauthorized
        }
        return when (ble.getBluetoothState()) {
            "on" -> BluetoothState.Ready
            "off" -> BluetoothState.PoweredOff
            "unsupported" -> BluetoothState.Unsupported
            else -> BluetoothState.Unknown
        }
    }

    private fun send(event: Event) {
        eventChannel.trySend(event)
    }

    companion object {
        private const val TAG = "OmiDevice"
        private const val MTU_SIZE = 512

        /** The runtime permissions Bluetooth needs on this Android version (asked on My Omi). */
        val requiredPermissions: List<String>
            get() = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
            } else {
                listOf(Manifest.permission.ACCESS_FINE_LOCATION)
            }
    }
}

/** What the app needs from the wearable driver (real: [OmiDeviceManager]; tests: a fake). */
interface DeviceDriving {
    val events: Flow<OmiDeviceManager.Event>
    fun startScan()
    fun stopScan()

    /**
     * A pending connect: completes whenever the device comes into range. Does nothing while
     * Bluetooth is not ready and never retries after a disconnect on its own.
     */
    fun connect(id: String)
    fun disconnect()
    fun readBattery()

    /** Offline storage (`OmiStorage`). Drivers without it (test fakes) get none. */
    val storageEvents: Flow<OmiStorage.Event> get() = emptyFlow()
    fun writeStorage(command: ByteArray) {}
    fun readStorageStatus() {}

    /** Settings and haptics (`OmiGATT.Control`). */
    fun write(control: OmiGATT.Control, payload: ByteArray) {}

    /** Signal strength of the connected device (diagnostics); answered with `Rssi`. */
    fun readRSSI() {}

    /** Android only: Bluetooth permissions were just granted or denied. */
    fun permissionsChanged() {}

    /** Android only: the device to connect next bonds first (`BondPolicy.requiresBond`). */
    fun setRequiresBond(requiresBond: Boolean) {}
}
