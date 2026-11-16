package com.friend.ios.ble

/** Metadata only. Observe firmware READ_BEGIN through DONE (including successful STOP).
 *  No notification bodies, ring IDs, paths or custody decisions are retained.
 *  Unknown/restored links remain unknown until a protocol boundary is observed.
 */
internal class RingReadDiagnostics {
    companion object {
        const val CHARACTERISTIC = "30295781-4301-eabd-2904-2849adfeae43"
    }

    private val pending = mutableMapOf<String, List<Byte>>()
    private val owners = mutableMapOf<String, Any>()
    private val beganAt = mutableMapOf<String, Long>()

    @Synchronized
    fun connected(address: String, owner: Any) {
        owners[address] = owner
        pending.remove(address)
        beganAt.remove(address)
    }

    // Legacy file packets can start with 0x05 too. Require a ring READ write.
    @Synchronized
    fun requested(address: String, owner: Any, characteristic: String, value: ByteArray) {
        if (owners[address] !== owner || !characteristic.equals(CHARACTERISTIC, ignoreCase = true)) return
        if (value.firstOrNull() != 0x11.toByte()) return
        if (value.size == 9 || value.size == 13) pending[address] = value.slice(1..8) else pending.remove(address)
    }

    @Synchronized
    fun rejected(address: String, owner: Any, characteristic: String, value: ByteArray) {
        if (owners[address] !== owner || !characteristic.equals(CHARACTERISTIC, ignoreCase = true)) return
        if (value.firstOrNull() == 0x11.toByte() && (value.size == 9 || value.size == 13) &&
            pending[address] == value.slice(1..8)) pending.remove(address)
    }

    @Synchronized
    fun received(address: String, owner: Any, characteristic: String, value: ByteArray, nowMs: Long) {
        if (owners[address] !== owner) return
        if (!characteristic.equals(CHARACTERISTIC, ignoreCase = true)) return
        if (value.size >= 13 && value[0] == 0x05.toByte() && pending[address] == value.slice(1..8)) {
            pending.remove(address)
            beganAt[address] = nowMs
        } else if (value.size >= 10 && value[0] == 0x04.toByte() &&
            (pending.containsKey(address) || beganAt.containsKey(address))) {
            pending.remove(address)
            beganAt.remove(address)
        }
    }

    /** Consume before teardown. Use elapsedRealtime, never the wall clock. */
    @Synchronized
    fun disconnected(address: String, nowMs: Long): Map<String, Any> {
        val began = beganAt.remove(address)
        pending.remove(address)
        if (owners.remove(address) == null) return emptyMap()
        return buildMap {
            put("ring_read_active", began != null)
            if (began != null) put("ring_read_age_ms", (nowMs - began).coerceAtLeast(0L))
        }
    }
}
