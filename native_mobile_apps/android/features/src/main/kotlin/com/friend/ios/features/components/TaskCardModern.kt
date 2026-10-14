package com.friend.ios.features.components

import android.provider.Settings
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.input.pointer.util.VelocityTracker
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.AvatarContent
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.EntityAvatar
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuSection
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.medium
import com.friend.ios.design.pressable
import com.friend.ios.design.semibold
import kotlinx.coroutines.launch
import kotlin.math.abs

/**
 * The Home task card, variant C (docs/HOME_TASK_CARD.md): one compact row. The picture says who
 * or what it is about (a brand, a person, the conversation's emoji); one meta line says why now
 * and where it came from; the magic button at the end is Omi's answer (`sparkles`, Omi starts at
 * once) or, where Omi cannot help, the checkmark that marks it done.
 *
 * While Omi works on it the card stays and changes in place: the button becomes a spinning ring,
 * the meta line reads "Omi is on it" with a pulsing dot. A swipe to the right puts it off until
 * tomorrow ([onSwipeLater]); only rightward drags are claimed, so a left drag still pages to Chat
 * and vertical drags scroll.
 */
@Composable
fun TaskCardModern(
    avatar: AvatarContent,
    avatarFallback: AvatarContent?,
    title: String,
    status: DecisionCard.Kicker,
    source: String?,
    canTakeOver: Boolean,
    isRunning: Boolean,
    onMagic: () -> Unit,
    onTap: () -> Unit,
    menu: () -> List<MenuSection>,
    modifier: Modifier = Modifier,
    onSwipeLater: (() -> Unit)? = null,
) {
    SwipeToLater(enabled = onSwipeLater != null && !isRunning, onCommit = { onSwipeLater?.invoke() }, modifier = modifier) {
        ContextMenuBox(sections = menu, onTap = onTap) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(DS.Palette.card, ContinuousRoundedShape(22.dp))
                    .padding(14.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                EntityAvatar(avatar, size = 40.dp, fallback = avatarFallback)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(title, style = TextStyles.body.medium(), color = DS.Palette.ink, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    if (isRunning) {
                        Meta(DecisionCard.Kicker("sparkles", L("nativeOmiOnIt"), DS.Palette.agent), source = null, pulses = true)
                    } else {
                        Meta(status, source)
                    }
                }
                when {
                    isRunning -> RunningButton(onClick = onTap)
                    else -> MagicButton(if (canTakeOver) "sparkles" else "checkmark", agent = canTakeOver, onClick = onMagic)
                }
            }
        }
    }
}

/** 6 pt status dot, the status in its color, then " · " and where it came from. */
@Composable
private fun Meta(status: DecisionCard.Kicker, source: String?, pulses: Boolean = false) {
    val alpha = if (pulses) {
        val transition = rememberInfiniteTransition(label = "pulse")
        val value by transition.animateFloat(1f, 0.3f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "dot")
        value
    } else {
        1f
    }
    HStack(spacing = 5.dp) {
        Box(Modifier.size(6.dp).alpha(alpha).background(status.color, CircleShape))
        Text(status.text, style = TextStyles.footnote.semibold(), color = status.color, maxLines = 1)
        if (!source.isNullOrEmpty()) {
            Text("·", style = TextStyles.footnote, color = DS.Palette.inkTertiary)
            Text(source, style = TextStyles.footnote, color = DS.Palette.inkSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
        }
    }
}

/** The 36 pt round answer: `sparkles` on agent blue when Omi can take over, else `checkmark`. */
@Composable
private fun MagicButton(symbol: String, agent: Boolean, onClick: () -> Unit) {
    val label = if (agent) L("nativeOmiTakesOver") else L("nativeMarkDone")
    Box(
        Modifier
            .size(36.dp)
            .pressable(onClick = onClick)
            .background(if (agent) DS.Palette.agentSoft else DS.Palette.fill, CircleShape)
            .semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        SFImage(symbol, size = 15.sp, weight = FontWeight.SemiBold, tint = if (agent) DS.Palette.agent else DS.Palette.ink)
    }
}

/** While Omi works: a small spinning ring in agent blue; tapping it opens the run. */
@Composable
private fun RunningButton(onClick: () -> Unit) {
    val label = L("nativeOmiOnIt")
    val transition = rememberInfiniteTransition(label = "spin")
    val angle by transition.animateFloat(0f, 360f, infiniteRepeatable(tween(900, easing = LinearEasing)), label = "angle")
    val agent = DS.Palette.agent
    Box(
        Modifier
            .size(36.dp)
            .pressable(onClick = onClick)
            .background(DS.Palette.agentSoft, CircleShape)
            .semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.size(16.dp).graphicsLayer { rotationZ = angle }) {
            val stroke = 2.dp.toPx()
            drawArc(
                agent, startAngle = 0f, sweepAngle = 270f, useCenter = false,
                topLeft = Offset(stroke / 2, stroke / 2),
                size = androidx.compose.ui.geometry.Size(size.width - stroke, size.height - stroke),
                style = Stroke(stroke, cap = StrokeCap.Round),
            )
        }
    }
}

