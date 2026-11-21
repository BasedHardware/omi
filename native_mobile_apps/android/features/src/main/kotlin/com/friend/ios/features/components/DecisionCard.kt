package com.friend.ios.features.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.MenuSection
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.medium
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold

/**
 * Port of `DecisionCard.swift`: something that needs a decision, as a raised card (Home's "For you"
 * items, the memory review entry; the Iris "Want me to handle it?" card): a small colored kicker
 * that says what kind of item it is, the title, one line of context, and pill buttons when there
 * are two or more choices. Tapping the card itself does the item's main thing. No swipe: a
 * sideways drag would fight the swipe between Home, Tasks and Memories. [menu] is the
 * `.contextMenu` the call sites attach.
 */
object DecisionCard {
    data class Kicker(val symbol: String, val text: String, val color: Color)

    class Pill(val title: String, val isPrimary: Boolean = false, val action: () -> Unit) {
        val id: String get() = title
    }
}

@Composable
fun DecisionCard(
    kicker: DecisionCard.Kicker,
    title: String,
    subtitle: String,
    modifier: Modifier = Modifier,
    source: String? = null,
    /** Omi is working: the kicker's glyph breathes. */
    pulses: Boolean = false,
    pills: List<DecisionCard.Pill>,
    onTap: (() -> Unit)?,
    menu: (() -> List<MenuSection>)? = null,
    /** In the chat thread: the smaller card, as the bubbles (at most two pills, no stroke). */
    compact: Boolean = false,
) {
    val haptics = rememberHaptics()
    val shape = ContinuousRoundedShape(if (compact) DS.Radius.bubble else DS.Radius.card)
    val shownPills = if (compact) pills.take(2) else pills
    val content: @Composable () -> Unit = {
        Column(
            Modifier
                .fillMaxWidth()
                .background(DS.Palette.card, shape)
                .then(if (compact) Modifier else Modifier.border(0.5.dp, DS.Palette.cardStroke, shape))
                .padding(
                    horizontal = if (compact) 14.dp else DS.Spacing.lg,
                    vertical = if (compact) DS.Spacing.sm + 2.dp else DS.Spacing.md,
                ),
            verticalArrangement = Arrangement.spacedBy(if (compact) DS.Spacing.xs + 2.dp else DS.Spacing.sm),
        ) {
            HStack(spacing = if (compact) DS.Spacing.xs else 6.dp) {
                SFImage(kicker.symbol, Modifier.symbolPulse(pulses), size = if (compact) 11.sp else 12.sp, weight = androidx.compose.ui.text.font.FontWeight.SemiBold, tint = kicker.color)
                Text(kicker.text, style = if (compact) TextStyles.caption1.semibold() else TextStyles.footnote.semibold(), color = kicker.color)
            }
            Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(
                    title, style = if (compact) DS.Typography.callout.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Medium) else TextStyles.body.medium(), color = DS.Palette.ink,
                    maxLines = if (compact) 1 else 2, overflow = TextOverflow.Ellipsis,
                )
                if (subtitle.isNotEmpty()) {
                    Text(
                        subtitle, style = if (compact) DS.Typography.caption else DS.Typography.callout, color = DS.Palette.inkSecondary,
                        maxLines = if (compact) 1 else 2, overflow = TextOverflow.Ellipsis,
                    )
                }
                if (!source.isNullOrEmpty()) {
                    Text(
                        source,
                        style = DS.Typography.caption,
                        color = DS.Palette.inkTertiary,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(top = 1.dp),
                    )
                }
            }
            if (shownPills.isNotEmpty()) {
                HStack(Modifier.padding(top = 2.dp), spacing = DS.Spacing.sm) {
                    shownPills.forEach { pill ->
                        Text(
                            pill.title,
                            style = if (compact) TextStyles.footnote.semibold() else TextStyles.subheadline.semibold(),
                            color = if (pill.isPrimary) DS.Palette.onAccent else DS.Palette.ink,
                            maxLines = 1,
                            modifier = Modifier
                                .plainButton {
                                    haptics.tap()
                                    pill.action()
                                }
                                .then(
                                    if (pill.isPrimary) Modifier.background(DS.Palette.ink, CircleShape)
                                    else Modifier.border(1.dp, DS.Palette.fill, CircleShape),
                                )
                                .padding(horizontal = DS.Spacing.md, vertical = if (compact) 6.dp else 7.dp),
                        )
                    }
                }
            }
        }
    }
    if (menu != null) {
        ContextMenuBox(sections = menu, modifier = modifier, onTap = onTap, content = content)
    } else {
        Box(modifier.then(if (onTap != null) Modifier.tapGesture(onTap) else Modifier)) { content() }
    }
}

/** `.onTapGesture { }`: a tap with no press feedback and no ripple. */
fun Modifier.tapGesture(onTap: () -> Unit): Modifier = this.then(
    Modifier.clickable(
        interactionSource = null,
        indication = null,
        onClick = onTap,
    ),
)
