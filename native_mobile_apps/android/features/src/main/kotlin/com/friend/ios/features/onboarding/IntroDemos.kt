package com.friend.ios.features.onboarding

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Conversation
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiChip
import com.friend.ios.design.OmiHairline
import com.friend.ios.design.OmiLivePill
import com.friend.ios.design.OmiPendantThumbnail
import com.friend.ios.design.SFImage
import com.friend.ios.features.components.AgentTaskStatus
import com.friend.ios.features.components.ConversationRow
import com.friend.ios.features.components.TaskRow
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import java.time.Instant

// The introduction's live demos: small scenes built from the app's own rows (a conversation,
// tasks, memories, the For you card, an ongoing notification), looping while their page shows.

/** A quiet surface edged by a hairline, as the app's cards are. */
@Composable
internal fun Modifier.demoSurface(radius: Dp): Modifier {
    val shape = ContinuousRoundedShape(radius)
    return background(DS.Palette.card, shape).border(DS.Stroke.regular, DS.Palette.cardStroke, shape)
}

/** `DemoClock`: steps a demo through its scenes while its page is showing, then starts over. */
private class DemoClock {
    var scene by mutableIntStateOf(0)
    /** Each round starts as a fresh view, cross-faded, instead of unwinding the last scene. */
    var round by mutableIntStateOf(0)
}

@Composable
private fun rememberDemoClock(active: Boolean, durations: List<Double>): DemoClock {
    val clock = remember { DemoClock() }
    LaunchedEffect(active) {
        clock.scene = 0
        if (!active) return@LaunchedEffect
        while (isActive) {
            durations.forEachIndexed { index, seconds ->
                if (index == 0) {
                    if (clock.round > 0 || clock.scene > 0) {
                        clock.round += 1
                        clock.scene = 0
                    }
                } else {
                    clock.scene = index
                }
                delay((seconds * 1000).toLong())
            }
        }
    }
    return clock
}

/** Fades a whole round in fresh (`.id(round).transition(.opacity)`). */
@Composable
private fun DemoRound(clock: DemoClock, content: @Composable (Int) -> Unit) {
    Crossfade(clock.round, animationSpec = tween(450), label = "demo-round") { _ -> content(clock.scene) }
}

/** Appears with a fade and a small rise, like `.transition(.opacity.combined(with: .offset(y: 8)))`. */
@Composable
private fun Appear(visible: Boolean, content: @Composable () -> Unit) {
    AnimatedVisibility(visible, enter = fadeIn(DS.Motion.standard()) + slideInVertically(DS.Motion.standard()) { 8 }, exit = fadeOut()) { content() }
}

private object Demo {
    @Composable
    fun conversation(processing: Boolean): Conversation {
        val now = Instant.now()
        return Conversation(
            id = "demo", title = if (processing) "" else L("nativeDemoConversationTitle"), overview = L("nativeDemoConversationOverview"),
            emoji = "☕️", category = null, createdAt = now.minusSeconds(600), startedAt = now.minusSeconds(600),
            finishedAt = now.minusSeconds(120), status = if (processing) Conversation.Status.Processing else Conversation.Status.Completed,
            isStarred = false, actionItemCount = if (processing) 0 else 2,
        )
    }

    @Composable
    fun task(key: String, id: String) = ActionItem(
        id = id, description = L(key), isCompleted = false, dueAt = null, conversationID = "demo", owner = ActionItem.Owner.User,
        workstreamID = null, createdAt = null,
    )
}

/** A conversation recorded live, processed, then its summary and next steps. */
@Composable
internal fun ListenDemo(isActive: Boolean) {
    val clock = rememberDemoClock(isActive, listOf(2.6, 1.3, 3.6))
    var since by remember { mutableLongStateOf(System.currentTimeMillis() - 42_000) }
    LaunchedEffect(clock.scene) { if (clock.scene == 0) since = System.currentTimeMillis() - 42_000 }
    DemoRound(clock) { scene ->
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            if (scene == 0) {
                OmiLivePill(since)
                TranscriptLine(L("nativeSpeakerYou"), L("nativeDemoLineYou"), isUser = true)
                TranscriptLine(L("nativeDemoSpeaker", "1"), L("nativeDemoLineOther"), isUser = false)
            } else {
                ConversationRow(Demo.conversation(processing = scene == 1))
                Appear(scene == 2) {
                    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                        Text(
                            L("nativeDemoConversationOverview"), style = DS.Typography.callout, color = DS.Palette.inkSecondary,
                            modifier = Modifier.padding(horizontal = DS.Spacing.xs),
                        )
                        Column(Modifier.padding(horizontal = DS.Spacing.xs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                            TaskRow(Demo.task("nativeDemoTaskSlides", "t1"), onToggle = {})
                            TaskRow(Demo.task("nativeDemoTaskTable", "t2"), onToggle = {})
                        }
                    }
                }
            }
        }
    }
}

