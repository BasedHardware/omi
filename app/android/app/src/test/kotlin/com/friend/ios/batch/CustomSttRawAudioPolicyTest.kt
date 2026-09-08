package com.friend.ios.batch

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CustomSttRawAudioPolicyTest {
    @Test
    fun defaultOmiConfigAllowsRawAudio() {
        assertTrue(CustomSttRawAudioPolicy.allowsForwarding(""))
        assertTrue(CustomSttRawAudioPolicy.allowsForwarding("""{"provider":"omi","send_raw_audio_to_omi":false}"""))
    }

    @Test
    fun customSttOptOutBlocksRawAudio() {
        assertFalse(
            CustomSttRawAudioPolicy.allowsForwarding(
                """{"provider":"onDeviceWhisper","send_raw_audio_to_omi":false}"""
            )
        )
    }

    @Test
    fun customSttOptInAllowsRawAudio() {
        assertTrue(
            CustomSttRawAudioPolicy.allowsForwarding(
                """{"provider":"onDeviceWhisper","send_raw_audio_to_omi":true}"""
            )
        )
    }

    @Test
    fun malformedCustomSttConfigFailsClosed() {
        assertFalse(CustomSttRawAudioPolicy.allowsForwarding("{not-json"))
    }
}
