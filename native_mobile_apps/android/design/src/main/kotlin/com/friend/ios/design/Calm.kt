package com.friend.ios.design

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

/** `OmiChip`: a small pill with a hairline edge. [tint] colors an active filter. */
@Composable
fun OmiChip(text: String, modifier: Modifier = Modifier, systemImage: String? = null, tint: Color? = null) {
    val ink = tint ?: DS.Palette.inkSecondary
    HStack(
        modifier
            .background(DS.Palette.card, CircleShape)
            .border(DS.Stroke.regular, tint?.copy(alpha = 0.4f) ?: DS.Palette.cardStroke, CircleShape)
            .padding(horizontal = DS.Spacing.md, vertical = DS.Spacing.xs + 2.dp),
        spacing = DS.Spacing.xs + 2.dp,
    ) {
        if (systemImage != null) SFImage(systemImage, size = 11.sp, tint = ink)
        Text(text, style = DS.Typography.label.copy(letterSpacing = DS.Tracking.label.sp), color = ink, maxLines = 1)
    }
}

/** `OmiHairline`: a hairline between quiet rows, starting at [leading]. */
@Composable
fun OmiHairline(modifier: Modifier = Modifier, leading: Dp = 0.dp) {
    Box(modifier.fillMaxWidth().padding(start = leading).height(DS.Stroke.hairline).background(DS.Palette.hairline))
}

/** `OmiStatusLine`: a small blue spinner and a short sentence ("Looking for your Omi"). */
@Composable
fun OmiStatusLine(text: String, modifier: Modifier = Modifier, isWorking: Boolean = true) {
    HStack(modifier, spacing = DS.Spacing.sm + 2.dp) {
        if (isWorking) OmiProgress(Modifier.size(16.dp), tint = DS.Palette.agent)
        Text(text, style = DS.Typography.button, color = DS.Palette.ink)
    }
}

/** `ProgressView()` (small): the iOS activity indicator stand-in. */
@Composable
fun OmiProgress(modifier: Modifier = Modifier.size(20.dp), tint: Color = DS.Palette.inkSecondary) {
    CircularProgressIndicator(modifier, color = tint, strokeWidth = 2.dp, trackColor = Color.Transparent)
}

/**
 * `OmiLivePill`: the capsule shown while Omi records. [sinceMillis] null hides the timer,
 * [symbol] null shows the pendant.
 */
@Composable
fun OmiLivePill(
    sinceMillis: Long?,
    modifier: Modifier = Modifier,
    title: String? = null,
    symbol: String? = null,
    trailing: @Composable () -> Unit = {},
) {
    HStack(
        modifier
            .heightIn(min = 48.dp)
            .shadow(DS.Glow.liveRadius, CircleShape, ambientColor = DS.Glow.live, spotColor = DS.Glow.live)
            .background(DS.Palette.card, CircleShape)
            .border(DS.Stroke.regular, DS.Palette.agent.copy(alpha = 0.55f), CircleShape)
            .padding(horizontal = DS.Spacing.sm),
        spacing = DS.Spacing.md,
    ) {
        if (symbol != null) {
            Box(Modifier.size(30.dp).background(DS.Palette.agentSoft, CircleShape), contentAlignment = Alignment.Center) {
                SFImage(symbol, size = 13.sp, weight = FontWeight.SemiBold, tint = DS.Palette.agent)
            }
        } else {
            OmiPendantThumbnail(30.dp)
        }
        if (title != null) {
            Text(
                title,
                style = DS.Typography.callout,
                color = DS.Palette.inkSecondary,
                maxLines = 1,
                // `.truncationMode(.head)`: the newest words stay visible.
                overflow = TextOverflow.StartEllipsis,
                // Takes the free width (iOS: the Spacer only keeps its minimum beside a title).
                modifier = Modifier.weight(1f),
            )
        } else {
            Spacer(Modifier.weight(1f).width(DS.Spacing.sm))
        }
        if (sinceMillis != null) {
            var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
            LaunchedEffect(sinceMillis) {
                while (true) {
                    now = System.currentTimeMillis()
                    delay(1000 - (now - sinceMillis) % 1000)
                }
            }
            Text(livePillElapsed((now - sinceMillis) / 1000.0), style = DS.Typography.timer, color = DS.Palette.ink)
        }
        trailing()
    }
}

/** "4:07", "1:02:33". */
fun livePillElapsed(seconds: Double): String {
    val total = maxOf(0, seconds.toInt())
    val hours = total / 3600
    val minutes = total / 60 % 60
    val rest = total % 60
    return if (hours > 0) "%d:%02d:%02d".format(hours, minutes, rest) else "%d:%02d".format(minutes, rest)
}

/** `OmiPendantThumbnail`: the Omi pendant photo with a soft blue glow. */
@Composable
fun OmiPendantThumbnail(size: Dp = 30.dp, modifier: Modifier = Modifier) {
    Image(
        painterResource(R.drawable.omi_device),
        contentDescription = null,
        contentScale = ContentScale.Fit,
        modifier = modifier.size(size).shadow(size / 5, CircleShape, clip = false, ambientColor = DS.Glow.live, spotColor = DS.Glow.live),
    )
}

/**
 * `OmiPendantIllustration`: the pendant drawn as a hero, a thin outline warming into amber with a
 * soft glow, the inner disc as a hairline, the loop on top and the blue light in the middle.
 */
@Composable
fun OmiPendantIllustration(size: Dp = 220.dp, modifier: Modifier = Modifier, pointsAtLight: Boolean = false, isGlowing: Boolean = true) {
    val glow = DS.Gradient.heroGlowColors
    val stroke = DS.Gradient.heroStroke
    val card = DS.Palette.card
    val inner = DS.Palette.inkTertiary.copy(alpha = 0.25f)
    val agent = DS.Palette.agent
    val liveGlow = DS.Glow.live
    Box(modifier.size(size * 1.2f), contentAlignment = Alignment.Center) {
        if (isGlowing) {
            Box(
                Modifier.size(size * 1.2f).offset(x = size * 0.18f).blur(size * 0.08f).drawBehind {
                    drawCircle(Brush.radialGradient(glow, center = Offset(this.size.width, this.size.height / 2), radius = 160.dp.toPx()))
                },
            )
        }
        Box(Modifier.size(size).background(card, CircleShape).border(DS.Stroke.hero, stroke, CircleShape))
        Box(Modifier.offset(y = -size / 2 - size * 0.02f).size(size * 0.16f, size * 0.09f).border(DS.Stroke.hero, stroke, CircleShape))
        Box(Modifier.size(size * 0.72f).border(DS.Stroke.hairline, inner, CircleShape))
        Box(
            Modifier.size(size * 0.035f)
                .shadow(size * 0.1f, CircleShape, ambientColor = liveGlow, spotColor = liveGlow)
                .shadow(size * 0.04f, CircleShape, ambientColor = agent, spotColor = agent)
                .background(agent, CircleShape),
        )
        if (pointsAtLight) {
            SFImage("arrow.left", Modifier.offset(x = size * 0.16f), size = (size.value * 0.11f).sp, weight = FontWeight.SemiBold, tint = agent)
        }
    }
}
