package com.friend.ios.service.stores

import com.friend.ios.core.models.FirmwareRelease
import com.friend.ios.device.DeviceDriving
import com.friend.ios.device.FirmwareUpdating
import com.friend.ios.device.OmiDeviceManager
import com.friend.ios.device.OmiDeviceManager.Event
import com.friend.ios.device.OmiGATT
import com.friend.ios.device.PairedDevice
import com.friend.ios.network.APIError
import com.friend.ios.persistence.Preferences
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** A driver the tests feed by hand; records what the store asked of it. */
class FakeDriver : DeviceDriving {
    private val channel = Channel<Event>(Channel.UNLIMITED)
    override val events: Flow<Event> = channel.receiveAsFlow()
    val log = mutableListOf<String>()
    val writes = mutableListOf<Pair<OmiGATT.Control, ByteArray>>()
    val bonds = mutableListOf<Boolean>()

    fun emit(event: Event) {
        channel.trySend(event)
    }

    override fun startScan() {
        log += "scan"
    }

    override fun stopScan() {
        log += "stopScan"
    }

    override fun connect(id: String) {
        log += "connect $id"
    }

    override fun disconnect() {
        log += "disconnect"
    }

    override fun readBattery() {}

    override fun write(control: OmiGATT.Control, payload: ByteArray) {
        writes += control to payload
    }

    override fun writeStorage(command: ByteArray) {
        log += "storage ${command.first()}"
    }

    override fun setRequiresBond(requiresBond: Boolean) {
        bonds += requiresBond
    }
}

/** Port of `DeviceGapsTests` / `DeviceControlsTests` / `LowBatteryTests` for `DeviceStore`. */
@OptIn(ExperimentalCoroutinesApi::class)
class DeviceStoreTest {
    private val id = "AA:BB:CC:DD:EE:FF"

    private fun TestScope.store(prefs: Preferences = freshPreferences(), paired: Boolean = true): Pair<DeviceStore, FakeDriver> {
        if (paired) prefs.set(Preferences.Key.BtDevice, PairedDevice(id = id, name = "Omi").encoded)
        val driver = FakeDriver()
        val store = DeviceStore({ driver }, prefs, backgroundScope, connectTimeoutMillis = 1_000, retryDelayMillis = 500, findPulseGapMillis = 10)
        return store to driver
    }

    @Test fun connectsThePairedOmiOnceBluetoothIsReady() = runTest {
        val (store, driver) = store()
        store.start()
        runCurrent()
        driver.emit(Event.Bluetooth(OmiDeviceManager.BluetoothState.Ready))
        runCurrent()
        assertEquals(listOf("connect $id", "connect $id"), driver.log)
        driver.emit(Event.Connecting(id))
        runCurrent()
        assertEquals(DeviceStore.Connection.Connecting, store.connection)
        // Out of range: after the timeout it waits quietly as "Not connected".
        advanceTimeBy(1_100)
        assertEquals(DeviceStore.Connection.Disconnected, store.connection)
        driver.emit(Event.Connected(id, "Omi"))
        driver.emit(Event.Codec(OmiGATT.Codec.OpusFS320))
        runCurrent()
        assertEquals(DeviceStore.Connection.Connected, store.connection)
        assertEquals(OmiGATT.Codec.OpusFS320, store.codec)
        assertEquals(id, store.storageDeviceID)
    }

    @Test fun reconnectsAfterADropButCapsFailedAttempts() = runTest {
        val (store, driver) = store()
        store.start()
        runCurrent()
        driver.emit(Event.Connected(id, "Omi"))
        driver.emit(Event.Disconnected(id, "gatt_status_8"))
        runCurrent()
        // A drop reconnects right away.
        assertEquals(2, driver.log.count { it.startsWith("connect") })
        assertEquals(1, store.diagnostics.events.size)
        // Failed attempts are retried three times, spaced out, then left alone.
        repeat(5) {
            driver.emit(Event.Disconnected(id, "gatt_status_133"))
            runCurrent()
            advanceTimeBy(600)
        }
        assertEquals(5, driver.log.count { it.startsWith("connect") })
        store.start()
        assertEquals(6, driver.log.count { it.startsWith("connect") })
    }