/** One line of a transcript: who, then what was said. */
@Composable
internal fun TranscriptLine(speaker: String, text: String, isUser: Boolean, icon: String? = null) {
    Column(Modifier.fillMaxWidth().demoSurface(DS.Radius.md).padding(DS.Spacing.md), verticalArrangement = Arrangement.spacedBy(3.dp)) {
        val tint = if (isUser) DS.Palette.agent else DS.Palette.inkSecondary
        HStack(spacing = DS.Spacing.xs) {
            SFImage(icon ?: if (isUser) "person.fill" else "person", size = 11.sp, tint = tint)
            Text(speaker, style = DS.Typography.micro, color = tint)
        }
        Text(text, style = DS.Typography.body, color = DS.Palette.ink)
    }
}

/** "What I know about you", growing one memory at a time. */
@Composable
internal fun MemoryDemo(isActive: Boolean) {
    val keys = listOf("nativeDemoMemory1", "nativeDemoMemory2", "nativeDemoMemory3", "nativeDemoMemory4")
    val symbols = listOf("person.2", "sunrise", "figure.run", "fork.knife")
    val clock = rememberDemoClock(isActive, listOf(1.1, 1.1, 1.1, 3.2))
    DemoRound(clock) { scene ->
        Column(Modifier.fillMaxWidth()) {
            Text(L("nativeWhatIKnowAboutYou"), style = DS.Typography.sectionTitle, color = DS.Palette.ink, modifier = Modifier.padding(bottom = DS.Spacing.md))
            Column(Modifier.fillMaxWidth().demoSurface(DS.Radius.card).padding(horizontal = DS.Spacing.md)) {
                keys.forEachIndexed { index, key ->
                    Appear(index <= scene) {
                        Column {
                            if (index > 0) OmiHairline(leading = 44.dp)
                            HStack(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.sm + 2.dp), spacing = DS.Spacing.md) {
                                Box(Modifier.size(32.dp).background(DS.Palette.tile, ContinuousRoundedShape(DS.Radius.sm)), contentAlignment = Alignment.Center) {
                                    SFImage(symbols[index], tint = DS.Palette.inkSecondary)
                                }
                                Text(L(key), style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.weight(1f))
                                SFImage("ellipsis", tint = DS.Palette.inkTertiary)
                            }
                        }
                    }
                }
            }
            Text(
                L("nativeDemoMemoryHint"), style = DS.Typography.caption, color = DS.Palette.inkTertiary,
                modifier = Modifier.padding(top = DS.Spacing.sm).alpha(if (scene == keys.size - 1) 1f else 0f),
            )
        }
    }
}

/** "Speaker 1" until Omi asks once who it was; from then on, the name. */
@Composable
internal fun VoicesDemo(isActive: Boolean) {
    val clock = rememberDemoClock(isActive, listOf(1.6, 2.0, 3.6))
    DemoRound(clock) { scene ->
        val other = if (scene >= 2) "Anna" else L("nativeDemoSpeaker", "1")
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            TranscriptLine(L("nativeSpeakerYou"), L("nativeDemoLineYou"), isUser = true)
            TranscriptLine(other, L("nativeDemoLineOther"), isUser = false, icon = if (scene >= 2) "person.crop.circle.badge.checkmark" else null)
            Appear(scene == 1) {
                HStack(
                    Modifier.fillMaxWidth().background(DS.Palette.agentSoft, ContinuousRoundedShape(DS.Radius.md)).padding(DS.Spacing.md),
                    spacing = DS.Spacing.sm,
                ) {
                    Text(L("nativeDemoWhoWasThis"), style = DS.Typography.cardTitle, color = DS.Palette.ink, modifier = Modifier.weight(1f))
                    OmiChip("Anna", tint = DS.Palette.agent)
                    OmiChip("Ben")
                }
            }
            Appear(scene >= 2) {
                TranscriptLine("Anna", L("nativeDemoLineOther2"), isUser = false, icon = "person.crop.circle.badge.checkmark")
            }
        }
    }
}

