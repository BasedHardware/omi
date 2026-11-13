package com.friend.ios.service.stores

/**
 * Port of `LowBatteryAlert.swift`: one low-battery notification per discharge. It fires when the
 * Omi drops below [low] and re-arms only after a charge above [rearm], so a level wobbling around
 * 15 % notifies once.
 */
class LowBatteryAlert(alerted: Boolean = false) {
    /** Already notified for this discharge. */
    var alerted: Boolean = alerted
        private set

    /** Feeds a reading; `true` when this reading should notify. */
    fun update(level: Int): Boolean {
        if (level > rearm) {
            alerted = false
            return false
        }
        if (level >= low || alerted) return false
        alerted = true
        return true
    }

    companion object {
        const val low = 15
        const val rearm = 30

        /** Below this the battery shows in orange. */
        fun isLow(level: Int): Boolean = level < low
    }
}
