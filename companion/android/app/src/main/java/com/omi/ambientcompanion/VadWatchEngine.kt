package com.omi.ambientcompanion

import kotlin.math.log10
import kotlin.math.sqrt

data class VadFrameResult(
    val speech: Boolean,
    val dbfs: Double,
    val zeroRatio: Double,
)

class VadWatchEngine(
    private val rmsSpeechDbfsThreshold: Double = -52.0,
    private val zeroRatioSilenceThreshold: Double = 0.98,
    private val speechFramesToTrigger: Int = 4,
    private val silenceFramesToEnd: Int = 80,
    private val preRollBytes: Int = 16_000 * 2 * 15,
) {
    private val preRoll = ArrayDeque<ByteArray>()
    private var preRollSize = 0
    private var speechFrames = 0
    private var silenceFrames = 0
    var activeSpeech: Boolean = false
        private set

    fun accept(bytes: ByteArray): VadFrameResult {
        addPreRoll(bytes)
        val result = analyzePcm16(bytes)
        val looksLikeSpeech = result.dbfs >= rmsSpeechDbfsThreshold && result.zeroRatio < zeroRatioSilenceThreshold
        if (looksLikeSpeech) {
            speechFrames += 1
            silenceFrames = 0
        } else {
            silenceFrames += 1
            speechFrames = 0
        }
        if (!activeSpeech && speechFrames >= speechFramesToTrigger) activeSpeech = true
        if (activeSpeech && silenceFrames >= silenceFramesToEnd) activeSpeech = false
        return result.copy(speech = looksLikeSpeech)
    }

    fun drainPreRoll(): List<ByteArray> {
        val copy = preRoll.toList()
        preRoll.clear()
        preRollSize = 0
        return copy
    }

    private fun addPreRoll(bytes: ByteArray) {
        preRoll.add(bytes.copyOf())
        preRollSize += bytes.size
        while (preRollSize > preRollBytes && preRoll.isNotEmpty()) {
            preRollSize -= preRoll.removeFirst().size
        }
    }

    companion object {
        fun analyzePcm16(bytes: ByteArray): VadFrameResult {
            if (bytes.size < 2) return VadFrameResult(false, -120.0, 1.0)
            var sumSquares = 0.0
            var zeroSamples = 0
            var samples = 0
            var i = 0
            while (i + 1 < bytes.size) {
                val sample = ((bytes[i + 1].toInt() shl 8) or (bytes[i].toInt() and 0xff)).toShort().toInt()
                if (sample == 0) zeroSamples++
                val normalized = sample / 32768.0
                sumSquares += normalized * normalized
                samples++
                i += 2
            }
            val rms = if (samples == 0) 0.0 else sqrt(sumSquares / samples)
            val dbfs = if (rms <= 0.0000001) -120.0 else 20.0 * log10(rms)
            return VadFrameResult(dbfs >= -52.0, dbfs, zeroSamples.toDouble() / samples.coerceAtLeast(1))
        }
    }
}
