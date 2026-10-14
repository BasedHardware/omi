package com.friend.ios.features.today

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.DailySummary
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.pressable
import com.friend.ios.features.components.ConversationRow
import com.friend.ios.features.components.ConversationRowStyle
import com.friend.ios.features.components.Formatting
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.stores.ConversationsStore
import kotlinx.coroutines.launch
import java.time.ZoneId

/**
 * Port of `RecapRow` (`DailyRecaps.swift`): a day's recap as the first row under its day on Home:
 * "Recap: <headline>", opens the recap. For yesterday without one (but with conversations) the
 * row offers to write it.
 */
@Composable
fun RecapRow(kind: ConversationsStore.RecapSlot, onOpen: (DailySummary) -> Unit, modifier: Modifier = Modifier) {
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    val isWriting = kind is ConversationsStore.RecapSlot.Write && conversations.isCreatingRecap
    val title = when (kind) {
        // Headlines are sentences ("Q4 roadmap and physio."); after "Recap:" the period reads odd.
        is ConversationsStore.RecapSlot.Recap -> L("nativeHomeRecapTitle", kind.recap.headline.removeSuffix("."))
        is ConversationsStore.RecapSlot.Write -> L("nativeHomeWriteRecap")
    }
    val subtitle = when (kind) {
        is ConversationsStore.RecapSlot.Recap -> kind.recap.overview.replace("\n", " ")
        is ConversationsStore.RecapSlot.Write -> L("nativeHomeWriteRecapHint")
    }
    val symbol = if (kind is ConversationsStore.RecapSlot.Recap) "calendar" else "sparkles"
    Column(
        modifier
            .fillMaxWidth()
            .pressable(enabled = !isWriting) {
                when (kind) {
                    is ConversationsStore.RecapSlot.Recap -> onOpen(kind.recap)
                    is ConversationsStore.RecapSlot.Write -> scope.launch { conversations.createRecap(kind.day) }
                }
            }
            .padding(vertical = DS.Spacing.sm + 2.dp),
        verticalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        // Text-first like the conversations below; only Omi's sparkle carries the accent.
        HStack(spacing = 6.dp) {
            if (isWriting) {
                OmiProgress(Modifier.size(12.dp))
            } else {
                SFImage(symbol, size = 14.sp, tint = DS.Palette.agent)
            }
            Text(title, style = DS.Typography.cardTitle, color = DS.Palette.ink, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        Text(subtitle, style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/**
 * Port of `RecapScreen` (`DailyRecaps.swift`): one day in review, pushed like a conversation (so
 * the edge swipe goes back), with that day's conversations to open.
 */
@Composable
fun RecapScreen(recap: DailySummary, onOpenConversation: (Conversation) -> Unit, modifier: Modifier = Modifier) {
    val conversations = LocalConversationsStore.current
    val zone = ZoneId.systemDefault()
    val day = recap.day
    val dayConversations = if (day == null) emptyList() else conversations.conversations.filter { it.date.atZone(zone).toLocalDate() == day }
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(DS.Spacing.gutter),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.xl),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            Text(day?.let { Formatting.dayTitle(it) } ?: recap.date, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
            HStack(spacing = DS.Spacing.sm, alignment = Alignment.Top) {
                recap.emoji?.let { Text(it, style = TextStyles.system(22)) }
                Text(recap.headline, style = DS.Typography.title, color = DS.Palette.ink)
            }
            Text(
                recap.overview,
                style = DS.Typography.body.copy(lineHeight = DS.Typography.body.lineHeight * 1.15f),
                color = DS.Palette.ink,
                modifier = Modifier.padding(top = DS.Spacing.xs),
            )
        }
        if (recap.highlights.isNotEmpty()) {
            RecapSection(L("highlights")) {
                recap.highlights.forEach { highlight ->
                    HStack(Modifier.fillMaxWidth(), spacing = DS.Spacing.md, alignment = Alignment.Top) {
                        Box(Modifier.width(30.dp), contentAlignment = Alignment.Center) { Text(highlight.emoji ?: "•", style = TextStyles.system(22)) }
                        Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                            Text(highlight.topic, style = DS.Typography.cardTitle, color = DS.Palette.ink)
                            Text(highlight.summary, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                        }
                    }
                }
            }
        }
        if (recap.decisions.isNotEmpty()) {
            RecapSection(L("decisions")) {
                recap.decisions.forEach { decision ->
                    HStack(spacing = DS.Spacing.md, alignment = Alignment.Top) {
                        Box(Modifier.width(30.dp), contentAlignment = Alignment.Center) {
                            SFImage("checkmark", size = 14.sp, tint = DS.Palette.inkSecondary)
                        }
                        Text(decision, style = DS.Typography.body, color = DS.Palette.ink)
                    }
                }
            }
        }
        if (dayConversations.isNotEmpty()) {
            RecapSection(L("nativeThatDaysConversations")) {
                // The same rows as on Home.
                dayConversations.forEach { conversation ->
                    ConversationRow(conversation, Modifier.pressable { onOpenConversation(conversation) }, style = ConversationRowStyle.Plain)
                }
            }
        }
    }
}

/** A small gray label, then the rows on the page (no card). */
@Composable
private fun RecapSection(title: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        Text(title, style = DS.Typography.sectionLabel, color = DS.Palette.inkSecondary, modifier = Modifier.semantics { heading() })
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) { content() }
    }
}
