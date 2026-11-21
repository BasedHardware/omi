package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.device.DeviceDriving
import com.friend.ios.device.OmiDeviceManager
import com.friend.ios.device.OmiGATT
import com.friend.ios.device.OmiStorage
import com.friend.ios.device.PairedDevice
import com.friend.ios.device.findPattern
import com.friend.ios.device.findPulseGapMillis
import com.friend.ios.device.ledBrightnessPayload
import com.friend.ios.device.micGainPayload
import com.friend.ios.persistence.Preferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Port of `DeviceStore.swift`: the Omi wearable (pairing, connection, battery, codec). Mirrors
 * `device_provider.dart`. The paired device lives in the Flutter app's `btDevice` preference, so a
 * device paired in the Flutter build reconnects after the update.
 *
 * Reconnecting lives here, not in the driver: the paired Omi is connected once Bluetooth is
 * ready and again after every disconnect. A connect waits until the device is in range, so the
 * attempt shows as `Connecting` for `connectTimeout` and then quietly keeps waiting as
 * `Disconnected`. Attempts that fail outright are retried a few times, spaced out.
 */
class DeviceStore(
    private val makeDriver: () -> DeviceDriving,
    private val preferences: Preferences,
    private val scope: CoroutineScope,
    private val connectTimeoutMillis: Long = 15_000,
    private val retryDelayMillis: Long = 5_000,
    private val findPulseGapMillis: Long = OmiGATT.findPulseGapMillis,
) : StorageLink, FirmwareDeviceHost {
    enum class Connection { Disconnected, Connecting, Connected }

    var bluetooth: OmiDeviceManager.BluetoothState by mutableStateOf(OmiDeviceManager.BluetoothState.Unknown)
        private set
    override var paired: PairedDevice? by mutableStateOf(PairedDevice.decode(preferences.string(Preferences.Key.BtDevice)))
        private set
    override var connection: Connection by mutableStateOf(Connection.Disconnected)
        private set
    override var battery: Int? by mutableStateOf(null)
        private set
    override var codec: OmiGATT.Codec? by mutableStateOf(null)
        private set
    var discovered: List<OmiDeviceManager.Discovery> by mutableStateOf(emptyList())
        private set
    var isScanning: Boolean by mutableStateOf(false)
        private set

    /** The firmware revision read on this connection (`null` until read, and while disconnected). */
    override var liveFirmware: String? by mutableStateOf(null)
        private set

    /** A firmware update owns the Omi: no connects until it hands the device back. */
    var isUpdatingFirmware: Boolean by mutableStateOf(false)
        private set

    /** On the charger (settings service; `null` until read, and on firmware without it). */
    var isCharging: Boolean? by mutableStateOf(null)
        private set

    /** What the connected firmware supports; `null` until read (old firmware never reports it). */
    var features: OmiGATT.Features? by mutableStateOf(null)
        private set

    /** LED brightness 0...100 and mic gain level 0...8, as read from (or last written to) the Omi. */
    var ledBrightness: Int? by mutableStateOf(null)
        private set
    var micGain: Int? by mutableStateOf(null)
        private set

    /** Find my Omi is buzzing. */
    var isFinding: Boolean by mutableStateOf(false)
        private set

    /** Drops, failed connects, battery and signal for My Devices › Diagnostics. */
    val diagnostics = DeviceDiagnosticsLog(preferences)

    private var doubleTap by mutableStateOf(
        DoubleTapAction.fromRaw(preferences.integer(Preferences.Key.DoubleTapAction, 0)) ?: DoubleTapAction.EndConversation,
    )
    var doubleTapAction: DoubleTapAction
        get() = doubleTap
        set(value) {
            doubleTap = value
            preferences.set(Preferences.Key.DoubleTapAction, value.rawValue)
        }

    private var actionsEnabled by mutableStateOf(preferences.bool(Preferences.Key.OmiButtonActionsEnabled, true))

    /** Single press asks Omi and double tap runs `doubleTapAction` (Flutter "Omi Button Actions"). */
    var buttonActionsEnabled: Boolean
        get() = actionsEnabled
        set(value) {
            actionsEnabled = value
            preferences.set(Preferences.Key.OmiButtonActionsEnabled, value)
        }

    /** Audio frames while connected (wired to the capture store by the app shell). */
    var onAudio: ((ByteArray) -> Unit)? = null

    /** Called once the codec is known after a connect: capture can start. */
    var onReady: ((OmiGATT.Codec) -> Unit)? = null
    var onDisconnect: (() -> Unit)? = null

    /** A second listener for the Omi's audio (onboarding's voice sample), next to capture. */
    var audioTap: ((ByteArray) -> Unit)? = null

    /** A double tap on the Omi's button while it is set to end the conversation. */
    var onDoubleTap: (() -> Unit)? = null

    /** Every routed button action (`ButtonAction.route`), the end-conversation tap included. */
    var onButtonAction: ((ButtonAction) -> Unit)? = null

    /**
     * Sees every raw button event first (the button lessons in onboarding); true keeps it from
     * `ButtonAction.route`, so a practice press does not end or star anything.
     */
    var buttonInterceptor: ((OmiGATT.ButtonEvent) -> Boolean)? = null

    /** Model or firmware read from the connected Omi (the firmware check runs from here). */
    var onDeviceInfo: (() -> Unit)? = null

    /**
     * Android only (and-askomi): the system's companion association, asked when pairing and
     * before the connect (the device still advertises), so the link can start in the background.
     * Null (tests, the fake device) connects straight away.
     */
    var associate: (suspend (address: String) -> Unit)? = null

    /** The Omi's battery dropped below `LowBatteryAlert.low`; once per discharge. */
    var onLowBattery: ((Int) -> Unit)? = null

    /** Offline storage replies (wired to the sync store by the app shell). */
    var onStorage: ((OmiStorage.Event) -> Unit)? = null

    /** Created on first use ([driver]); null until then. Internal for the controls extension. */
    internal var driverInstance: DeviceDriving? = null
    private var timeoutJob: Job? = null
    private var retryJob: Job? = null

    /** Whether the link was up before the last disconnect (otherwise the attempt failed). */
    private var wasConnected = false
    private var failedAttempts = 0
    private val lowBattery = LowBatteryAlert(preferences.bool(Preferences.NativeKey.LowBatteryAlerted, false))

    /**
     * The driver is created lazily: it registers Bluetooth receivers and on iOS shows the Bluetooth
     * prompt, which only users with (or looking for) a wearable should see.
     */
    private val driver: DeviceDriving
        get() {
            driverInstance?.let { return it }
            val driver = makeDriver()
            driverInstance = driver
            scope.launch { driver.events.collect { handle(it) } }
            scope.launch { driver.storageEvents.collect { onStorage?.invoke(it) } }
            return driver
        }

    /**
     * Connects the paired device (no-op, and no Bluetooth set-up, without one). Also "Try again":
     * starts over after failed attempts.
     */
    fun start() {
        failedAttempts = 0
        connectPaired()
    }

    fun scan() {
        discovered = emptyList()
        isScanning = true
        driver.startScan()
    }

    fun stopScan() {
        isScanning = false
        driverInstance?.stopScan()
    }

    fun pair(discovery: OmiDeviceManager.Discovery) {
        stopScan()
        val device = PairedDevice(id = discovery.id, name = discovery.name, rssi = discovery.rssi)
        persist(device)
        driver.setRequiresBond(com.friend.ios.ble.BondPolicy.requiresBond(device.type))
        val associate = associate ?: return driver.connect(discovery.id)
        scope.launch {
            // Non-fatal, as in Flutter: without an association the link still works while the app is open.
            runCatching { associate(discovery.id) }
            if (paired?.id == discovery.id) driver.connect(discovery.id)
        }
    }

    fun forget() {
        diagnostics.reset()
        driverInstance?.disconnect()
        paired = null
        preferences.set(Preferences.Key.BtDevice, null)
        connection = Connection.Disconnected
        battery = null
        codec = null
        liveFirmware = null
        clearControls()
        timeoutJob?.cancel()
        retryJob?.cancel()
        wasConnected = false
        failedAttempts = 0
    }

    /** Bluetooth permissions were answered (My Omi asks for them on Android). */
    fun permissionsChanged() {
        driver.permissionsChanged()
    }

    // MARK: Controls

    fun setLEDBrightness(percent: Int) {
        if (!canDimLED) return
        val value = percent.coerceIn(0, 100)
        ledBrightness = value
        driverInstance?.write(OmiGATT.Control.LedBrightness, OmiGATT.ledBrightnessPayload(value))
    }

    fun setMicGain(level: Int) {
        if (!canSetMicGain) return
        val value = level.coerceIn(0, 8)
        micGain = value
        driverInstance?.write(OmiGATT.Control.MicGain, OmiGATT.micGainPayload(value))
    }

    /** Find my Omi: three long buzzes. Calls while it buzzes are ignored. */
    suspend fun findDevice() {
        if (!canFind || isFinding) return
        isFinding = true
        try {
            val pattern = OmiGATT.findPattern
            for ((index, pulse) in pattern.withIndex()) {
                if (connection != Connection.Connected) return
                driverInstance?.write(OmiGATT.Control.Haptic, pulse.payload)
                if (index < pattern.size - 1) delay(findPulseGapMillis)
            }
        } finally {
            isFinding = false
        }
    }

    private fun clearControls() {
        isCharging = null
        features = null
        ledBrightness = null
        micGain = null
    }

    /** Writes a command to the Omi's storage (no-op while not connected). */
    override fun sendStorage(command: OmiStorage.Command) {
        if (connection != Connection.Connected) return
        driverInstance?.writeStorage(command.bytes)
    }

    override val storageDeviceID: String? get() = if (connection == Connection.Connected) paired?.id else null

    private val pairedID: String? get() = paired?.id

    private fun connectPaired() {
        val id = pairedID ?: return
        if (connection == Connection.Connected || isUpdatingFirmware) return
        retryJob?.cancel()
        driver.setRequiresBond(com.friend.ios.ble.BondPolicy.requiresBond(paired?.type ?: "omi"))
        driver.connect(id)
    }

    private fun bluetoothChanged(state: OmiDeviceManager.BluetoothState) {
        bluetooth = state
        // Connects made before Bluetooth reported ready (every cold start) went nowhere.
        if (state == OmiDeviceManager.BluetoothState.Ready) {
            failedAttempts = 0
            connectPaired()
        } else if (connection != Connection.Disconnected) {
            // Bluetooth off drops the link without a disconnect callback.
            if (connection == Connection.Connected) diagnostics.disconnected(reason = null, wasConnected = true, manual = true)
            connection = Connection.Disconnected
            wasConnected = false
            timeoutJob?.cancel()
            onDisconnect?.invoke()
        }
    }

    /** "Connecting..." for `connectTimeout`; after that the attempt keeps waiting as "Not connected". */
    private fun connecting() {
        connection = Connection.Connecting
        timeoutJob?.cancel()
        timeoutJob = scope.launch {
            delay(connectTimeoutMillis)
            if (connection == Connection.Connecting) connection = Connection.Disconnected
        }
    }

    /**
     * Reconnects right away when the link dropped (the connect waits for the device); spaced out
     * and capped when the attempt itself failed, so a broken bond does not spin.
     */
    private fun disconnected(id: String, error: String?) {
        onDisconnect?.invoke()
        // A previous device let go while switching: not ours to reconnect.
        if (!id.equals(pairedID, ignoreCase = true)) return
        // A firmware update let go on purpose (recorded when it did).
        if (!isUpdatingFirmware) diagnostics.disconnected(reason = error, wasConnected = wasConnected)
        connection = Connection.Disconnected
        liveFirmware = null
        timeoutJob?.cancel()
        if (wasConnected) {
            wasConnected = false
            failedAttempts = 0
            connectPaired()
            return
        }
        failedAttempts += 1
        if (failedAttempts > MAX_FAILED_ATTEMPTS) return
        retryJob?.cancel()
        retryJob = scope.launch {
            delay(retryDelayMillis)
            connectPaired()
        }
    }

    /**
     * Lets go of the Omi for a firmware update, which connects on its own: live audio stops and
     * nothing reconnects until `resumeAfterFirmwareUpdate()`.
     */
    override fun suspendForFirmwareUpdate() {
        isUpdatingFirmware = true
        if (connection == Connection.Connected) diagnostics.disconnected(reason = null, wasConnected = true, manual = true)
        timeoutJob?.cancel()
        retryJob?.cancel()
        driverInstance?.disconnect()
        if (connection != Connection.Disconnected) onDisconnect?.invoke()
        connection = Connection.Disconnected
        wasConnected = false
        liveFirmware = null
    }

    /** The update is over (either way): reconnect, waiting for the Omi to finish restarting. */
    override fun resumeAfterFirmwareUpdate() {
        if (!isUpdatingFirmware) return
        isUpdatingFirmware = false
        failedAttempts = 0
        connectPaired()
    }

    private fun batteryChanged(level: Int) {
        battery = level
        diagnostics.batteryRead(level, charging = isCharging)
        val wasAlerted = lowBattery.alerted
        if (lowBattery.update(level)) onLowBattery?.invoke(level)
        if (lowBattery.alerted != wasAlerted) preferences.set(Preferences.NativeKey.LowBatteryAlerted, lowBattery.alerted)
    }

    private fun persist(device: PairedDevice) {
        paired = device
        preferences.set(Preferences.Key.BtDevice, device.encoded)
    }

    internal fun handle(event: OmiDeviceManager.Event) {
        when (event) {
            is OmiDeviceManager.Event.Bluetooth -> bluetoothChanged(event.state)
            is OmiDeviceManager.Event.Discovered -> {
                val index = discovered.indexOfFirst { it.id == event.discovery.id }
                discovered = if (index >= 0) discovered.toMutableList().also { it[index] = event.discovery } else discovered + event.discovery
            }
            is OmiDeviceManager.Event.Connecting -> connecting()
            is OmiDeviceManager.Event.Connected -> {
                connection = Connection.Connected
                liveFirmware = null
                clearControls()
                wasConnected = true
                diagnostics.connected()
                failedAttempts = 0
                timeoutJob?.cancel()
                if (!paired?.id.equals(event.id, ignoreCase = true)) persist(PairedDevice(id = event.id, name = event.name))
            }
            is OmiDeviceManager.Event.Disconnected -> disconnected(event.id, event.error)
            is OmiDeviceManager.Event.Battery -> batteryChanged(event.level)
            is OmiDeviceManager.Event.Codec -> {
                codec = event.codec
                onReady?.invoke(event.codec)
            }
            is OmiDeviceManager.Event.Info -> {
                val device = paired ?: return
                persist(
                    device.copy(
                        modelNumber = event.model ?: device.modelNumber,
                        firmwareRevision = event.firmware ?: device.firmwareRevision,
                        manufacturerName = event.manufacturer ?: device.manufacturerName,
                        hardwareRevision = event.hardware ?: device.hardwareRevision,
                    ),
                )
                event.firmware?.let { liveFirmware = it }
                onDeviceInfo?.invoke()
            }
            is OmiDeviceManager.Event.Audio -> {
                onAudio?.invoke(event.frame)
                audioTap?.invoke(event.frame)
            }
            is OmiDeviceManager.Event.Button -> {
                val button = OmiGATT.ButtonEvent.from(event.value) ?: return
                if (buttonInterceptor?.invoke(button) == true) return
                val action = ButtonAction.route(button, doubleTapAction, buttonActionsEnabled) ?: return
                if (action == ButtonAction.EndConversation) onDoubleTap?.invoke()
                onButtonAction?.invoke(action)
            }
            is OmiDeviceManager.Event.Rssi -> diagnostics.signalRead(event.rssi)
            is OmiDeviceManager.Event.Features -> features = event.features
            is OmiDeviceManager.Event.Charging -> isCharging = event.charging
            is OmiDeviceManager.Event.LedBrightness -> ledBrightness = event.level
            is OmiDeviceManager.Event.MicGain -> micGain = event.level
            is OmiDeviceManager.Event.SerialNumber -> {
                val device = paired ?: return
                if (device.serialNumber != event.serial) persist(device.copy(serialNumber = event.serial))
            }
        }
    }

    companion object {
        private const val MAX_FAILED_ATTEMPTS = 3
    }
}
