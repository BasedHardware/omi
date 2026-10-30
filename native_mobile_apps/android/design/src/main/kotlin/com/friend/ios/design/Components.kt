package com.friend.ios.design

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** `SectionHeader`: section title with an optional trailing action ("See all"). */
@Composable
fun SectionHeader(title: String, modifier: Modifier = Modifier, actionTitle: String? = null, action: (() -> Unit)? = null) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
        Text(title, style = DS.Typography.sectionTitle, color = DS.Palette.ink, modifier = Modifier.semantics { heading() })
        Spacer(Modifier.weight(1f))
        if (actionTitle != null && action != null) {
            Text(actionTitle, style = DS.Typography.callout, color = DS.Palette.inkSecondary, modifier = Modifier.plainButton(onClick = action))
        }
    }
}

/** `EmojiBadge`: square emoji badge used by conversation rows. */
@Composable
fun EmojiBadge(emoji: String?, modifier: Modifier = Modifier) {
    Box(
        modifier.size(DS.Size.emojiBadge).background(DS.Palette.fill, ContinuousRoundedShape(DS.Radius.sm)),
        contentAlignment = Alignment.Center,
    ) {
        Text(emoji ?: "💬", style = TextStyles.title3)
    }
}

/** `SkeletonBlock`: shimmer-free loading placeholder (skeleton, never a spinner). */
@Composable
fun SkeletonBlock(modifier: Modifier = Modifier, height: Dp = 64.dp) {
    Box(
        modifier.fillMaxWidth().height(height).background(DS.Palette.card, ContinuousRoundedShape(DS.Radius.card)),
        contentAlignment = Alignment.CenterStart,
    ) {
        Row(Modifier.padding(horizontal = DS.Spacing.lg), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(DS.Size.emojiBadge).background(DS.Palette.fill, ContinuousRoundedShape(DS.Radius.sm)))
            Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                Box(Modifier.width(160.dp).height(10.dp).background(DS.Palette.fill, CircleShape))
                Box(Modifier.width(100.dp).height(8.dp).background(DS.Palette.fill, CircleShape))
            }
        }
    }
}

/** `Pill`: small pill label (counts, statuses). */
@Composable
fun Pill(text: String, modifier: Modifier = Modifier, tint: Color = DS.Palette.inkSecondary) {
    Text(
        text,
        style = DS.Typography.micro,
        color = tint,
        modifier = modifier
            .background(tint.copy(alpha = 0.12f), CircleShape)
            .padding(horizontal = DS.Spacing.sm, vertical = DS.Spacing.xxs + 1.dp),
    )
}
