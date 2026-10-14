package com.friend.ios.features.agent

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Outline
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiPendantThumbnail
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.service.stores.ChatGrouping
import kotlin.math.min

/*
 * Port of `ChatBubbles.swift`: the pieces the thread is drawn with, as in Messages: the bubble's
 * shape (smaller corners on the sender's side inside a group, a quiet tail on its last bubble),
 * Omi's avatar, the widest a bubble may get, and a stack for cards of one kind.
 */

/** The widest a bubble gets: about 78 % of the thread's width (set by the chat). */
val LocalChatBubbleWidth = compositionLocalOf { 300.dp }

/**
 * As wide as the content wants, up to a bubble's width (iOS `.frame(maxWidth: bubbleWidth,
 * alignment: .leading)` on a card that fills its row).
 */
@Composable
internal fun Modifier.bubbleWide(): Modifier = widthIn(max = LocalChatBubbleWidth.current).fillMaxWidth()

/** Where a bubble sits in its group, which side it is on (`ChatBubbleShape`). */
internal class ChatBubbleShape(private val isUser: Boolean, private val position: ChatGrouping.Position) : Shape {
    override fun createOutline(size: Size, layoutDirection: LayoutDirection, density: Density): Outline {
        val round = with(density) { DS.Radius.bubble.toPx() }
        val joined = with(density) { DS.Radius.bubbleJoined.toPx() }
        val top = if (position.isFirst) round else joined
        val bottom = if (position.isLast) with(density) { DS.Radius.bubbleTail.toPx() } else joined
        // The sender's side is the trailing one for yours, the leading one for Omi's.
        val senderTrailing = isUser == (layoutDirection == LayoutDirection.Ltr)
        val radii = if (senderTrailing) {
            floatArrayOf(round, top, bottom, round)
        } else {
            floatArrayOf(top, round, round, bottom)
        }
        return Outline.Generic(continuousRect(size, radii))
    }

    override fun equals(other: Any?) = other is ChatBubbleShape && other.isUser == isUser && other.position == position
    override fun hashCode() = 31 * isUser.hashCode() + position.hashCode()
}

/**
 * `UnevenRoundedRectangle(cornerRadii:style: .continuous)`: the squircle corners of
 * `ContinuousRoundedShape`, one radius per corner. [radii]: top left, top right, bottom right,
 * bottom left, in pixels. A corner too round for its squircle on a short bubble (one line of text)
 * becomes a circular arc of that radius, as iOS keeps the radius there instead of shrinking it.
 */
private fun continuousRect(size: Size, radii: FloatArray): Path {
    val w = size.width
    val h = size.height
    val half = min(w, h) / 2f
    val squircleLimit = half / K
    val corners = radii.map { radius ->
        val r = min(radius, half)
        Corner(r, continuous = r <= squircleLimit)
    }
    val (tl, tr, br, bl) = corners
    return Path().apply {
        moveTo(tl.reach, 0f)
        lineTo(w - tr.reach, 0f)
        corner(Offset(w, 0f), tr, dx = -1f, dy = 1f, horizontalFirst = true)
        lineTo(w, h - br.reach)
        corner(Offset(w, h), br, dx = -1f, dy = -1f, horizontalFirst = false)
        lineTo(bl.reach, h)
        corner(Offset(0f, h), bl, dx = 1f, dy = -1f, horizontalFirst = true)
        lineTo(0f, tl.reach)
        corner(Offset(0f, 0f), tl, dx = 1f, dy = 1f, horizontalFirst = false)
        close()
    }
}

/** One corner: its radius, and whether it is drawn as a squircle (else a circular arc). */
private class Corner(val r: Float, val continuous: Boolean) {
    /** How far along each edge the corner reaches. */
    val reach: Float get() = if (continuous) K * r else r
}

/** How far along each edge a continuous corner reaches, in units of its radius. */
private const val K = 1.52866483f

/** A quarter circle as one cubic. */
private const val ARC = 0.5522848f

/** The UIBezierPath control points of a continuous corner entered along x, in units of r. */
private val CORNER = arrayOf(
    floatArrayOf(1.08849323f, 0f), floatArrayOf(0.86840689f, 0f), floatArrayOf(0.66993427f, 0.06549600f),
    floatArrayOf(0.63149399f, 0.07491100f),
    floatArrayOf(0.37282392f, 0.16905899f), floatArrayOf(0.16905899f, 0.37282401f), floatArrayOf(0.07491176f, 0.63149399f),
    floatArrayOf(0.06549600f, 0.66993427f),
    floatArrayOf(0f, 0.86840701f), floatArrayOf(0f, 1.08849299f), floatArrayOf(0f, K),
)

