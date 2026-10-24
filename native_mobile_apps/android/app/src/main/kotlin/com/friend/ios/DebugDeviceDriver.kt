package com.friend.ios

import com.friend.ios.device.DeviceDriving
import com.friend.ios.device.OmiDeviceManager
import com.friend.ios.device.OmiDeviceManager.Event
import com.friend.ios.device.OmiGATT
import com.friend.ios.device.PairedDevice
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch

/**
 * Port of `DebugDeviceDriver.swift`: a pretend Omi for emulator QA (`--es omiFakeDevice
 * nearby|connected`, debug only; the emulator has no Bluetooth). "nearby" shows two Omis to pair
 * with, "connected" behaves like a paired Omi that is in range, with battery, firmware and every
 * control. No audio ever arrives.
 */
class DebugDeviceDriver : DeviceDriving {
    private val channel = Channel<Event>(Channel.UNLIMITED)
    override val events: Flow<Event> = channel.receiveAsFlow()
    private val scope = CoroutineScope(Dispatchers.Main)

    init {
        channel.trySend(Event.Bluetooth(OmiDeviceManager.BluetoothState.Ready))
    }

    override fun startScan() {
        channel.trySend(Event.Discovered(OmiDeviceManager.Discovery(PAIRED_ID, "Omi", -52)))
        channel.trySend(Event.Discovered(OmiDeviceManager.Discovery("0B:9E:2F:44:7A:1C", "Omi DevKit 2", -78)))
    }

    override fun stopScan() {}

    override fun connect(id: String) {
        channel.trySend(Event.Connecting(id))
        scope.launch {
            delay(600)
            channel.trySend(Event.Connected(id, "Omi"))
            channel.trySend(Event.Info(model = "Omi CV 1", firmware = "2.0.10", manufacturer = "Based Hardware", hardware = "CV1"))
            channel.trySend(Event.SerialNumber("OMI-24A7-91C3"))
            channel.trySend(
                Event.Features(
                    OmiGATT.Features.of(
                        OmiGATT.Features.button, OmiGATT.Features.battery, OmiGATT.Features.haptic,
                        OmiGATT.Features.offlineStorage, OmiGATT.Features.ledDimming, OmiGATT.Features.micGain,
                    ),
                ),
            )
            channel.trySend(Event.Battery(76))
            channel.trySend(Event.Charging(false))
            channel.trySend(Event.LedBrightness(60))
            channel.trySend(Event.MicGain(5))
            channel.trySend(Event.Codec(OmiGATT.Codec.Opus))
        }
    }

    override fun disconnect() {
        channel.trySend(Event.Disconnected(PAIRED_ID, null))
    }

    override fun readBattery() {
        channel.trySend(Event.Battery(76))
    }

    companion object {
        const val PAIRED_ID = "6F:1D:0C:3A:1B:2C"

        /** The encoded paired device a "connected" launch starts with. */
        val pairedJSON: String
            get() = PairedDevice(id = PAIRED_ID, name = "Omi", rssi = -52, modelNumber = "Omi CV 1", firmwareRevision = "2.0.10").encoded
    }
}
