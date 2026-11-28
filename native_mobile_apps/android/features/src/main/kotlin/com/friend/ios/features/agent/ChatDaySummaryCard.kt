package com.friend.ios.features.agent

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.features.components.MarkdownBlocks
import com.friend.ios.service.stores.ChatDaySummary
import java.time.Instant
import java.time.ZoneId
import java.util.Locale

/**
 * Port of `DaySummaryCard` (`ChatDaySummaryCard.swift`). The day's summary Omi posts in the
 * evening: "Day Summary · 7 Oct" over a numbered list of what happened (`day_summary` messages;
 * Flutter `DaySummaryWidget`).
 */
@Composable
fun DaySummaryCard(message: ChatMessage, modifier: Modifier = Modifier) {
    val items = ChatDaySummary.items(message.text)
    Column(modifier.bubbleWide(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        if (message.text.isNotEmpty()) {
            Text(
                L("daySummaryForDate", summaryDate(message.createdAt)),
                style = DS.Typography.sectionTitle,
                color = DS.Palette.inkSecondary,
                modifier = Modifier.semantics { heading() },
            )
        }
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            items.forEachIndexed { index, item ->
                HStack(alignment = androidx.compose.ui.Alignment.Top, spacing = DS.Spacing.md) {
                    Text(
                        "${index + 1}.",
                        style = DS.Typography.callout.copy(fontWeight = FontWeight.Bold, fontFeatureSettings = "tnum"),
                        color = DS.Palette.inkTertiary,
                    )
                    Text(item, style = DS.Typography.callout, color = DS.Palette.ink)
                }
            }
            if (items.isEmpty()) {
                MarkdownBlocks(message.text, style = DS.Typography.bubble, color = DS.Palette.ink)
            }
        }
    }
}

/** The day the summary covers, as "7 Oct 2026" in the reader's language (`Date.formatted(.abbreviated)`). */
fun summaryDate(date: Instant, now: Instant = Instant.now(), zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Locale.getDefault()): String {
    val day = date.atZone(zone).toLocalDate()
    // The year only when it is not this one, as the abbreviated style writes it.
    return MessageTime.day(day, wide = false, withYear = day.year != now.atZone(zone).year, locale = locale)
}