    @Test fun pairingPersistsLikeFlutterAndForgetClearsIt() = runTest {
        val prefs = freshPreferences()
        val (store, driver) = store(prefs, paired = false)
        store.scan()
        driver.emit(Event.Discovered(OmiDeviceManager.Discovery(id, "Omi", -50)))
        driver.emit(Event.Discovered(OmiDeviceManager.Discovery(id, "Omi", -40)))
        runCurrent()
        assertEquals(1, store.discovered.size)
        store.pair(store.discovered[0])
        assertEquals(id, PairedDevice.decode(prefs.string(Preferences.Key.BtDevice))?.id)
        driver.emit(Event.Connected(id, "Omi"))
        driver.emit(Event.Info("Omi CV 1", "2.0.10", "Based Hardware", "CV1"))
        driver.emit(Event.SerialNumber("0A1B2C3D4E5F6789"))
        runCurrent()
        val saved = PairedDevice.decode(prefs.string(Preferences.Key.BtDevice))
        assertEquals("2.0.10", saved?.firmwareRevision)
        assertEquals("0A1B2C3D4E5F6789", saved?.serialNumber)
        assertEquals("2.0.10", store.liveFirmware)
        store.forget()
        assertNull(store.paired)
        assertNull(prefs.string(Preferences.Key.BtDevice))
        assertTrue("disconnect" in driver.log)
    }

    @Test fun lowBatteryNotifiesOncePerDischarge() = runTest {
        val prefs = freshPreferences()
        val (store, driver) = store(prefs)
        val alerts = mutableListOf<Int>()
        store.onLowBattery = { alerts += it }
        store.start()
        runCurrent()
        driver.emit(Event.Connected(id, "Omi"))
        listOf(40, 14, 13, 16, 12, 35, 10).forEach { driver.emit(Event.Battery(it)) }
        runCurrent()
        assertEquals(listOf(14, 10), alerts)
        assertEquals(10, store.battery)
        assertTrue(prefs.bool(Preferences.NativeKey.LowBatteryAlerted, false))
        val alert = LowBatteryAlert()
        assertTrue(alert.update(14))
        assertFalse(alert.update(12))
        assertFalse(alert.update(31))
        assertTrue(alert.update(5))
        assertTrue(LowBatteryAlert.isLow(14))
        assertFalse(LowBatteryAlert.isLow(15))
    }

    @Test fun buttonEventsRouteByTheChosenDoubleTap() = runTest {
        val prefs = freshPreferences()
        val (store, driver) = store(prefs)
        val actions = mutableListOf<ButtonAction>()
        var ended = 0
        store.onButtonAction = { actions += it }
        store.onDoubleTap = { ended += 1 }
        store.start()
        runCurrent()
        fun press(value: Int) = driver.emit(Event.Button(byteArrayOf(value.toByte(), 0, 0, 0)))
        press(2)
        runCurrent()
        store.doubleTapAction = DoubleTapAction.Star
        press(2)
        press(1)
        press(4)
        runCurrent()
        assertEquals(listOf(ButtonAction.EndConversation, ButtonAction.ToggleStar, ButtonAction.AskToggle), actions)
        assertEquals(1, ended)
        assertEquals(2L, prefs.integer(Preferences.Key.DoubleTapAction, 0).toLong())
        store.buttonActionsEnabled = false
        press(1)
        runCurrent()
        assertEquals(3, actions.size)
        // A lesson sees presses first and keeps them from the real actions.
        store.buttonActionsEnabled = true
        val tutorial = ButtonTutorialStore(store, null)
        tutorial.begin(ButtonTutorialStore.Lesson.DoublePress)
        press(1)
        press(2)
        runCurrent()
        assertEquals(1, tutorial.doublePresses)
        assertEquals(3, actions.size)
        tutorial.end()
        assertNull(store.buttonInterceptor)
    }

