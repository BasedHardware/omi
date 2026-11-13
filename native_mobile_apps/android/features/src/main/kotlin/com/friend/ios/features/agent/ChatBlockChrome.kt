package com.friend.ios.features.agent

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold

/*
 * Port of `ChatBlockChrome.swift`: the pieces every content-block card shares: the card itself,
 * its kind in small caps, the link card, the one action a card offers, and the line a block with
 * no card stays readable as.
 */

/** The lines the cards cannot draw, when the cards replaced the body (otherwise the body already
 * carries them). A thinking line, a tool call, a type this client does not know: each stays
 * readable instead of vanishing.
 */
@Composable
fun ChatBlockFallbacks(lines: List<String>, modifier: Modifier = Modifier) {
    if (lines.isEmpty()) return
    Column(modifier.bubbleWide(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
        for (line in lines) {
            Text(line, style = DS.Typography.caption, color = DS.Palette.inkTertiary)
        }
    }
}

/**
 * The card every block draws on: the chat card color, a soft radius, and the file's own padding.
 * A card is tappable only when it leads somewhere.
 */
@Composable
fun ChatBlockCard(modifier: Modifier = Modifier, onTap: (() -> Unit)? = null, content: @Composable () -> Unit) {
    val haptics = rememberHaptics()
    var card = modifier.fillMaxWidth().background(DS.Palette.card, ContinuousRoundedShape(DS.Radius.bubble))
    if (onTap != null) {
        card = card.plainButton {
            haptics.tap()
            onTap()
        }
    }
    Column(card.padding(horizontal = 14.dp, vertical = DS.Spacing.sm + 1.dp)) { content() }
}

/** What the card holds: its kind, in small caps, with the sign that goes with it. */
@Composable
fun ChatBlockEyebrow(symbol: String, label: String, modifier: Modifier = Modifier) {
    HStack(modifier, spacing = DS.Spacing.xs + 2.dp) {
        SFImage(symbol, size = 12.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkSecondary)
        Text(label, style = DS.Typography.caption.semibold(), color = DS.Palette.inkSecondary, letterSpacing = DS.Tracking.label.sp)
    }
}

/**
 * A block whose entity is not in the loaded list, or a store that is still fetching it. No dead
 * affordance either way: the card says what it cannot do.
 */
@Composable
fun ChatBlockNotice(symbol: String, label: String, message: String, isLoading: Boolean = false, modifier: Modifier = Modifier) {
    ChatBlockCard(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs + 2.dp)) {
            ChatBlockEyebrow(symbol, label)
            HStack(spacing = DS.Spacing.sm) {
                if (isLoading) OmiProgress(Modifier.size(12.dp), tint = DS.Palette.inkSecondary)
                Text(message, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
            }
        }
    }
}

/**
 * Summary plus its one destination, shared by the goal, memory and conversation cards. The action
 * is the card's only affordance, so it is drawn as the compact button it is (Flutter
 * `ChatBlockLinkCard`).
 */
@Composable
fun ChatBlockLinkCard(
    symbol: String,
    eyebrow: String,
    summary: String,
    action: String,
    modifier: Modifier = Modifier,
    footer: (@Composable () -> Unit)? = null,
    onOpen: (() -> Unit)? = null,
) {
    ChatBlockCard(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            ChatBlockEyebrow(symbol, eyebrow)
            if (summary.isNotEmpty()) Text(summary, style = DS.Typography.callout, color = DS.Palette.ink)
            footer?.invoke()
            if (onOpen != null) ChatBlockAction(action, onOpen = onOpen)
        }
    }
}

/** A left-aligned compact button inside a card (Flutter `OmiButton.tertiary` with `open_in_new`). */
@Composable
fun ChatBlockAction(title: String, modifier: Modifier = Modifier, onOpen: () -> Unit) {
    val haptics = rememberHaptics()
    HStack(
        modifier
            .heightIn(min = 36.dp)
            .plainButton {
                haptics.tap()
                onOpen()
            }
            .background(DS.Palette.agentSoft, CircleShape)
            .padding(horizontal = DS.Spacing.md, vertical = DS.Spacing.xs + 2.dp),
        spacing = DS.Spacing.xs + 2.dp,
    ) {
        SFImage("arrow.up.forward.app", size = 12.sp, weight = FontWeight.SemiBold, tint = DS.Palette.agent)
        Text(title, style = DS.Typography.caption.semibold(), color = DS.Palette.agent)
    }
}
