package com.friend.ios.network.endpoints

import com.friend.ios.network.customstt.CustomSTTConfig
import com.friend.ios.network.customstt.CustomSTTError
import com.friend.ios.network.customstt.CustomSTTProvider
import com.friend.ios.network.customstt.CustomSTTRequests
import com.friend.ios.network.customstt.CustomSTTSegment
import com.friend.ios.network.customstt.PCMWave
import okhttp3.Request
import okio.Buffer
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Port of `CustomSTTTests.swift`: the wire shapes of the user's own speech-to-text providers (Flutter `buildRequestConfig`). */
class CustomSTTTest {
    private fun body(request: Request): String = Buffer().also { request.body?.writeTo(it) }.readUtf8()

    @Test
    fun openAIUploadsAWavWithBearerAuthAndSegmentTimes() {
        val config = CustomSTTConfig(CustomSTTProvider.OpenAI, apiKey = "sk-test", language = "de")
        val request = CustomSTTRequests.upload(config, "WAV".toByteArray(), boundary = "B")
        assertEquals("https://api.openai.com/v1/audio/transcriptions", request.url.toString())
        assertEquals("Bearer sk-test", request.header("Authorization"))
        assertEquals("multipart/form-data; boundary=B", request.body?.contentType().toString())
        val text = body(request)
        assertTrue(text.contains("name=\"model\"\r\nContent-Length: 9\r\n\r\nwhisper-1\r\n"))
        assertTrue(text.contains("verbose_json"))
        assertTrue(text.contains("name=\"language\"\r\nContent-Length: 2\r\n\r\nde\r\n"))
        assertTrue(text.contains("filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\nContent-Length: 3\r\n\r\nWAV\r\n--B--"))
    }

    @Test
    fun detectSendsNoLanguageAndLocalWhisperNoKey() {
        val config = CustomSTTConfig(CustomSTTProvider.LocalWhisper, apiKey = "ignored", language = "multi", url = "http://192.0.2.5:8080/inference")
        val request = CustomSTTRequests.upload(config, ByteArray(0), boundary = "B")
        assertEquals("http://192.0.2.5:8080/inference", request.url.toString())
        assertNull(request.header("Authorization"))
        assertFalse(body(request).contains("name=\"language\""))
        assertTrue(body(request).contains("name=\"temperature\""))
    }

    @Test
    fun incompleteSetupsAreRefused() {
        assertFalse(CustomSTTConfig(CustomSTTProvider.OpenAI, apiKey = " ").isComplete)
        assertFalse(CustomSTTConfig(CustomSTTProvider.Custom, url = "ftp://x").isComplete)
        assertTrue(CustomSTTConfig(CustomSTTProvider.Custom).isComplete) // the default local endpoint
        val live = CustomSTTConfig(CustomSTTProvider.DeepgramLive, apiKey = "k")
        assertTrue(runCatching { CustomSTTRequests.upload(live, ByteArray(0)) }.exceptionOrNull() == CustomSTTError.Incomplete)
    }

    @Test
    fun answersBecomeSegments() {
        val openAI = """{"text":"Hi there","segments":[{"start":0.2,"end":1.4,"text":" Hi "},{"start":1.5,"end":2,"text":"there"}]}"""
        assertEquals(listOf(CustomSTTSegment("Hi", 0.2, 1.4), CustomSTTSegment("there", 1.5, 2.0)), CustomSTTRequests.segments(openAI, 3.0))
        val diarized = """{"segments":[{"start":0,"end":1,"text":"A1","speaker":"A"},{"start":1,"end":2,"text":"B1","speaker":"B"}]}"""
        assertEquals(listOf(0, 1), CustomSTTRequests.segments(diarized, 2.0).map { it.speaker })
        assertEquals(listOf(CustomSTTSegment("only text", 0.0, 3.0)), CustomSTTRequests.segments("""{"text":" only text "}""", 3.0))
        assertTrue(runCatching { CustomSTTRequests.segments("nope", 1.0) }.exceptionOrNull() == CustomSTTError.Undecodable)
    }

    @Test
    fun deepgramStreamsLinear16AndGroupsWordsBySpeaker() {
        val request = CustomSTTRequests.deepgramSocket(CustomSTTConfig(CustomSTTProvider.DeepgramLive, apiKey = "dg"))
        assertEquals("api.deepgram.com", request.url.host)
        assertEquals("Token dg", request.header("Authorization"))
        assertEquals("linear16", request.url.queryParameter("encoding"))
        assertEquals("nova-3", request.url.queryParameter("model"))
        assertEquals("multi", request.url.queryParameter("language"))
        val message = """
            {"type":"Results","is_final":true,"channel":{"alternatives":[{"transcript":"hi you there","words":[
            {"punctuated_word":"Hi","start":0.1,"end":0.3,"speaker":0},{"punctuated_word":"you","start":0.4,"end":0.5,"speaker":0},
            {"punctuated_word":"there.","start":0.6,"end":0.9,"speaker":1}]}]}}
        """.trimIndent()
        assertEquals(
            listOf(CustomSTTSegment("Hi you", 0.1, 0.5, 0), CustomSTTSegment("there.", 0.6, 0.9, 1)),
            CustomSTTRequests.deepgramSegments(message),
        )
        assertNull(CustomSTTRequests.deepgramSegments("""{"type":"Metadata"}"""))
        assertNull(CustomSTTRequests.deepgramSegments("""{"type":"Results","is_final":false,"channel":{"alternatives":[{"transcript":"x"}]}}"""))
    }

    @Test
    fun wavHeaderDescribes16kMonoPCM() {
        val wav = PCMWave.wav(ByteArray(320))
        assertEquals(44 + 320, wav.size)
        assertArrayEquals("RIFF".toByteArray(), wav.copyOfRange(0, 4))
        assertArrayEquals(byteArrayOf(0x80.toByte(), 0x3E, 0, 0), wav.copyOfRange(24, 28))
    }
}
