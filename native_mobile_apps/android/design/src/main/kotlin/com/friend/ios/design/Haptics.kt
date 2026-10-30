package com.friend.ios.design

import android.os.SystemClock
import android.view.HapticFeedbackConstants
import android.view.View
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalView

/** Port of `DSInteractionGate`: one interaction should not double-fire haptics. */
object DSInteractionGate {
    private var suppressTapUntil = 0L

    val allowsTap: Boolean get() = SystemClock.uptimeMillis() >= suppressTapUntil

    fun suppressTaps(durationMillis: Long = 360) {
        suppressTapUntil = maxOf(suppressTapUntil, SystemClock.uptimeMillis() + durationMillis)
    }
}

/** Port of `DSHaptics`, routed through the view so feature code doesn't reach the Vibrator. */
class DSHaptics(private val view: View) {
    enum class Style { Light, Medium, Heavy }

    fun tap(style: Style = Style.Light): Boolean {
        if (!DSInteractionGate.allowsTap) return false
        view.performHapticFeedback(
            when (style) {
                Style.Light -> HapticFeedbackConstants.CLOCK_TICK
                Style.Medium -> HapticFeedbackConstants.VIRTUAL_KEY
                Style.Heavy -> HapticFeedbackConstants.LONG_PRESS
            },
        )
        return true
    }

    fun selection() {
        if (!DSInteractionGate.allowsTap) return
        view.performHapticFeedback(HapticFeedbackConstants.SEGMENT_FREQUENT_TICK)
    }

    /** A barely-there tick, for things that arrive on their own. */
    fun soft() {
        view.performHapticFeedback(HapticFeedbackConstants.SEGMENT_TICK)
    }

    /** Something finished well. */
    fun success() {
        view.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
    }
}

@Composable
fun rememberHaptics(): DSHaptics {
    val view = LocalView.current
    return remember(view) { DSHaptics(view) }
}
