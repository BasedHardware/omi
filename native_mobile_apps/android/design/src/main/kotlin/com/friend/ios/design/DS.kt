package com.friend.ios.design

import androidx.compose.animation.core.FiniteAnimationSpec
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.runtime.Composable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextGeometricTransform
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.PI

/**
 * Port of omi-native `OmiDesign/DesignTokens.swift`: the single source of visual truth.
 * Same names, same values. Feature code uses `DS` only: no raw colors, sizes or durations.
 */
object DS {
    object Palette {
        /** Soft graphite at night, white by day. */
        val background: Color @Composable @ReadOnlyComposable get() = pick(0xFFFFFF, 0x212121)
        /** The few raised surfaces (a banner, a settings group, the composer). */
        val card: Color @Composable @ReadOnlyComposable get() = pick(0xF4F4F4, 0x2F2F2F)
        val conversationCard: Color @Composable @ReadOnlyComposable get() = card
        /** A surface on a surface (a pill on a card, a pressed row). */
        val cardRaised: Color @Composable @ReadOnlyComposable get() = pick(0xF4F4F4, 0x303030)
        /** A raised surface's edge: only visible by day. */
        val cardStroke: Color @Composable @ReadOnlyComposable get() = pick(0xE6E6E6, 0x2F2F2F)
        val tile: Color @Composable @ReadOnlyComposable get() = pick(0xF4F4F4, 0x2F2F2F)
        val fill: Color @Composable @ReadOnlyComposable get() = pick(0xECECEC, 0x3A3A3A)
        val hairline: Color @Composable @ReadOnlyComposable get() = pick(0xE6E6E6, 0x343434)

        val ink: Color @Composable @ReadOnlyComposable get() = pick(0x0D0D0D, 0xECECEC)
        val inkSecondary: Color @Composable @ReadOnlyComposable get() = pick(0x5D5D5D, 0xB4B4B4)
        val inkTertiary: Color @Composable @ReadOnlyComposable get() = pick(0x8F8F8F, 0x8E8E8E)
        val inkDisabled: Color @Composable @ReadOnlyComposable get() = pick(0xC4C4C4, 0x5A5A5A)

        val accent: Color @Composable @ReadOnlyComposable get() = ink
        val onAccent: Color @Composable @ReadOnlyComposable get() = pick(0xFFFFFF, 0x000000)
        /** Omi blue: what is live or active, and everything the agent does. */
        val agent: Color @Composable @ReadOnlyComposable get() = pick(0x2463EB, 0x3B82F6)
        /** Text and glyphs on Omi blue (white in both modes). */
        val onAgent: Color @Composable @ReadOnlyComposable get() = pick(0xFFFFFF, 0xFFFFFF)
        val agentSoft: Color @Composable @ReadOnlyComposable get() = agent.copy(alpha = 0.12f)
        val live: Color @Composable @ReadOnlyComposable get() = pick(0xE5484D, 0xFF5A5F)
        val success: Color @Composable @ReadOnlyComposable get() = pick(0x2F9E5B, 0x3DD68C)
        val warning: Color @Composable @ReadOnlyComposable get() = pick(0xD9822B, 0xF5A04A)
        val amber: Color @Composable @ReadOnlyComposable get() = pick(0xE8833A, 0xF59A4A)

        /**
         * Chat bubbles, as in Messages but softer: yours in a light tint of Omi blue with ink text
         * (a deep blue at night), Omi's on the card surface.
         */
        val bubbleUser: Color @Composable @ReadOnlyComposable get() = pick(0xDCE7FC, 0x233C66)
        val onBubbleUser: Color @Composable @ReadOnlyComposable get() = ink
        val bubbleAssistant: Color @Composable @ReadOnlyComposable get() = card

        @Composable
        @ReadOnlyComposable
        private fun pick(light: Long, dark: Long): Color = hex(if (LocalOmiDark.current) dark else light)
    }

    object Stroke {
        val hairline: Dp = 0.75.dp
        val regular: Dp = 1.dp
        val hero: Dp = 1.5.dp
    }