    @Test fun controlsFollowWhatTheFirmwareSupports() = runTest {
        val (store, driver) = store()
        store.start()
        runCurrent()
        driver.emit(Event.Connected(id, "Omi"))
        runCurrent()
        // No features read yet: find is assumed, dimming and gain are not.
        assertTrue(store.canFind)
        assertFalse(store.canDimLED)
        store.setLEDBrightness(50)
        assertTrue(driver.writes.isEmpty())
        driver.emit(Event.Features(OmiGATT.Features.of(OmiGATT.Features.ledDimming, OmiGATT.Features.micGain, OmiGATT.Features.haptic)))
        driver.emit(Event.LedBrightness(60))
        driver.emit(Event.MicGain(5))
        runCurrent()
        assertTrue(store.canDimLED)
        assertTrue(store.canSetMicGain)
        store.setLEDBrightness(150)
        store.setMicGain(12)
        assertEquals(100, store.ledBrightness)
        assertEquals(8, store.micGain)
        assertEquals(listOf(OmiGATT.Control.LedBrightness, OmiGATT.Control.MicGain), driver.writes.map { it.first })
        store.findDevice()
        assertEquals(3, driver.writes.count { it.first == OmiGATT.Control.Haptic })
        assertFalse(store.isFinding)
        // A new connection reads the controls fresh.
        driver.emit(Event.Disconnected(id, null))
        driver.emit(Event.Connected(id, "Omi"))
        runCurrent()
        assertNull(store.features)
        assertNull(store.ledBrightness)
    }

    @Test fun firmwareUpdateHoldsReconnectsUntilHandedBack() = runTest {
        val (store, driver) = store()
        store.start()
        runCurrent()
        driver.emit(Event.Connected(id, "Omi"))
        runCurrent()
        store.suspendForFirmwareUpdate()
        assertEquals(DeviceStore.Connection.Disconnected, store.connection)
        val connects = driver.log.count { it.startsWith("connect") }
        driver.emit(Event.Disconnected(id, null))
        runCurrent()
        store.start()
        assertEquals(connects, driver.log.count { it.startsWith("connect") })
        store.resumeAfterFirmwareUpdate()
        assertEquals(connects + 1, driver.log.count { it.startsWith("connect") })
    }
}

/** Port of `DeviceDiagnosticsTests`. */
class DeviceDiagnosticsTest {
    private var clock = 1_790_000_000_000L
    private val prefs = freshPreferences()

    private fun log() = DeviceDiagnosticsLog(prefs) { clock }

    @Test fun dropsAreTimedUntilTheOmiIsBack() {
        val diagnostics = log()
        diagnostics.connected()
        clock += 600_000
        diagnostics.signalRead(-70)
        diagnostics.disconnected("timed out", wasConnected = true)
        assertEquals(0, diagnostics.summary.drops)
        clock += 8_000
        diagnostics.connected()
        val drop = diagnostics.events[0]
        assertEquals(DiagnosticsEvent.Kind.Disconnect, drop.kind)
        assertEquals(600.0, drop.connectedFor)
        assertEquals(8.0, drop.reconnectedAfter)
        assertEquals(-70, drop.lastRSSI)
        assertEquals(1, diagnostics.summary.drops)
        assertEquals(8.0, diagnostics.summary.medianReconnect)
        assertFalse(diagnostics.summary.hasTrouble)
    }

    @Test fun failedConnectsDecideTheVerdict() {
        val diagnostics = log()
        diagnostics.connected()
        diagnostics.disconnected(null, wasConnected = true, manual = true)
        clock += 30_000
        diagnostics.connected()
        assertEquals(0, diagnostics.summary.drops)
        assertNull(diagnostics.events[0].reconnectedAfter)
        diagnostics.disconnected(null, wasConnected = false)
        assertEquals(1, diagnostics.summary.failed)
        assertTrue(diagnostics.summary.hasTrouble)
        clock += 25 * 3_600_000L
        assertFalse(diagnostics.summary.hasTrouble)
    }

