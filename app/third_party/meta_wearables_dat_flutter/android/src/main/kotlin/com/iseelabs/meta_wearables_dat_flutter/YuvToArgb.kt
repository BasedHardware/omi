// CPU-side I420 → ARGB conversion.
//
// Used only by [MetaSessionManager]. Single-threaded; perf is fine for
// 720p@30fps on every Android device that meets minSdk 31.
//
// Layout assumption: Meta DAT SDK 0.6.x VideoFrame.buffer is documented
// (and verified at runtime via `c2.android.hevc.decoder` config diff:
// `raw.pixel-format = 35` = YUV420_FLEXIBLE / I420, `stride = width`,
// `vstride = height`) as a tightly-packed I420 plane triple:
//
//     [ Y(w*h) | U(w/2 * h/2) | V(w/2 * h/2) ] = w * h * 3 / 2 bytes.
//
// The reference Android sample at
// https://github.com/facebook/meta-wearables-dat-android (see
// `samples/CameraAccess/.../stream/YuvToBitmapConverter.kt`) is
// hardcoded to the same shape, so any cross-format probing on our side
// is dead code at best and a source of subtle render bugs at worst.
//
// Colour conversion: BT.709 limited range (studio swing). The HEVC
// decoder advertises `raw.color.matrix = 1` (= BT.709 in C2 enums)
// when decoding frames from the glasses, which matches the official
// sample's hardcoded BT.709 path. Using BT.601 coefficients here
// produces a visible green/yellow cast on natural scenes.

package com.iseelabs.meta_wearables_dat_flutter

import android.graphics.Bitmap
import java.nio.ByteBuffer

internal object YuvToArgb {
    // Scratch buffers reused across frames to keep the hot path
    // allocation-free. At 30 fps the YUV input is ~1.4 MiB and the
    // ARGB output is ~3.6 MiB per frame, so allocating per frame
    // causes ~150 MiB/s of GC pressure on the 720p stream. The
    // official Meta sample's `YuvToBitmapConverter` does the same
    // caching for the same reason.
    private val lock = Any()
    private var yuvBytes: ByteArray = ByteArray(0)
    private var pixels: IntArray = IntArray(0)

    /**
     * Converts a tightly-packed I420 [yuvData] buffer to ARGB pixels in
     * [output]. The buffer must contain `Y(w*h) | U(w*h/4) | V(w*h/4)`
     * = `w * h * 3 / 2` bytes. The caller's [yuvData] position is
     * preserved (we read through a duplicate).
     *
     * Returns silently when the buffer is too small for the declared
     * dimensions or when [width] / [height] are not even — the caller
     * can fall through to a no-op for the frame.
     */
    fun convert(
        yuvData: ByteBuffer,
        width: Int,
        height: Int,
        output: Bitmap,
    ) {
        if (width <= 0 || height <= 0) return
        if (width and 1 != 0 || height and 1 != 0) return

        val frameSize = width * height
        val expected = frameSize + (frameSize shr 1)
        if (yuvData.remaining() < expected) return

        synchronized(lock) {
            if (yuvBytes.size < expected) yuvBytes = ByteArray(expected)
            if (pixels.size < frameSize) pixels = IntArray(frameSize)

            val src = yuvData.duplicate().apply { position(yuvData.position()) }
            src.get(yuvBytes, 0, expected)

            convertI420ToArgb(yuvBytes, pixels, width, height)
            output.setPixels(pixels, 0, width, 0, 0, width, height)
        }
    }

    /**
     * Converts I420 YUV bytes directly to ARGB pixel ints.
     *
     * BT.709 limited range, fixed-point with 10-bit precision. Math
     * matches the official Meta DAT Android sample byte-for-byte (see
     * `YuvToBitmapConverter.convertI420ToArgb` in
     * `meta-wearables-dat-android`):
     *
     *     R = 1.164 * (Y - 16) + 1.793 * (V - 128)
     *     G = 1.164 * (Y - 16) - 0.213 * (U - 128) - 0.533 * (V - 128)
     *     B = 1.164 * (Y - 16) + 2.112 * (U - 128)
     *
     * Coefficients are scaled by 1024 = 2^10 so the multiplies and
     * one right-shift produce the same value as the float form.
     */
    private fun convertI420ToArgb(
        yuvBytes: ByteArray,
        argbOut: IntArray,
        width: Int,
        height: Int,
    ) {
        val frameSize = width * height
        val uvPlaneSize = frameSize shr 2

        val uOffset = frameSize
        val vOffset = uOffset + uvPlaneSize

        // BT.709 limited range fixed-point coefficients (×1024).
        val coeffVr = 1836 // 1.793 * 1024
        val coeffUg = 218  // 0.213 * 1024
        val coeffVg = 546  // 0.533 * 1024
        val coeffUb = 2163 // 2.112 * 1024

        val halfWidth = width shr 1
        var pixelIndex = 0

        for (row in 0 until height) {
            val uvRowOffset = (row shr 1) * halfWidth

            for (col in 0 until width) {
                val uvIndex = uvRowOffset + (col shr 1)

                val y = (yuvBytes[pixelIndex].toInt() and 0xff) - 16
                val u = (yuvBytes[uOffset + uvIndex].toInt() and 0xff) - 128
                val v = (yuvBytes[vOffset + uvIndex].toInt() and 0xff) - 128

                // Y scaled from 16-235 to 0-255: 255/219 ≈ 1.164 → ×1192/1024
                val yScaled = (y * 1192) shr 10

                val r = yScaled + ((coeffVr * v) shr 10)
                val g = yScaled - ((coeffUg * u + coeffVg * v) shr 10)
                val b = yScaled + ((coeffUb * u) shr 10)

                // Branchless clamp to 0..255 — avoids branch mispredict
                // on hot inner loop. `(x shr 31).inv()` is 0xffffffff for
                // x ≥ 0, 0 otherwise; the second mask reflects 255 - x.
                val rClamped = (r and (r shr 31).inv()) or ((255 - r) shr 31 and 255) and 255
                val gClamped = (g and (g shr 31).inv()) or ((255 - g) shr 31 and 255) and 255
                val bClamped = (b and (b shr 31).inv()) or ((255 - b) shr 31 and 255) and 255

                argbOut[pixelIndex] =
                    0xff000000.toInt() or (rClamped shl 16) or (gClamped shl 8) or bClamped

                pixelIndex++
            }
        }
    }
}
