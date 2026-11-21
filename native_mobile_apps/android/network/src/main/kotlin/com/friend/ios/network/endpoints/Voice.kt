package com.friend.ios.network.endpoints

import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method

/** Port of `APIClient+Voice.swift`: the voice sample from onboarding (and Settings). */
interface VoiceAPI {
    /** `POST v3/upload-audio`: the user's voice sample (16 kHz mono WAV) becomes the speech profile. */
    suspend fun uploadSpeechProfile(wav: ByteArray)
}

internal class VoiceEndpoints(private val http: HttpCore) : VoiceAPI {
    override suspend fun uploadSpeechProfile(wav: ByteArray) {
        http.data(Method.POST, "v3/upload-audio", body = Body.File("file", "voice.wav", "audio/wav", wav))
    }
}
