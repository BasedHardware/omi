package com.friend.ios.ble

/** Counts the 16-bit little-endian packet index without retaining audio bytes. */
internal class BleAudioPacketCounter {
    var received: Long = 0
        private set
    var expected: Long = 0
        private set
    private var previous: Int? = null

    fun record(packet: ByteArray): Boolean {
        if (packet.size < 3) return false
        val index = (packet[0].toInt() and 0xff) or ((packet[1].toInt() and 0xff) shl 8)
        val delta = previous?.let { (index - it + 65536) % 65536 } ?: 1
        if (delta == 0) return false
        received++
        expected += if (delta > 4096) 1 else delta // Treat a stream reset as a new baseline.
        previous = index
        return true
    }
}
