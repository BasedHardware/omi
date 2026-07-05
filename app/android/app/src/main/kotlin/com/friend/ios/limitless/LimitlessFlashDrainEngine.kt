package com.friend.ios.limitless

import com.friend.ios.ble.OmiBleManager
import com.friend.ios.batch.LimitlessBatchAudioWriter

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * Native flash-drain engine for the Limitless pendant (Transcribe Later).
 *
 * With batch mode on, the pendant records to its onboard flash (the Dart connector
 * suppresses live streaming). This engine periodically drains that flash with the
 * Flutter engine idle or dead: it queries the storage state (msg21), switches the
 * pendant into download mode (msg8 {1,0}), reassembles the pushed flash pages,
 * appends the extracted opus frames to [LimitlessBatchAudioWriter], and ACKs (msg7)
 * — strictly after an fsync barrier, because an ACK deletes the pendant's copy.
 * When caught up (or stalled) it returns the pendant to record-to-flash ({0,0}).
 *
 * Runs inside [OmiBleForegroundService]; all state is confined to a single-thread
 * executor. Wire codec lives in [LimitlessProtocol] (pure, unit-tested against the
 * golden fixtures shared with the Dart connector).
 */
class LimitlessFlashDrainEngine(
    private val context: Context,
    private val writer: LimitlessBatchAudioWriter,
) {
    companion object {
        private const val TAG = "OmiBle.LimitlessDrain"
        private const val FLUTTER_PREFS = "FlutterSharedPreferences"
        private const val CYCLE_MS = 90_000L
        private const val FIRST_CYCLE_DELAY_MS = 5_000L
        private const val STATUS_TIMEOUT_MS = 8_000L
        private const val STALL_MS = 30_000L
        private const val STALL_CHECK_MS = 5_000L
        private const val ACK_EVERY_PAGES = 25
        private const val STORAGE_FULL_FRACTION = 0.05
    }

    private enum class Phase { IDLE, AWAITING_STATUS, DRAINING }

    private data class Config(val deviceId: String, val serviceUuid: String, val characteristicUuid: String)

    private val executor = Executors.newSingleThreadScheduledExecutor { r ->
        Thread(r, "limitless-drain").apply { isDaemon = true }
    }

    // All fields below are executor-confined.
    private var phase = Phase.IDLE
    private var deviceAddress: String? = null
    private var messageIndex = 0
    private var requestId = 0L
    private val fragmentBuffer = mutableMapOf<Int, MutableMap<Int, ByteArray>>()
    private var endPage = 0
    private var maxSeenPageIndex = -1
    private var lastAppendedPageIndex = -1
    private var lastAckedPageIndex = -1
    private var pagesSinceAck = 0
    private var lastPageAtMs = 0L
    private var cycleTask: ScheduledFuture<*>? = null
    private var statusTimeoutTask: ScheduledFuture<*>? = null
    private var stallCheckTask: ScheduledFuture<*>? = null

    fun onDeviceReady(address: String) {
        executor.execute {
            val config = loadConfig()
            if (config != null && !config.deviceId.equals(address, ignoreCase = true)) return@execute
            deviceAddress = address
            if (phase != Phase.DRAINING) setBoolPref("pendantDraining", false)
            cycleTask?.cancel(false)
            cycleTask = executor.scheduleWithFixedDelay({ runCycle() }, FIRST_CYCLE_DELAY_MS, CYCLE_MS, TimeUnit.MILLISECONDS)
        }
    }

    fun onDeviceDisconnected(address: String) {
        executor.execute {
            if (!address.equals(deviceAddress, ignoreCase = true)) return@execute
            cycleTask?.cancel(false)
            cycleTask = null
            resetDrainState("disconnected")
            deviceAddress = null
            messageIndex = 0
            requestId = 0
            writer.stop("ble_disconnected")
        }
    }

    fun stop(reason: String) {
        executor.execute {
            cycleTask?.cancel(false)
            cycleTask = null
            resetDrainState(reason)
        }
        writer.stop(reason)
    }

    fun handleCharacteristic(address: String, serviceUuid: String, characteristicUuid: String, value: ByteArray) {
        val config = loadConfig() ?: return
        if (!config.deviceId.equals(address, ignoreCase = true)) return
        if (!config.serviceUuid.equals(serviceUuid, ignoreCase = true)) return
        if (!config.characteristicUuid.equals(characteristicUuid, ignoreCase = true)) return
        executor.execute { processPacket(value) }
    }

    // ── Cycle (executor) ──

    private fun runCycle() {
        val address = deviceAddress ?: return
        if (phase != Phase.IDLE) return
        val config = loadConfig()
        if (config == null) {
            writer.stop("batch_disabled")
            return
        }
        if (!config.deviceId.equals(address, ignoreCase = true)) return

        phase = Phase.AWAITING_STATUS
        write(address, LimitlessProtocol.encodeSetCurrentTime(messageIndex++, ++requestId, System.currentTimeMillis()))
        write(address, LimitlessProtocol.encodeGetDeviceStatus(messageIndex++, ++requestId))
        statusTimeoutTask?.cancel(false)
        statusTimeoutTask = executor.schedule({
            if (phase == Phase.AWAITING_STATUS) {
                Log.w(TAG, "storage status timed out — retrying next cycle")
                phase = Phase.IDLE
            }
        }, STATUS_TIMEOUT_MS, TimeUnit.MILLISECONDS)
    }

    private fun processPacket(data: ByteArray) {
        if (phase == Phase.AWAITING_STATUS) {
            LimitlessProtocol.parseDeviceStatus(data)?.let { onStorageState(it) }
        }

        val packet = LimitlessProtocol.parseBlePacket(data) ?: return
        fragmentBuffer.getOrPut(packet.index) { mutableMapOf() }[packet.seq] = packet.payload
        val fragments = fragmentBuffer[packet.index] ?: return
        if (fragments.size != packet.numFrags) return

        var totalSize = 0
        for (i in 0 until packet.numFrags) {
            totalSize += fragments[i]?.size ?: 0
        }
        val complete = ByteArray(totalSize)
        var offset = 0
        for (i in 0 until packet.numFrags) {
            val fragment = fragments[i] ?: continue
            fragment.copyInto(complete, offset)
            offset += fragment.size
        }
        fragmentBuffer.remove(packet.index)

        if (phase == Phase.DRAINING) {
            for (page in LimitlessProtocol.parsePendantMessage(complete)) {
                processFlashPage(page)
            }
        }
    }

    private fun onStorageState(state: LimitlessProtocol.StorageState) {
        publishStorageState(state)
        if (phase != Phase.AWAITING_STATUS) return
        statusTimeoutTask?.cancel(false)

        val pageCount = state.newestFlashPage - state.oldestFlashPage + 1
        if (state.newestFlashPage < state.oldestFlashPage || pageCount <= 0) {
            phase = Phase.IDLE
            return
        }

        val address = deviceAddress ?: run { phase = Phase.IDLE; return }
        fragmentBuffer.clear()
        endPage = state.newestFlashPage
        maxSeenPageIndex = -1
        lastAppendedPageIndex = -1
        lastAckedPageIndex = -1
        pagesSinceAck = 0
        lastPageAtMs = System.currentTimeMillis()
        phase = Phase.DRAINING
        setBoolPref("pendantDraining", true)
        Log.i(TAG, "drain start: pages ${state.oldestFlashPage}..${state.newestFlashPage} ($pageCount)")
        write(address, LimitlessProtocol.encodeDownloadFlashPages(messageIndex++, ++requestId, batchMode = true, realTime = false))

        stallCheckTask?.cancel(false)
        stallCheckTask = executor.scheduleWithFixedDelay({
            if (phase == Phase.DRAINING && System.currentTimeMillis() - lastPageAtMs > STALL_MS) {
                finishDrain("stall")
            }
        }, STALL_CHECK_MS, STALL_CHECK_MS, TimeUnit.MILLISECONDS)
    }

    private fun processFlashPage(page: LimitlessProtocol.FlashPage) {
        lastPageAtMs = System.currentTimeMillis()
        val index = page.index ?: return

        if (page.opusFrames.isNotEmpty()) {
            if (!writer.append(page.opusFrames, page.timestampMs)) {
                Log.w(TAG, "append failed (storage guard?) — pausing drain without ACKing unwritten pages")
                finishDrain("append_failed")
                return
            }
        }
        lastAppendedPageIndex = maxOf(lastAppendedPageIndex, index)
        maxSeenPageIndex = maxOf(maxSeenPageIndex, index)
        pagesSinceAck++

        if (pagesSinceAck >= ACK_EVERY_PAGES) {
            if (!ackWritten()) {
                finishDrain("fsync_failed")
                return
            }
        }
        if (maxSeenPageIndex >= endPage) {
            finishDrain("caught_up")
        }
    }

    /** fsync barrier, then ACK everything appended so far. Never ACKs unwritten pages.
     *  On a failed barrier the watermark rolls back to the last ACK — a later ACK is
     *  up-to-index and would otherwise cover the unconfirmed pages — and the caller
     *  must end the drain so those pages redeliver next cycle. */
    private fun ackWritten(): Boolean {
        val address = deviceAddress ?: return true
        if (lastAppendedPageIndex <= lastAckedPageIndex) return true
        if (!writer.sync()) {
            Log.w(TAG, "fsync failed — dropping ACK watermark, pages redrain next cycle")
            lastAppendedPageIndex = lastAckedPageIndex
            return false
        }
        write(address, LimitlessProtocol.encodeAcknowledgeProcessedData(messageIndex++, ++requestId, lastAppendedPageIndex))
        lastAckedPageIndex = lastAppendedPageIndex
        pagesSinceAck = 0
        return true
    }

    private fun finishDrain(reason: String) {
        if (phase != Phase.DRAINING) return
        stallCheckTask?.cancel(false)
        stallCheckTask = null
        ackWritten()
        val address = deviceAddress
        // Return the pendant to record-to-flash — unless batch mode was turned off
        // mid-drain, in which case the Dart connector owns the mode ({0,1}) and a
        // late {0,0} here would silently stop realtime streaming.
        if (address != null && loadConfig() != null) {
            write(address, LimitlessProtocol.encodeDownloadFlashPages(messageIndex++, ++requestId, batchMode = false, realTime = false))
        }
        phase = Phase.IDLE
        setBoolPref("pendantDraining", false)
        Log.i(TAG, "drain finished ($reason): appended<=$lastAppendedPageIndex acked<=$lastAckedPageIndex end=$endPage")
    }

    private fun resetDrainState(reason: String) {
        statusTimeoutTask?.cancel(false)
        stallCheckTask?.cancel(false)
        statusTimeoutTask = null
        stallCheckTask = null
        fragmentBuffer.clear()
        if (phase == Phase.DRAINING) {
            Log.i(TAG, "drain aborted ($reason): acked<=$lastAckedPageIndex")
            setBoolPref("pendantDraining", false)
        }
        phase = Phase.IDLE
    }

    // ── IO helpers ──

    private fun write(address: String, data: ByteArray) {
        OmiBleManager.instance.writeCharacteristic(
            address,
            limitlessServiceUuid(),
            limitlessTxCharUuid(),
            data,
        ) { result ->
            result.exceptionOrNull()?.let { Log.w(TAG, "TX write failed: ${it.message}") }
        }
    }

    private fun limitlessServiceUuid() = "632de001-604c-446b-a80f-7963e950f3fb"

    private fun limitlessTxCharUuid() = "632de002-604c-446b-a80f-7963e950f3fb"

    private fun publishStorageState(state: LimitlessProtocol.StorageState) {
        val pageCount = (state.newestFlashPage - state.oldestFlashPage + 1).coerceAtLeast(0)
        try {
            val editor = prefs().edit()
            editor.putLong("flutter.pendantPagesStored", pageCount.toLong())
            if (state.totalCapturePages > 0) {
                val almostFull = state.freeCapturePages < state.totalCapturePages * STORAGE_FULL_FRACTION
                editor.putBoolean("flutter.pendantStorageAlmostFull", almostFull)
            }
            editor.apply()
        } catch (_: Exception) {
        }
    }

    private fun setBoolPref(key: String, value: Boolean) {
        try {
            prefs().edit().putBoolean("flutter.$key", value).apply()
        } catch (_: Exception) {
        }
    }

    // ── Config ──

    private fun loadConfig(): Config? {
        if (prefValue("batchModeEnabled") != true) return null
        val raw = prefValue("nativeBleStreamConfig") as? String ?: return null
        if (raw.isEmpty()) return null
        return try {
            val json = JSONObject(raw)
            if (json.optString("deviceType") != "limitless") return null
            val deviceId = json.optString("deviceId")
            val serviceUuid = json.optString("serviceUuid").lowercase(Locale.US)
            val characteristicUuid = json.optString("characteristicUuid").lowercase(Locale.US)
            if (deviceId.isEmpty() || serviceUuid.isEmpty() || characteristicUuid.isEmpty()) return null
            Config(deviceId, serviceUuid, characteristicUuid)
        } catch (_: Exception) {
            null
        }
    }

    private fun prefs() = context.getSharedPreferences(FLUTTER_PREFS, Context.MODE_PRIVATE)

    private fun prefValue(key: String): Any? = prefs().all["flutter.$key"]
}
