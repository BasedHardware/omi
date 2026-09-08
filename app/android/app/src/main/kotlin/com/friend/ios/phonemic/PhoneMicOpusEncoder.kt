package com.friend.ios.phonemic

import android.util.Log

/**
 * Native opus encoder for batch (transcribe-later) phone-mic capture — the Kotlin
 * peer of iOS `PhoneMicOpusEncoder`. Takes the PCM16 little-endian mono @16kHz
 * chunks the converter pipeline emits and produces exact 20ms opus packets, one
 * length-prefixed frame per packet — the same on-disk shape (`opus_fs320`,
 * 50 packets/sec) the BLE batch writers use.
 *
 * One instance per batch session: created at batch bring-up and kept alive across
 * file rotations *and* engine rebuilds (interruption/route/media-reset), so the
 * resampler-fed byte stream is encoded contiguously. The backend decodes every file
 * with a fresh decoder, so mid-stream file boundaries are harmless — this matches how
 * Limitless pendant files are produced.
 *
 * libopus itself ships in the APK via the opus_flutter_android plugin (soname
 * `libopus.so`, all four ABIs, full C API exported). The thin JNI shim
 * `libphonemicopus.so` resolves the four entry points it needs by dlopen/dlsym at
 * first [create]; see `phone_mic_opus_jni.c` for why opus's headers can't be
 * referenced from a repo build.
 *
 * Confinement: every method runs on the controller's single audio executor. libopus's
 * encoder state is stateful and not thread-safe, and the [carry] buffer is plain
 * (unlocked) state — there are deliberately no locks here because there is exactly one
 * caller thread.
 */
class PhoneMicOpusEncoder private constructor(private var handle: Long) {
    /**
     * Sub-frame remainder carried between [encode] calls until it completes a whole
     * 320-sample (640-byte) frame.
     */
    private var carry = ByteArray(0)

    /**
     * Encode every whole 320-sample frame available once [pcm] is appended to the
     * carry, returning one opus packet per frame. Any sub-frame tail stays buffered
     * for the next call. A frame that fails to encode is logged and dropped; the
     * remaining frames still encode.
     */
    fun encode(pcm: ByteArray): List<ByteArray> {
        if (handle == 0L || pcm.isEmpty()) return emptyList()
        carry = if (carry.isEmpty()) pcm else carry + pcm
        if (carry.size < FRAME_BYTES) return emptyList()

        val packets = ArrayList<ByteArray>()
        var offset = 0
        while (carry.size - offset >= FRAME_BYTES) {
            val frame = carry.copyOfRange(offset, offset + FRAME_BYTES)
            offset += FRAME_BYTES
            val packet = nativeEncodeFrame(handle, frame)
            if (packet != null) {
                packets.add(packet)
            } else {
                Log.w(TAG, "opus encode returned null for a frame — dropping it")
            }
        }
        carry = if (offset == carry.size) ByteArray(0) else carry.copyOfRange(offset, carry.size)
        return packets
    }

    /**
     * Drop the buffered sub-frame remainder. Called at every capture gap (engine
     * teardown / interruption) so pre- and post-gap audio is never spliced into one
     * opus frame.
     */
    fun discardPartial() {
        carry = ByteArray(0)
    }

    /**
     * Destroy the native encoder. Idempotent — a zero handle is a no-op, so it is safe
     * to call twice (e.g. explicit teardown followed by a defensive close).
     */
    fun destroy() {
        if (handle == 0L) return
        nativeDestroy(handle)
        handle = 0L
    }

    companion object {
        private const val TAG = "PhoneMicOpus"

        // iOS-identical framing constants.
        private const val SAMPLE_RATE = 16000
        private const val CHANNELS = 1
        private const val APPLICATION_VOIP = 2048 // OPUS_APPLICATION_VOIP
        private const val BITRATE = 32000
        // 320 samples = 20ms @ 16kHz; 640 bytes as PCM16 mono. opus requires an exact
        // frame size, so partial chunks are buffered in [carry] until a whole frame lands.
        private const val FRAME_BYTES = 640

        @Volatile
        private var librariesLoaded = false

        /**
         * Create an encoder, or null when the native libraries or the encoder itself
         * cannot be brought up (the caller then raises `opus_init_failed`). Loads
         * `libopus` first so the shim can dlsym its symbols from the already-mapped
         * library, then the shim `libphonemicopus`; any Throwable (missing ABI, link
         * error, native create failure) is swallowed into a null return so a bring-up
         * failure never crashes the app.
         */
        fun create(): PhoneMicOpusEncoder? {
            if (!ensureLibrariesLoaded()) return null
            val handle =
                try {
                    nativeCreate(SAMPLE_RATE, CHANNELS, APPLICATION_VOIP, BITRATE)
                } catch (t: Throwable) {
                    Log.e(TAG, "nativeCreate threw", t)
                    0L
                }
            if (handle == 0L) {
                Log.e(TAG, "opus encoder create failed")
                return null
            }
            return PhoneMicOpusEncoder(handle)
        }

        @Synchronized
        private fun ensureLibrariesLoaded(): Boolean {
            if (librariesLoaded) return true
            return try {
                System.loadLibrary("opus") // libopus.so, shipped by opus_flutter_android
                System.loadLibrary("phonemicopus") // our JNI shim
                librariesLoaded = true
                true
            } catch (t: Throwable) {
                Log.e(TAG, "failed to load opus native libraries", t)
                false
            }
        }

        @JvmStatic
        private external fun nativeCreate(sampleRate: Int, channels: Int, application: Int, bitrate: Int): Long

        @JvmStatic
        private external fun nativeEncodeFrame(handle: Long, pcm: ByteArray): ByteArray?

        @JvmStatic
        private external fun nativeDestroy(handle: Long)
    }
}