    @Test fun summaryUsesTheMedianAndLongestGap() {
        val events = listOf(3.0, 10.0, 40.0).mapIndexed { index, gap ->
            DiagnosticsEvent(DiagnosticsEvent.Kind.Disconnect, at = clock + index * 60_000L, reconnectedAfter = gap)
        }
        val summary = DiagnosticsSummary.make(events, now = clock + 7_200_000, since = clock)
        assertEquals(3, summary.drops)
        assertEquals(10.0, summary.medianReconnect)
        assertEquals(40.0, summary.longestGap)
        assertEquals(2, summary.dropsPerHour)
    }

    @Test fun historyIsKeptForAWeekAndClearedOnForget() {
        val first = log()
        first.connected()
        first.disconnected("gone", wasConnected = true)
        first.batteryRead(80, false)
        first.batteryRead(80, false)
        clock += 16 * 60_000
        first.batteryRead(80, false)
        assertEquals(2, first.battery.size)
        val relaunched = log()
        assertEquals(listOf("gone"), relaunched.events.map { it.reason })
        assertEquals(2, relaunched.battery.size)
        clock += 8 * 24 * 3_600_000L
        assertTrue(log().events.isEmpty())
        relaunched.reset()
        assertNull(prefs.string(Preferences.NativeKey.DeviceDiagnostics))
    }

    @Test fun signalBands() {
        assertEquals(SignalQuality.Excellent, SignalQuality.of(-55))
        assertEquals(SignalQuality.Good, SignalQuality.of(-70))
        assertEquals(SignalQuality.Fair, SignalQuality.of(-80))
        assertEquals(SignalQuality.Weak, SignalQuality.of(-95))
    }

    /** Flutter's schema 2: the backend refuses anything else. */
    @Test fun bundleIsSchemaTwo() {
        val diagnostics = log()
        diagnostics.connected()
        diagnostics.disconnected("x", wasConnected = true)
        clock += 5_000
        diagnostics.connected()
        val device = PairedDevice(id = "dev-1", name = "Omi", firmwareRevision = "3.0.1")
        val text = String(diagnostics.bundle(device, 64, false, DeviceDiagnosticsLog.Environment("1.0", "7", "16", "Pixel 9")))
        val obj = kotlinx.serialization.json.Json.parseToJsonElement(text) as kotlinx.serialization.json.JsonObject
        assertEquals("2", obj["schema_version"].toString())
        assertEquals("\"dev-1\"", obj["device_id"].toString())
        assertEquals("\"3.0.1\"", obj["firmware"].toString())
        assertEquals("64", obj["battery"].toString())
        assertEquals("1", obj["reconnection_count"].toString())
        assertEquals("\"android\"", obj["platform"].toString())
    }
}

/** Plays a scripted upload: progress values, then success or a failure. */
class FakeUpdater : FirmwareUpdating {
    var progress = listOf(0.25, 0.5, 1.0)
    var failure: Throwable? = null
    val flashed = mutableListOf<File>()

    override fun update(deviceID: String, firmware: File): Flow<Double> = flow {
        flashed += firmware
        progress.forEach { emit(it) }
        failure?.let { throw it }
    }
}

class FakeFirmwareHost(firmware: String = "3.0.21") : FirmwareDeviceHost {
    override var paired: PairedDevice? = PairedDevice(id = "AA:BB", name = "Omi", modelNumber = "Omi CV 1", firmwareRevision = firmware)
    override var connection = DeviceStore.Connection.Connected
    override var battery: Int? = 80
    override var liveFirmware: String? = firmware
    val log = mutableListOf<String>()

    override fun suspendForFirmwareUpdate() {
        log += "suspend"
        connection = DeviceStore.Connection.Disconnected
        liveFirmware = null
    }

