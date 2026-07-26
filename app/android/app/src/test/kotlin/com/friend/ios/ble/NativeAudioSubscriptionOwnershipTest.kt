package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NativeAudioSubscriptionOwnershipTest {
    private val legacyAudio = NativeAudioSubscriptionTarget(
        serviceUuid = "service",
        characteristicUuid = "legacy-audio",
    )

    @Test
    fun omittedConfigReleasesLegacySubscriptionOwnedByNativeOnSameGatt() {
        val ownership = NativeAudioSubscriptionOwnership()

        assertEquals(
            legacyAudio,
            ownership.reconcile("aa:bb", sessionToken = 7, desired = legacyAudio).subscribe,
        )

        val handoff = ownership.reconcile("AA:BB", sessionToken = 7, desired = null)

        assertEquals(legacyAudio, handoff.unsubscribe)
        assertNull(handoff.subscribe)
        assertEquals(
            NativeAudioSubscriptionTransition(),
            ownership.reconcile("aa:bb", sessionToken = 7, desired = null),
        )
    }

    @Test
    fun replacementGattDoesNotInheritOrDisableRetiredSessionState() {
        val ownership = NativeAudioSubscriptionOwnership()
        ownership.reconcile("AA:BB", sessionToken = 7, desired = legacyAudio)

        val replacement = ownership.reconcile(
            "AA:BB",
            sessionToken = 8,
            desired = legacyAudio,
        )

        assertNull(replacement.unsubscribe)
        assertEquals(legacyAudio, replacement.subscribe)
    }
}
