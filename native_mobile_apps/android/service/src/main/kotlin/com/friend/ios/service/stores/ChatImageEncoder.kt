package com.friend.ios.service.stores

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.util.UUID
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Port of `ChatImageEncoder.swift`: photos travel as JPEG (the backend refuses HEIC), at most
 * [maxSide] pixels on the long side, turned upright as the camera recorded them.
 */
object ChatImageEncoder {
    /** The long side of a photo sent with a message. */
    const val maxSide = 2048
    /** The long side of the composer's thumbnail. */
    const val thumbnailSide = 240

    /** JPEG of [data] at most [maxSide] pixels on its long side, or null when it is not an image. */
    fun jpeg(data: ByteArray, maxSide: Int = ChatImageEncoder.maxSide, quality: Double = 0.85): ByteArray? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(data, 0, data.size, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
        var sample = 1
        while (max(bounds.outWidth, bounds.outHeight) / (sample * 2) >= maxSide) sample *= 2
        val decoded = BitmapFactory.decodeByteArray(data, 0, data.size, BitmapFactory.Options().apply { inSampleSize = sample }) ?: return null
        val longest = max(decoded.width, decoded.height)
        val scale = if (longest > maxSide) maxSide.toFloat() / longest else 1f
        val matrix = Matrix().apply {
            postScale(scale, scale)
            postRotate(rotation(data).toFloat())
        }
        val upright = if (scale != 1f || !matrix.isIdentity) Bitmap.createBitmap(decoded, 0, 0, decoded.width, decoded.height, matrix, true) else decoded
        return ByteArrayOutputStream().use { out ->
            upright.compress(Bitmap.CompressFormat.JPEG, (quality * 100).roundToInt(), out)
            out.toByteArray()
        }
    }

    /** A photo's file name with the `.jpg` it now is ("IMG_0042.HEIC" becomes "IMG_0042.jpg"). */
    fun jpegName(name: String?): String {
        val base = name?.substringBeforeLast('.', name)?.trim().orEmpty()
        return (base.ifEmpty { "photo-" + UUID.randomUUID().toString().take(8).lowercase() }) + ".jpg"
    }

    private fun rotation(data: ByteArray): Int = runCatching {
        when (ExifInterface(ByteArrayInputStream(data)).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
            ExifInterface.ORIENTATION_ROTATE_90 -> 90
            ExifInterface.ORIENTATION_ROTATE_180 -> 180
            ExifInterface.ORIENTATION_ROTATE_270 -> 270
            else -> 0
        }
    }.getOrDefault(0)
}

/** Attaches a photo from any source as JPEG (HEIC converted). False when it is no image. */
fun ChatStore.attachImage(data: ByteArray, filename: String? = null): Boolean {
    val jpeg = ChatImageEncoder.jpeg(data) ?: return false
    val preview = ChatImageEncoder.jpeg(jpeg, ChatImageEncoder.thumbnailSide, 0.7)
    attach(jpeg, ChatImageEncoder.jpegName(filename), "image/jpeg", preview)
    return true
}