    override fun resumeAfterFirmwareUpdate() {
        log += "resume"
    }
}

/** Port of `FirmwareStoreTests`. */
@OptIn(ExperimentalCoroutinesApi::class)
class FirmwareStoreTest {
    private val release = FirmwareRelease("3.0.22", null, "https://example.com/omi.zip", isLegacySecureDFU = false, notes = "Better battery")
    private var clock = 1_790_000_000_000L
    private val prefs = freshPreferences()

    @Test fun offersANewerReleaseAndChecksAtMostOnceADay() = runTest {
        val api = fakeAPI { "latestFirmware" returns release }
        val store = FirmwareStore(api.client, FakeFirmwareHost(), FakeUpdater(), prefs, backgroundScope, { File("x.zip") }, now = { clock }, handOverDelayMillis = 0)
        store.checkIfDue()
        assertEquals("3.0.22", store.available?.version)
        clock += 3_600_000
        store.checkIfDue()
        assertEquals(1, api.called("latestFirmware").size)
        clock += 24 * 3_600_000L
        store.checkIfDue()
        assertEquals(2, api.called("latestFirmware").size)
        // The same version, an older one, a legacy bootloader or an unmet minimum is no update.
        assertFalse(release.isUpdate("3.0.22"))
        assertFalse(release.isUpdate("v3.0.23"))
        assertFalse(release.copy(isLegacySecureDFU = true).isUpdate("3.0.21"))
        assertFalse(release.copy(minVersion = "3.0.0").isUpdate("2.9"))
        assertFalse(release.isUpdate("Unknown"))
        assertTrue(release.isUpdate("v3.0.21"))
    }

    @Test fun aFailedCheckWaitsBeforeAskingAgain() = runTest {
        val api = fakeAPI { "latestFirmware" throws APIError.Transport("offline") }
        val store = FirmwareStore(api.client, FakeFirmwareHost(), FakeUpdater(), prefs, backgroundScope, { File("x.zip") }, now = { clock })
        store.checkIfDue()
        store.checkIfDue()
        assertEquals(1, api.called("latestFirmware").size)
        assertNull(store.available)
    }

    @Test fun installFlashesAndWaitsForTheNewVersion() = runTest {
        val api = fakeAPI { "latestFirmware" returns release }
        val host = FakeFirmwareHost()
        val updater = FakeUpdater()
        val file = File.createTempFile("omi-test", ".zip")
        val store = FirmwareStore(api.client, host, updater, prefs, backgroundScope, { file }, now = { clock }, handOverDelayMillis = 0)
        store.checkIfDue()
        store.install()
        assertEquals(FirmwareStore.Phase.Restarting, store.phase)
        assertEquals(listOf("suspend", "resume"), host.log)
        assertEquals(listOf(file), updater.flashed)
        assertFalse(file.exists())
        host.liveFirmware = "3.0.22"
        store.deviceInfoChanged()
        assertEquals(FirmwareStore.Phase.Finished("3.0.22"), store.phase)
        assertNull(store.available)
    }

    @Test fun installRefusesLowBatteryAndReportsAFailedFlash() = runTest {
        val api = fakeAPI { "latestFirmware" returns release }
        val host = FakeFirmwareHost()
        val updater = FakeUpdater().apply { failure = IllegalStateException("smp") }
        val store = FirmwareStore(api.client, host, updater, prefs, backgroundScope, { File.createTempFile("omi", ".zip") }, now = { clock }, handOverDelayMillis = 0)
        store.checkIfDue()
        host.battery = 19
        store.install()
        assertEquals(FirmwareStore.Phase.Failed(FirmwareStore.Failure.LowBattery), store.phase)
        assertTrue(updater.flashed.isEmpty())
        host.battery = 60
        store.dismissResult()
        store.install()
        assertEquals(FirmwareStore.Phase.Failed(FirmwareStore.Failure.Install), store.phase)
        assertEquals(listOf("suspend", "resume"), host.log)
    }
}
