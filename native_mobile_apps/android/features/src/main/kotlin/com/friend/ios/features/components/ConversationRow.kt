package com.friend.ios.features.components

import android.text.format.DateFormat
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Conversation
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.Formatted
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.Pill
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.omiCardSurface
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt

/**
 * Port of `ConversationRow.swift`: one conversation as Omi shows it: emoji tile, title,
 * "9:12 AM · 2m". On Home each row is its own card; inside a list use `Plain`, the list draws the
 * cell. A star marks starred ones; while selecting, a check circle leads.
 */
enum class ConversationRowStyle { Card, Plain }

/** [isSelected] is null outside selection mode. */
@Composable
fun ConversationRow(
    conversation: Conversation,
    modifier: Modifier = Modifier,
    isSelected: Boolean? = null,
    style: ConversationRowStyle = ConversationRowStyle.Card,
) {
    val card = style == ConversationRowStyle.Card
    HStack(
        modifier
            .fillMaxWidth()
            .then(if (card) Modifier.omiCardSurface() else Modifier)
            .padding(horizontal = if (card) DS.Spacing.md else 0.dp, vertical = if (card) DS.Spacing.md - 2.dp else DS.Spacing.xxs),
        spacing = DS.Spacing.md,
    ) {
        if (isSelected != null) {
            SFImage(
                if (isSelected) "checkmark.circle.fill" else "circle",
                size = 22.sp,
                tint = if (isSelected) DS.Palette.agent else DS.Palette.inkTertiary,
            )
        }
        // Cards keep the emoji tile; plain lists show the emoji on its own, no tile behind it.
        if (card) {
            EmojiTile(conversation.emoji ?: "💬")
        } else {
            Box(Modifier.width(30.dp), contentAlignment = Alignment.Center) {
                Text(conversation.emoji ?: "💬", style = TextStyles.system(22))
            }
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(conversation.displayTitle(), style = DS.Typography.cardTitle, color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
            HStack(spacing = DS.Spacing.sm) {
                Text(Formatting.meta(conversation), style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 1, softWrap = false)
                Status(conversation)
            }
        }
        if (conversation.isStarred) {
            SFImage("star.fill", size = 13.sp, tint = DS.Palette.warning)
        }
    }
}

@Composable
private fun Status(conversation: Conversation) {
    when {
        conversation.status == Conversation.Status.Processing || conversation.status == Conversation.Status.InProgress ->
            Pill(L("nativeProcessing"), tint = DS.Palette.warning)
        conversation.status == Conversation.Status.Merging -> Pill(L("nativeMerging"), tint = DS.Palette.agent)
        conversation.summaryFailed -> Pill(L("nativeSummaryFailed"), tint = DS.Palette.live)
        conversation.actionItemCount > 0 -> {
            // Quiet: Home shows many rows; the agent color is for what Omi does, not for counts.
            val label = if (conversation.actionItemCount == 1) L("nativeNextStepOne") else L("nativeNextStepsCount", "${conversation.actionItemCount}")
            HStack(spacing = 3.dp) {
                SFImage("checklist", size = 10.sp, tint = DS.Palette.inkTertiary)
                Text(label, style = DS.Typography.caption, color = DS.Palette.inkTertiary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

/** The square emoji tile on conversation and recap rows. On the page itself (not on a card) pass `DS.Palette.card` as [fill]. */
@Composable
fun EmojiTile(emoji: String, modifier: Modifier = Modifier, fill: Color = DS.Palette.tile) {
    Box(
        modifier.size(DS.Size.tile).background(fill, ContinuousRoundedShape(DS.Radius.tile)),
        contentAlignment = Alignment.Center,
    ) {
        Text(emoji, style = TextStyles.system(20))
    }
}

/** The `Formatting` enum of `ConversationRow.swift`. */
object Formatting {
    /** "9:12 AM · 2m", Omi's row meta. */
    fun meta(conversation: Conversation): String {
        val time = Formatted.shortTime(conversation.date)
        val duration = conversation.duration ?: return time
        return "$time · ${length(duration)}"
    }

    /** "2m", "1h 35m"; anything under a minute counts as a minute, as in Omi. */
    fun length(seconds: Double): String {
        val minutes = maxOf(1, (seconds / 60).roundToInt())
        return if (minutes >= 60) "${minutes / 60}h ${minutes % 60}m" else "${minutes}m"
    }

    /** "Today", "Yesterday", or "Tue, Sep 29". */
    @Composable
    fun dayTitle(day: LocalDate, now: Instant = Instant.now(), zone: ZoneId = ZoneId.systemDefault()): String {
        val today = now.atZone(zone).toLocalDate()
        if (day == today) return L("today")
        if (day == today.minusDays(1)) return L("yesterday")
        return weekdayMonthDay(day)
    }

    /** `.dateTime.weekday(.abbreviated).month(.abbreviated).day()`. */
    fun weekdayMonthDay(day: LocalDate, locale: Locale = Locale.getDefault()): String =
        DateTimeFormatter.ofPattern(DateFormat.getBestDateTimePattern(locale, "EEEMMMd"), locale).format(day)

    /** `.dateTime.weekday(.abbreviated)`: "Wed". */
    fun weekday(instant: Instant, locale: Locale = Locale.getDefault(), zone: ZoneId = ZoneId.systemDefault()): String =
        DateTimeFormatter.ofPattern(DateFormat.getBestDateTimePattern(locale, "EEE"), locale).format(instant.atZone(zone))
}
