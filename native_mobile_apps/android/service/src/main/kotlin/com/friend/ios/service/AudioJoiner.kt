package com.friend.ios.service

import com.friend.ios.core.models.AudioPart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Port of `AudioJoiner.swift`: joins a conversation's audio parts into one local file, as
 * Flutter's `AudioDownloadService`: MP3 parts are concatenated byte for byte, WAV parts get one
 * header over all their samples, and mixed formats fall back to the first part.
 */
object AudioJoiner {
    /** Downloads the cached parts in order and writes `<name>.mp3|wav` to [directory]. */
    suspend fun join(parts: List<AudioPart>, name: String, directory: File, download: suspend (String) -> ByteArray? = ::download): File? {
        val urls = parts.mapNotNull { it.url }
        if (urls.isEmpty()) return null
        val files = mutableListOf<ByteArray>()
        for (url in urls) files += download(url) ?: return null
        val wav = files.map(::isWAV)
        val (joined, ext) = when {
            wav.all { it } -> combineWAV(files) to "wav"
            wav.none { it } -> files.fold(ByteArray(0)) { acc, bytes -> acc + bytes } to "mp3"
            else -> files.first() to (if (wav.first()) "wav" else "mp3")
        }
        joined ?: return null
        return withContext(Dispatchers.IO) {
            runCatching {
                val target = File(directory, "$name.$ext")
                target.delete()
                target.writeBytes(joined)
                target
            }.getOrNull()
        }
    }

    private suspend fun download(url: String): ByteArray? = withContext(Dispatchers.IO) {
        runCatching {
            val connection = URL(url).openConnection() as HttpURLConnection
            try {
                if (connection.responseCode !in 200..299) null else connection.inputStream.use { it.readBytes() }
            } finally {
                connection.disconnect()
            }
        }.getOrNull()
    }

    fun isWAV(data: ByteArray): Boolean =
        data.size >= 12 && String(data, 0, 4, Charsets.US_ASCII) == "RIFF" && String(data, 8, 4, Charsets.US_ASCII) == "WAVE"

    /** One RIFF/WAVE file with the first part's format and every part's samples, in order. */
    fun combineWAV(files: List<ByteArray>): ByteArray? {
        var format: ByteArray? = null
        val samples = ByteArrayOutputStream()
        for (file in files) {
            val chunks = chunks(file) ?: return null
            val fmt = chunks.first ?: return null
            if (format == null) format = fmt
            samples.write(chunks.second)
        }
        val fmt = format ?: return null
        val data = samples.toByteArray()
        val out = ByteArrayOutputStream()
        out.write("RIFF".toByteArray(Charsets.US_ASCII))
        out.write(le32(4 + 8 + fmt.size + 8 + data.size))
        out.write("WAVE".toByteArray(Charsets.US_ASCII))
        out.write("fmt ".toByteArray(Charsets.US_ASCII))
        out.write(le32(fmt.size))
        out.write(fmt)
        out.write("data".toByteArray(Charsets.US_ASCII))
        out.write(le32(data.size))
        out.write(data)
        return out.toByteArray()
    }

    /** The `fmt ` body and the `data` body of a WAV file. */
    private fun chunks(file: ByteArray): Pair<ByteArray?, ByteArray>? {
        if (!isWAV(file)) return null
        var offset = 12
        var fmt: ByteArray? = null
        while (offset + 8 <= file.size) {
            val id = String(file, offset, 4, Charsets.US_ASCII)
            val size = (file[offset + 4].toInt() and 0xff) or ((file[offset + 5].toInt() and 0xff) shl 8) or
                ((file[offset + 6].toInt() and 0xff) shl 16) or ((file[offset + 7].toInt() and 0xff) shl 24)
            val body = offset + 8
            val end = minOf(file.size, body + size)
            if (id == "fmt ") fmt = file.copyOfRange(body, end)
            if (id == "data") return fmt to file.copyOfRange(body, end)
            offset = body + size + (size and 1)
        }
        return null
    }

    private fun le32(value: Int): ByteArray =
        byteArrayOf((value and 0xff).toByte(), ((value shr 8) and 0xff).toByte(), ((value shr 16) and 0xff).toByte(), ((value shr 24) and 0xff).toByte())
}