    object Gradient {
        /** A hero illustration's outline: hairline gray that warms into amber on one side. */
        val heroStroke: Brush
            @Composable @ReadOnlyComposable get() = Brush.horizontalGradient(
                0f to Palette.inkTertiary.copy(alpha = 0.35f),
                0.45f to Palette.inkTertiary.copy(alpha = 0.35f),
                1f to Palette.amber,
            )
        val heroGlowColors: List<Color>
            @Composable @ReadOnlyComposable get() = listOf(Palette.amber.copy(alpha = 0.35f), Palette.amber.copy(alpha = 0f))
        val heroGlowEndRadius: Dp = 160.dp
    }

    object Glow {
        val live: Color @Composable @ReadOnlyComposable get() = Palette.agent.copy(alpha = 0.45f)
        val liveRadius: Dp = 10.dp
    }

    object Spacing {
        val xxs: Dp = 2.dp
        val xs: Dp = 4.dp
        val sm: Dp = 8.dp
        val md: Dp = 12.dp
        val lg: Dp = 16.dp
        /** The screen's horizontal gutter. */
        val gutter: Dp = 20.dp
        val xl: Dp = 24.dp
        val section: Dp = 32.dp
    }

    object Radius {
        val sm: Dp = 10.dp
        val tile: Dp = 10.dp
        val md: Dp = 16.dp
        val card: Dp = 20.dp
        /** Chat bubbles and the cards in the thread. */
        val bubble: Dp = 18.dp
        /** A bubble's corner on the sender's side where it joins the next one of its group. */
        val bubbleJoined: Dp = 7.dp
        /** The sender-side bottom corner of a group's last bubble (Messages' tail, quieter). */
        val bubbleTail: Dp = 4.dp
        val hero: Dp = 28.dp
    }

    /**
     * iOS text styles at the default ("Large") content size: size / line height / tracking from the
     * Apple HIG tables, same weights as `DS.Typography`. `sp` follows the system font scale the way
     * the iOS styles follow Dynamic Type.
     */
    object Typography {
        val display: TextStyle = TextStyles.largeTitle.bold()
        val largeTitle: TextStyle = TextStyles.title1.bold()
        val title: TextStyle = TextStyles.title2.bold()
        val switcher: TextStyle = TextStyles.title1.bold()
        val sectionTitle: TextStyle = TextStyles.title3.semibold()
        val sectionLabel: TextStyle = TextStyles.subheadline.medium()
        val cardTitle: TextStyle = TextStyles.body
        val body: TextStyle = TextStyles.body
        val callout: TextStyle = TextStyles.subheadline
        val bubble: TextStyle = TextStyles.callout
        val caption: TextStyle = TextStyles.footnote
        val micro: TextStyle = TextStyles.caption2.semibold()
        val button: TextStyle = TextStyles.body.semibold()
        val label: TextStyle = TextStyles.footnote.medium()
        val timer: TextStyle = TextStyles.title3.semibold().copy(fontFeatureSettings = "tnum")
    }

    object Tracking {
        const val label: Float = 0.3f
    }

    object Size {
        val emojiBadge: Dp = 40.dp
        val tile: Dp = 38.dp
        val headerButton: Dp = 40.dp
        /** Omi's picture beside the last bubble of its group in the chat. */
        val chatAvatar: Dp = 26.dp
        /** The chat composer's field, "+" and mic. */
        val composer: Dp = 44.dp
        val searchField: Dp = 44.dp
        val omiBarHeight: Dp = 60.dp
        val primaryButtonHeight: Dp = 52.dp
    }

    object Motion {
        /** `.smooth(duration: 0.32, extraBounce: 0)`: critically damped spring, response 0.32 s. */
        fun <T> standard(): FiniteAnimationSpec<T> = spring(dampingRatio = 1f, stiffness = stiffness(0.32f))
        /** `.snappy(duration: 0.28)`: a little bounce (damping 0.85), response 0.28 s. */
        fun <T> snappy(): FiniteAnimationSpec<T> = spring(dampingRatio = 0.85f, stiffness = stiffness(0.28f))
        /** `.easeInOut(duration: 0.22)`. */
        fun <T> gentle(): FiniteAnimationSpec<T> = tween(220, easing = CubicBezierEasing(0.42f, 0f, 0.58f, 1f))

