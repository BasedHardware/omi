package com.friend.ios.ble

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Pins the capture-first invariants of the BLE foreground service against the
 * real Kotlin source. The retention probe is an optional battery optimization;
 * the audio CCCD write is the product, so no probe work may precede or delay
 * it on the serial GATT queue (AGENTS.md: never lose user audio), and a
 * completed retention proof may only be consumed by the connection it was
 * proven on.
 */
class RetentionCaptureOrderingContractTest {
    private fun serviceSource(): String {
        val relativePath = "app/android/app/src/main/kotlin/com/friend/ios/ble/OmiBleForegroundService.kt"
        return generateSequence(File(System.getProperty("user.dir") ?: ".").absoluteFile) { it.parentFile }
            .map { File(it, relativePath) }
            .firstOrNull { it.isFile }
            ?.readText()
            ?: error("Could not locate $relativePath")
    }

    private fun lifecycleSource(): String {
        val relativePath = "app/android/app/src/main/kotlin/com/friend/ios/ble/RetentionProbeLifecycle.kt"
        return generateSequence(File(System.getProperty("user.dir") ?: ".").absoluteFile) { it.parentFile }
            .map { File(it, relativePath) }
            .firstOrNull { it.isFile }
            ?.readText()
            ?: error("Could not locate $relativePath")
    }

    @Test
    fun `fireDeviceReady subscribes audio before any retention work`() {
        val source = serviceSource()
        val body = source.substringAfter("private fun fireDeviceReady").substringBefore("private fun ensureBackgroundAudioSubscription")
        val subscribe = body.indexOf("ensureBackgroundAudioSubscription(addr, services)")
        val record = body.indexOf("recordVerifiedRetention(addr, services)")
        val probe = body.indexOf("probeRetentionRuntime(addr)")
        assertTrue("audio subscription must run inside fireDeviceReady", subscribe >= 0)
        assertTrue("retention advertisement recording must run inside fireDeviceReady", record >= 0)
        assertTrue("retention probe must run inside fireDeviceReady", probe >= 0)
        assertTrue("audio subscription must precede retention advertisement recording", subscribe < record)
        assertTrue("audio subscription must precede the retention probe read", subscribe < probe)
        // The probe is gated on an audio subscription being queued: with no
        // native target and Flutter alive, the probe waits behind Dart's
        // onDeviceReady post so Dart's own subscription can win the queue.
        assertTrue(
            "probe must be deferred behind the Flutter onDeviceReady post when no native subscription was queued",
            body.contains("OmiBleManager.isFlutterAlive -> bleManager.mainHandler.post { probeRetentionRuntime(addr) }"),
        )
    }

    @Test
    fun `retention probe read cannot join the serial queue ahead of the audio CCCD write`() {
        val source = serviceSource()
        // The probe enqueue is posted through the same looper the subscription
        // uses, so it always lands behind subscribeCharacteristic's deferred
        // enqueue; a direct readCharacteristic call would win that race.
        val body = source.substringAfter("private fun probeRetentionRuntime").substringBefore("private fun retireRetentionProbe")
        assertTrue(
            "probe read must be deferred via mainHandler.post behind the subscription enqueue",
            body.contains("mainHandler.post"),
        )
        val directCall = Regex("readCharacteristic\\((address|addr)").findAll(body).toList()
        assertTrue(
            "probe read must not be enqueued directly from the ready path",
            directCall.all { match ->
                val prefix = body.substring(0, match.range.first)
                prefix.substringAfterLast("mainHandler.post", "").isNotEmpty()
            },
        )
    }

    @Test
    fun `disconnection cancels the in-flight probe without erasing a completed proof`() {
        val lifecycle = lifecycleSource()
        val cancel = lifecycle.substringAfter("fun cancel()").substringBefore("/** Retired attempts")
        assertTrue("cancel() must not clear the completed verification", !cancel.contains("resetVerification()"))
        val service = serviceSource()
        val retire = service.substringAfter("private fun retireRetentionProbe").substringBefore("private fun mapGattServices")
        assertTrue("disconnection must not reset verification", !retire.contains("resetVerification()"))
        assertTrue("disconnection must cancel only the in-flight probe", retire.contains("retentionProbe.cancel()"))
    }

    @Test
    fun `a new GATT connection invalidates the stale retention proof before retry logic can consume it`() {
        val service = serviceSource()
        val connect = service.substringAfter("override fun onGattConnected").substringBefore("override fun onGattDisconnected")
        assertTrue("connect must reset the stale retention proof", connect.contains("retentionProbe.resetVerification()"))
        assertTrue("connect must also clear the advertisement flag", connect.contains("hasVerifiedRetention = false"))
        assertTrue("connect must reset the bounded re-probe budget", connect.contains("retentionReprobes = 0"))
        val backoff = BleReconnectBackoff()
        // And the predicate it gates: RTC-less storage never licenses escalation.
        val timeless = java.nio.ByteBuffer.allocate(16).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            .putInt(0).putInt(0).putInt(4096).putInt(0).array()
        assertEquals(3_000L, backoff.delayForFailure("AA", false, null, BleReconnectBackoff.retentionProbeSucceeds(timeless)))
    }

    @Test
    fun `the disconnect path retires the in-flight probe before retry logic consumes verification`() {
        // Refutation pin for the original finding 3 ("stale proof consumed on a
        // pre-ready disconnect"): handleDisconnection calls retireRetentionProbe
        // BEFORE handleRetryLogic, so at retry-selection time an in-flight probe
        // is already cancelled on this path — a never-completed probe cannot be
        // consumed, and RetentionProbeLifecycle.result rejects retired probes.
        val service = serviceSource()
        val disconnect = service.substringAfter("private fun handleDisconnection").substringBefore("private fun handleRetryLogic")
        val retire = disconnect.indexOf("retireRetentionProbe(managed)")
        val retry = disconnect.indexOf("handleRetryLogic(addr, status)")
        assertTrue("disconnect must retire the probe", retire >= 0)
        assertTrue("disconnect must select the retry delay", retry >= 0)
        assertTrue("probe retirement must precede retry selection", retire < retry)
        // And a probe cancelled before completion can never verify anything.
        val state = RetentionProbeLifecycle()
        val gatt = Any()
        val probe = state.start(gatt)!!
        state.cancel()
        assertTrue(!state.result(probe, gatt, true, storageStatusWithClock))
        assertEquals(false, state.runtimeVerified)
    }

    private val storageStatusWithClock = java.nio.ByteBuffer.allocate(16).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        .putInt(0).putInt(0).putInt(4096).putInt(1).array()

    @Test
    fun `the post-clock-sync re-probe is bounded and bound to its originating link`() {
        val service = serviceSource()
        assertTrue(
            "re-probe scheduling must be guarded by the per-link budget",
            service.contains("attempt <= RETENTION_MAX_REPROBES"),
        )
        assertTrue(
            "scheduling a re-probe must consume the budget",
            service.contains("managed.retentionReprobes = attempt"),
        )
        // A stale callback must not fire on a successor GATT: the scheduled
        // probe checks the current connection against the originating GATT.
        assertTrue(
            "re-probe must be bound to its originating GATT",
            service.contains("if (bleManager.connectedGatts[addr] !== gatt) return@postDelayed"),
        )
    }
}
