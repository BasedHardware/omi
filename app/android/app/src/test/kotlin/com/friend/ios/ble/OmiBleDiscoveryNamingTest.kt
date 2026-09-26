package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OmiBleDiscoveryNamingTest {

    private val notePin = byteArrayOf(0x04, 0x56, 0xCF.toByte(), 0x00)

    @Test
    fun `note pin payload is recognised`() {
        assertTrue(isNotePinAdvertisement(notePin))
    }

    @Test
    fun `missing short or different payloads are rejected`() {
        assertFalse(isNotePinAdvertisement(null))
        assertFalse(isNotePinAdvertisement(byteArrayOf(0x04, 0x56, 0xCF.toByte())))
        assertFalse(isNotePinAdvertisement(byteArrayOf(0x04, 0x56, 0xCF.toByte(), 0x01)))
        assertFalse(isNotePinAdvertisement(byteArrayOf(0x00, 0x00, 0x00, 0x00)))
    }

    @Test
    fun `advertised name wins and is trimmed`() {
        assertEquals("NotePin S", discoveredPeripheralName("  NotePin S  ", "cached", notePin))
        assertEquals("NotePin S", discoveredPeripheralName("NotePin S", null, null))
    }

    @Test
    fun `blank advertised name falls back to cached then note pin`() {
        assertEquals("cached", discoveredPeripheralName("   ", "cached", notePin))
        assertEquals("cached", discoveredPeripheralName(null, "cached", null))
        assertEquals("NotePin", discoveredPeripheralName(null, null, notePin))
        assertEquals("NotePin", discoveredPeripheralName("", "  ", notePin))
    }

    @Test
    fun `unnamed non-note-pin peripheral stays empty`() {
        assertEquals("", discoveredPeripheralName(null, null, null))
        assertEquals("", discoveredPeripheralName(null, null, byteArrayOf(0x01, 0x02, 0x03, 0x04)))
    }
}
