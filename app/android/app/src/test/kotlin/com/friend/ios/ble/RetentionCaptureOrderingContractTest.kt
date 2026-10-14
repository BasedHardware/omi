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
        val backoff = BleReconnectBackoff()
        // And the predicate it gates: RTC-less storage never licenses escalation.
        val timeless = java.nio.ByteBuffer.allocate(16).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            .putInt(0).putInt(0).putInt(4096).putInt(0).array()
        assertEquals(3_000L, backoff.delayForFailure("AA", false, null, BleReconnectBackoff.retentionProbeSucceeds(timeless)))
    }
}