/** The For you card: a suggestion that came on its own and the daily recap. */
@Composable
internal fun ForYouDemo(isActive: Boolean) {
    val clock = rememberDemoClock(isActive, listOf(1.4, 4.0))
    DemoRound(clock) { scene ->
        val scale by animateFloatAsState(if (scene == 0) 0.98f else 1f, DS.Motion.standard(), label = "for-you-scale")
        Column(Modifier.fillMaxWidth()) {
            Text(L("forYou"), style = DS.Typography.sectionTitle, color = DS.Palette.ink, modifier = Modifier.padding(bottom = DS.Spacing.md))
            Column(Modifier.fillMaxWidth().scale(scale).demoSurface(DS.Radius.card).padding(horizontal = DS.Spacing.md)) {
                ForYouRow("sparkles", L("nativeDemoForYouPrep"), L("nativeDemoForYouPrepDetail"), DS.Palette.agent)
                Appear(scene >= 1) {
                    Column {
                        OmiHairline(leading = 52.dp)
                        ForYouRow("moon.stars", L("nativeDemoForYouRecap"), L("nativeDemoForYouRecapDetail"), DS.Palette.inkSecondary)
                    }
                }
            }
        }
    }
}

@Composable
private fun ForYouRow(symbol: String, title: String, detail: String, tint: Color) {
    HStack(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.md), spacing = DS.Spacing.md) {
        Box(Modifier.size(36.dp).background(DS.Palette.tile, CircleShape), contentAlignment = Alignment.Center) { SFImage(symbol, tint = tint) }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, style = DS.Typography.cardTitle, color = DS.Palette.ink)
            Text(detail, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
        }
        SFImage("chevron.right", size = 13.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkTertiary)
    }
}

/** A task handed over: Omi takes it, works on it, and the lock screen shows how far it got. */
@Composable
internal fun HandOverDemo(isActive: Boolean) {
    val clock = rememberDemoClock(isActive, listOf(1.6, 1.6, 3.2))
    DemoRound(clock) { scene ->
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg)) {
            Box(Modifier.fillMaxWidth().demoSurface(DS.Radius.card).padding(DS.Spacing.md)) {
                TaskRow(
                    Demo.task("nativeDemoTaskTable", "t2"),
                    agentStatus = if (scene >= 1) AgentTaskStatus.working else null,
                    onToggle = {}, onHandOver = {},
                )
            }
            Appear(scene >= 1) { LockScreenActivity(if (scene >= 2) 0.66f else 0.33f) }
        }
    }
}

/** A Live Activity as it looks on the lock screen (Android: the ongoing notification). */
@Composable
internal fun LockScreenActivity(progress: Float) {
    val animated by animateFloatAsState(progress, DS.Motion.standard(), label = "lock-progress")
    Column(
        Modifier.fillMaxWidth().background(DS.Palette.cardRaised, ContinuousRoundedShape(DS.Radius.hero)).padding(DS.Spacing.lg),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        HStack(spacing = DS.Spacing.sm) {
            OmiPendantThumbnail(22.dp)
            Text(L("nativeOmiOnIt"), style = DS.Typography.cardTitle, color = DS.Palette.ink, modifier = Modifier.weight(1f))
            SFImage("lock.fill", size = 12.sp, tint = DS.Palette.inkTertiary)
        }
        Text(L("nativeDemoLockScreen"), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
        BoxWithConstraints(Modifier.fillMaxWidth().height(4.dp).background(DS.Palette.ink.copy(alpha = 0.1f), CircleShape)) {
            Box(Modifier.width(maxWidth * animated).height(4.dp).background(DS.Palette.agent, CircleShape))
        }
    }
}
