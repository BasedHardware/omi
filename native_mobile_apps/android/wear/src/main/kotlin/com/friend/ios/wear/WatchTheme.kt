package com.friend.ios.wear

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * The few tokens `RecorderView.swift` uses. The iOS watch app draws with watchOS system colors on
 * black, not with `DS` (which is light/dark and phone-sized), so these are the watchOS dark values.
 * Kept here instead of depending on :design (Material 3, 49 locales of phone strings).
 */
object WatchPalette {
    val background = Color.Black
    val primary = Color.White
    /** `.foregroundStyle(.secondary)` on watchOS. */
    val secondary = Color(0xFFEBEBF5).copy(alpha = 0.6f)
    /** `Color.red` on watchOS (dark). */
    val red = Color(0xFFFF453A)
    /** `Color.orange` on watchOS (dark). */
    val orange = Color(0xFFFF9F0A)
}

/** SF Pro, as in :design (`DS.SFPro`); the system font of watchOS. */
val SFPro = FontFamily(
    Font(R.font.sf_pro_display_regular, FontWeight.Normal),
    Font(R.font.sf_pro_display_bold, FontWeight.SemiBold),
    Font(R.font.sf_pro_display_bold, FontWeight.Bold),
)

/** watchOS text styles at the default size. */
object WatchType {
    val footnote = TextStyle(fontFamily = SFPro, fontSize = 13.sp, lineHeight = 16.sp)
    val headline = TextStyle(fontFamily = SFPro, fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold)
    /** `.system(size: 24, weight: .semibold, design: .rounded).monospacedDigit()`. */
    val timer = TextStyle(fontFamily = SFPro, fontSize = 24.sp, fontWeight = FontWeight.SemiBold, fontFeatureSettings = "tnum")
}