        /** SwiftUI spring response (period in seconds) to a Compose stiffness for unit mass. */
        fun stiffness(response: Float): Float = (2 * PI.toFloat() / response).let { it * it }
    }
}

/** sRGB from a packed 24-bit value, like `Color(hex:)`. */
fun hex(value: Long, alpha: Float = 1f): Color = Color(0xFF000000 or value).copy(alpha = alpha)

/** SF Pro Display, the face the Omi Flutter app already ships (`app/assets/fonts`). */
val SFPro = FontFamily(
    Font(R.font.sf_pro_display_regular, FontWeight.Normal),
    Font(R.font.sf_pro_display_medium, FontWeight.Medium),
    // No upright semibold ships with Omi; Flutter resolves w600 to bold the same way.
    Font(R.font.sf_pro_display_bold, FontWeight.SemiBold),
    Font(R.font.sf_pro_display_bold, FontWeight.Bold),
)

/** The iOS text styles (HIG, Large content size). */
object TextStyles {
    val largeTitle = style(34, 41, 0.40)
    val title1 = style(28, 34, 0.38)
    val title2 = style(22, 28, -0.26)
    val title3 = style(20, 25, -0.45)
    val headline = style(17, 22, -0.43, FontWeight.SemiBold)
    val body = style(17, 22, -0.43)
    val callout = style(16, 21, -0.31)
    val subheadline = style(15, 20, -0.23)
    val footnote = style(13, 18, -0.08)
    val caption1 = style(12, 16, 0.0)
    val caption2 = style(11, 13, 0.06)

    /** `.font(.system(size:weight:))` for the literal sizes feature code uses. */
    fun system(size: Int, weight: FontWeight = FontWeight.Normal): TextStyle =
        style(size, (size * 1.2).toInt(), trackingFor(size), weight)

    private fun style(size: Int, lineHeight: Int, tracking: Double, weight: FontWeight = FontWeight.Normal) = TextStyle(
        fontFamily = SFPro,
        fontWeight = weight,
        fontSize = size.sp,
        lineHeight = lineHeight.sp,
        letterSpacing = (tracking + textCutTracking(size)).sp,
        textGeometricTransform = if (size < TEXT_CUT_BELOW) TextGeometricTransform(scaleX = TEXT_CUT_SCALE_X) else null,
    )

    /**
     * iOS switches to SF Pro Text below 20 pt: wider glyphs and looser spacing than the Display
     * cut Omi ships. Measured on the Memories screen (iPhone 17 Pro vs Pixel, same strings), a
     * 17 pt line was 12.7 % wider on iOS; a slightly wider glyph plus extra tracking closes it.
     * Display sizes (20 pt and up) already match to the point.
     */
    private const val TEXT_CUT_BELOW = 20
    private const val TEXT_CUT_SCALE_X = 1.065f

    private fun textCutTracking(size: Int): Double = if (size < TEXT_CUT_BELOW) 0.035 * size else 0.0

    private fun trackingFor(size: Int): Double = when {
        size <= 11 -> 0.06
        size <= 12 -> 0.0
        size <= 13 -> -0.08
        size <= 15 -> -0.23
        size <= 16 -> -0.31
        size <= 17 -> -0.43
        size <= 20 -> -0.45
        size <= 22 -> -0.26
        size <= 28 -> 0.38
        else -> 0.40
    }
}

fun TextStyle.medium(): TextStyle = copy(fontWeight = FontWeight.Medium)
fun TextStyle.semibold(): TextStyle = copy(fontWeight = FontWeight.SemiBold)
fun TextStyle.bold(): TextStyle = copy(fontWeight = FontWeight.Bold)