/**
 * One corner at [c]. [dx]/[dy] point from the corner into the rect. When [horizontalFirst] the
 * path arrives along a horizontal edge and leaves along a vertical one.
 */
private fun Path.corner(c: Offset, corner: Corner, dx: Float, dy: Float, horizontalFirst: Boolean) {
    val r = corner.r
    if (r <= 0f) {
        lineTo(c.x, c.y)
        return
    }
    if (!corner.continuous) {
        val along = Offset(c.x + dx * r, c.y)
        val across = Offset(c.x, c.y + dy * r)
        val (from, to) = if (horizontalFirst) along to across else across to along
        val first = from + (c - from) * ARC
        val second = to + (c - to) * ARC
        cubicTo(first.x, first.y, second.x, second.y, to.x, to.y)
        return
    }
    val seq = CORNER.map { point ->
        val (a, b) = if (horizontalFirst) point[0] to point[1] else point[1] to point[0]
        Offset(c.x + dx * a * r, c.y + dy * b * r)
    }
    cubicTo(seq[0].x, seq[0].y, seq[1].x, seq[1].y, seq[2].x, seq[2].y)
    lineTo(seq[3].x, seq[3].y)
    cubicTo(seq[4].x, seq[4].y, seq[5].x, seq[5].y, seq[6].x, seq[6].y)
    lineTo(seq[7].x, seq[7].y)
    cubicTo(seq[8].x, seq[8].y, seq[9].x, seq[9].y, seq[10].x, seq[10].y)
}

/** A chat bubble's padding, fill and shape. */
internal fun Modifier.chatBubble(color: Color, isUser: Boolean, position: ChatGrouping.Position): Modifier =
    this.background(color, ChatBubbleShape(isUser, position)).padding(horizontal = 14.dp, vertical = 9.dp)

/** In Omi's column: clear of the avatar beside its bubbles. */
internal fun Modifier.omiColumn(): Modifier = padding(start = OmiAvatarColumn)

/**
 * Port of `OmiAvatar`. Omi's picture beside the last bubble of an Omi group (the pendant); an empty
 * slot of the same width beside the others, so all of Omi's bubbles line up. Hidden from TalkBack.
 */
@Composable
internal fun OmiAvatar(shows: Boolean, modifier: Modifier = Modifier) {
    Box(modifier.size(DS.Size.chatAvatar).clearAndSetSemantics {}) {
        AnimatedVisibility(shows, enter = fadeIn(), exit = fadeOut()) {
            OmiPendantThumbnail(size = DS.Size.chatAvatar)
        }
    }
}

/** The avatar and the gap after it (`OmiAvatar.column`). */
internal val OmiAvatarColumn: Dp = DS.Size.chatAvatar + 6.dp

/** Port of `ChatCardStack`. Cards of one kind in a row: the first, and "2 more" that opens the rest. */
@Composable
internal fun <T> ChatCardStack(items: List<T>, stackKey: String, modifier: Modifier = Modifier, card: @Composable (T) -> Unit) {
    var isOpen by rememberSaveable(stackKey) { mutableStateOf(false) }
    val haptics = rememberHaptics()
    Column(modifier, verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs + 2.dp)) {
        items.firstOrNull()?.let { card(it) }
        AnimatedVisibility(isOpen, enter = fadeIn() + expandVertically(), exit = fadeOut() + shrinkVertically()) {
            Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs + 2.dp)) {
                items.drop(1).forEach { card(it) }
            }
        }
        if (items.size > 1 && !isOpen) {
            HStack(
                Modifier
                    .heightIn(min = 28.dp)
                    .plainButton {
                        haptics.selection()
                        isOpen = true
                    }
                    .padding(horizontal = DS.Spacing.xs),
                spacing = DS.Spacing.xs,
            ) {
                Text(L("nativeChatMoreCards", (items.size - 1).toString()), style = DS.Typography.caption.copy(fontWeight = FontWeight.Medium), color = DS.Palette.inkSecondary)
                SFImage("chevron.down", size = 10.sp, tint = DS.Palette.inkSecondary)
            }
        }
    }
}