/** Whether the system asks for less motion ("Remove animations"). */
@Composable
internal fun rememberReduceMotion(): Boolean {
    val context = LocalContext.current
    return remember(context) { Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f }
}

/**
 * Right swipe = Later: the card follows the finger to the right only; past ~35 % of its width
 * (or a fast fling) it slides out and [onCommit] runs, below that it springs back. Reduce Motion:
 * no slide, the card fades instead. A drag that starts leftward or vertically is never claimed.
 */
@Composable
private fun SwipeToLater(enabled: Boolean, onCommit: () -> Unit, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val reduceMotion = rememberReduceMotion()
    val scope = rememberCoroutineScope()
    val offset = remember { Animatable(0f) }
    val fade = remember { Animatable(1f) }
    val flingVelocity = with(LocalDensity.current) { 900.dp.toPx() }
    BoxWithConstraints(modifier.fillMaxWidth()) {
        val width = constraints.maxWidth.toFloat()
        fun progress(value: Float) = (value / width).coerceIn(0f, 1f)
        fun release(velocity: Float) {
            val commit = offset.value > width * 0.35f || (velocity > flingVelocity && offset.value > 0f)
            scope.launch {
                if (commit) {
                    if (reduceMotion) {
                        fade.animateTo(0f, DS.Motion.gentle())
                    } else {
                        launch { fade.animateTo(0f, DS.Motion.standard()) }
                        offset.animateTo(width, DS.Motion.standard())
                    }
                    onCommit()
                } else {
                    launch { fade.animateTo(1f, DS.Motion.snappy()) }
                    offset.animateTo(0f, DS.Motion.snappy())
                }
            }
        }
        Box(
            Modifier
                .graphicsLayer {
                    translationX = if (reduceMotion) 0f else offset.value
                    alpha = if (reduceMotion) fade.value * (1f - progress(offset.value) * 0.6f) else fade.value * (1f - progress(offset.value) * 0.4f)
                }
                .then(
                    if (!enabled) Modifier else Modifier.pointerInput(Unit) {
                        awaitEachGesture {
                            val down = awaitFirstDown(requireUnconsumed = false)
                            val tracker = VelocityTracker()
                            tracker.addPosition(down.uptimeMillis, down.position)
                            var total = Offset.Zero
                            var dragging = false
                            while (true) {
                                val event = awaitPointerEvent()
                                val change = event.changes.firstOrNull { it.id == down.id } ?: break
                                if (!change.pressed) {
                                    if (dragging) {
                                        change.consume()
                                        release(tracker.calculateVelocity().x)
                                    }
                                    return@awaitEachGesture
                                }
                                tracker.addPosition(change.uptimeMillis, change.position)
                                val delta = change.positionChange()
                                if (!dragging) {
                                    if (change.isConsumed) break
                                    total += delta
                                    val slop = viewConfiguration.touchSlop
                                    if (abs(total.x) > slop || abs(total.y) > slop) {
                                        // Only a rightward, mostly horizontal drag is ours; the rest
                                        // belongs to the pager (left) and the list (vertical).
                                        if (total.x > 0 && abs(total.x) > abs(total.y) * 1.2f) {
                                            dragging = true
                                            change.consume()
                                            val start = total.x - slop
                                            scope.launch { offset.snapTo(start.coerceAtLeast(0f)) }
                                        } else {
                                            break
                                        }
                                    }
                                } else {
                                    change.consume()
                                    scope.launch { offset.snapTo((offset.value + delta.x).coerceAtLeast(0f)) }
                                }
                            }
                            // Cancelled (another gesture took over): back into place.
                            if (dragging) release(0f)
                        }
                    },
                ),
        ) {
            content()
        }
    }
}
