package com.friend.ios.features.today

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.pressable
import com.friend.ios.features.components.AgentWording
import com.friend.ios.features.components.symbolPulse
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.service.stores.HomeAttention
import com.friend.ios.service.stores.question

/**
 * Port of `ForYouRow.swift`: one "For you" row: an icon in a small tinted circle, a title, a
 * one-line subtitle, a chevron. One accent per row (the icon); text stays ink and secondary ink.
 */
object ForYouRow {
    data class Content(
        val symbol: String,
        val tint: Tint,
        val title: String,
        val subtitle: String,
        /** Omi is working: the icon breathes. */
        val pulses: Boolean = false,
    ) {
        enum class Tint { Agent, Attention, Neutral }

        companion object {
            /** The words and icon for one attention item. */
            @Composable
            fun from(item: HomeAttention.Item, taskSource: (ActionItem) -> String?): Content = when (item) {
                is HomeAttention.Item.Finished -> {
                    val result = firstLine(item.run.state)
                    val done = L("nativeOmiFinished")
                    Content("sparkles", Tint.Agent, item.run.taskTitle, if (result.isEmpty()) done else "$done · $result")
                }
                is HomeAttention.Item.FinishedGroup -> Content(
                    "sparkles", Tint.Agent, L("nativeHomeOmiFinishedCount", "${item.runs.size}"),
                    item.runs.joinToString(" · ") { it.taskTitle },
                )
                is HomeAttention.Item.Working -> {
                    val step = (item.run.state as? AgentStore.RunState.Working)?.step?.ifEmpty { null } ?: L("nativeOmiOnIt")
                    Content("sparkles", Tint.Agent, item.run.taskTitle, step, pulses = true)
                }
                is HomeAttention.Item.OmiAsks -> {
                    val presentation = com.friend.ios.features.components.omiAsksPresentation(item.pending)
                    Content("questionmark.bubble", Tint.Agent, presentation.title, presentation.subtitle)
                }
                // Why it stopped, in plain words ("Omi got stuck and stopped").
                is HomeAttention.Item.NeedsHelp -> Content(
                    "hand.raised", Tint.Attention, item.run.taskTitle,
                    item.run.failure?.let { AgentWording.words(it) } ?: L("nativeHomeNeedsYourHelp"),
                )
                // Asked, in the backend's own next-action words: "Send Anna the Thursday follow-up?"
                is HomeAttention.Item.RecommendationItem ->
                    Content("flag", Tint.Attention, item.recommendation.question, item.recommendation.whyNow)
                is HomeAttention.Item.Task ->
                    Content("checklist", Tint.Neutral, item.card.task.description, taskSource(item.card.task) ?: "")
                is HomeAttention.Item.TidyUp ->
                    Content("sparkles", Tint.Agent, TidyUpWording.title(item.proposal), L("nativeTidyUpSubtitle"))
                is HomeAttention.Item.Nudge -> Content("lightbulb", Tint.Neutral, item.item.title, oneLine(item.item.body))
                is HomeAttention.Item.SpeakerPrompt ->
                    Content("person.wave.2.fill", Tint.Neutral, SpeakerPromptCard.question(item.prompt), context(item.prompt))
                HomeAttention.Item.SiriTip -> Content("mic", Tint.Neutral, L("nativeHomeSiriTitle"), L("nativeHomeSiriSubtitle"))
                is HomeAttention.Item.Connect -> Content(
                    "link", Tint.Agent, L("nativeForYouConnectTitle", ConnectSuggestion.name(item.connection)),
                    ConnectSuggestion.purpose(item.connection),
                )
            }

            private fun oneLine(text: String): String = text.replace("\n", " ")

            @Composable
            private fun context(prompt: com.friend.ios.core.models.SpeakerPrompt): String {
                val title = prompt.conversationTitle.ifEmpty { L("untitledConversation") }
                return if (prompt.excerpt.isEmpty()) title else "\u201C${oneLine(prompt.excerpt)}\u201D \u00B7 $title"
            }

            /**
             * Results are Markdown: the first line without its heading or emphasis marks. The agent
             * often opens with a plan ("I'll start by ..."); the first line after it says what it did.
             */
            private fun firstLine(state: AgentStore.RunState): String {
                val result = (state as? AgentStore.RunState.Done)?.result ?: return ""
                val lines = result.lines().filter { it.isNotBlank() }
                val preamble = listOf("I'll ", "I will ", "Let me ", "First, I'll ")
                val line = lines.firstOrNull { line -> preamble.none { line.startsWith(it) } } ?: lines.firstOrNull() ?: ""
                return line.trim { it in "#*_> " || it.isWhitespace() }
            }
        }
    }

    /** 32 pt at the default size, at most 44 pt. */
    fun circleSize(scaled: Float): Float = minOf(scaled, 44f)
}

@Composable
fun ForYouRow(content: ForYouRow.Content, isTappable: Boolean, modifier: Modifier = Modifier, action: () -> Unit) {
    // A thin line glyph, no tinted circle: only Omi's own work carries the accent.
    val color = if (content.tint == ForYouRow.Content.Tint.Agent) DS.Palette.agent else DS.Palette.inkSecondary
    val iconSize = ForYouRow.circleSize(32f)
    HStack(
        modifier
            .then(if (isTappable) Modifier.pressable(onClick = action) else Modifier)
            .padding(vertical = DS.Spacing.sm + 2.dp)
            .heightIn(min = 52.dp),
        spacing = DS.Spacing.md,
    ) {
        Box(Modifier.size(iconSize.dp), contentAlignment = Alignment.Center) {
            SFImage(content.symbol, Modifier.symbolPulse(content.pulses), size = (iconSize * 0.56f).sp, tint = color)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
            Text(content.title, style = DS.Typography.cardTitle, color = DS.Palette.ink, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (content.subtitle.isNotEmpty()) {
                Text(content.subtitle, style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}
