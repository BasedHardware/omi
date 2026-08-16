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
    fun typedPrivacyPoliciesControlRawAudioForwarding() {
        assertTrue(
            CustomSttRawAudioPolicy.allowsForwarding(
                """{"provider":"onDeviceWhisper","privacy_policy":"full"}"""
            )
        )
        assertFalse(
            CustomSttRawAudioPolicy.allowsForwarding(
                """{"provider":"onDeviceWhisper","privacy_policy":"transcriptOnly"}"""
            )
        )
        assertFalse(
            CustomSttRawAudioPolicy.allowsForwarding(
                """{"provider":"onDeviceWhisper","privacy_policy":"localOnly"}"""
            )
        )
    }

    @Test
    fun typedPrivacyPolicyTakesPrecedenceOverLegacyBoolean() {
        assertTrue(
            CustomSttRawAudioPolicy.allowsForwarding(
                """{"provider":"onDeviceWhisper","privacy_policy":"full","send_raw_audio_to_omi":false}"""
            )
        )
        assertFalse(
            CustomSttRawAudioPolicy.allowsForwarding(
                """{"provider":"onDeviceWhisper","privacy_policy":"transcriptOnly","send_raw_audio_to_omi":true}"""
            )
        )
        assertFalse(
            CustomSttRawAudioPolicy.allowsForwarding(
                """{"provider":"onDeviceWhisper","privacy_policy":"localOnly","send_raw_audio_to_omi":true}"""
            )
        )
    }

    @Test
    fun unknownTypedPrivacyPolicyFailsClosedRegardlessOfLegacyBoolean() {
        assertFalse(
            CustomSttRawAudioPolicy.allowsForwarding(
                """{"provider":"onDeviceWhisper","privacy_policy":"unknown","send_raw_audio_to_omi":true}"""
            )
        )
        assertFalse(
            CustomSttRawAudioPolicy.allowsForwarding(
                """{"provider":"onDeviceWhisper","privacy_policy":42,"send_raw_audio_to_omi":true}"""
            )
        )
    }

    @Test
    fun malformedCustomSttConfigFailsClosed() {
        assertFalse(CustomSttRawAudioPolicy.allowsForwarding("{not-json"))
    }

    @Test
    fun missingOrUnknownProviderFailsClosed() {
        assertFalse(CustomSttRawAudioPolicy.allowsForwarding("{}"))
        assertFalse(CustomSttRawAudioPolicy.allowsForwarding("""{"provider":"bogus"}"""))
    }
}
