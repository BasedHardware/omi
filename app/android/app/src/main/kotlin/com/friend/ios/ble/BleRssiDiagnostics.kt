package com.friend.ios.ble

internal object BleRssiDiagnostics {
    fun trend(samples: List<Pair<Long, Int>>, nowMs: Long): String {
        val recent = samples.filter { it.first >= nowMs - 15_000L }
        if (recent.isEmpty()) return "gap"
        if (recent.size < 2) return "unknown"
        val third = (recent.size / 3).coerceAtLeast(1)
        val oldest = recent.take(third).sumOf { it.second } / third
        val newest = recent.takeLast(third).sumOf { it.second } / third
        return if (oldest - newest >= 10) "fading" else "sudden"
    }

    fun ageMs(samples: List<Pair<Long, Int>>, nowMs: Long): Long =
        samples.lastOrNull()?.let { (nowMs - it.first).coerceAtLeast(0L) } ?: -1L
}
