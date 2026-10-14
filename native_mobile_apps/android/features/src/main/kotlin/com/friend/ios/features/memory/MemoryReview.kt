package com.friend.ios.features.memory

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Memory
import com.friend.ios.core.models.MemoryConflict
import com.friend.ios.design.CircleIconButton
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiPrimaryButton
import com.friend.ios.design.OmiSecondaryButton
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.omiCard
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.features.components.DecisionCard
import com.friend.ios.service.LocalMemoriesStore
import com.friend.ios.service.stores.MemoryReviewAnswer
import com.friend.ios.service.stores.MemoryReviewItem
import com.friend.ios.service.stores.MemoryReviewQuestion
import com.friend.ios.service.stores.answer
import com.friend.ios.service.stores.loadReviewQueue
import com.friend.ios.service.stores.reviewQueue
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

/**
 * Port of `MemoryReviewEntry` (`MemoryReview.swift`): the one entry for memories Omi has a reason
 * to doubt, at the top of Memories ("2 memories to check"). Shown only when there are any: a
 * contradiction, someone else as the subject, an old fact, something heard unclearly. Opens
 * [MemoryReviewSheet].
 */
@Composable
fun MemoryReviewEntry(count: Int, modifier: Modifier = Modifier, onOpen: () -> Unit) {
    DecisionCard(
        kicker = DecisionCard.Kicker("questionmark.circle", L("nativeMemoryDoubtsKicker"), DS.Palette.agent),
        title = if (count == 1) L("nativeMemoryDoubtsOne") else L("nativeMemoryDoubts", "$count"),
        subtitle = L("nativeMemoryDoubtsHint"),
        modifier = modifier,
        pills = emptyList(),
        onTap = onOpen,
    )
}

/**
 * Port of `MemoryReviewSheet`: one doubt at a time, asked the way that fits it ("Is this still
 * true?", "Is this about Lena, not you?", "Earlier one thing, now another: which is right?"). The
 * memory itself is shown as a quote under the question, never as the question. The queue is fixed
 * when the sheet opens, so answering does not reshuffle it.
 */
@Composable
fun MemoryReviewSheet(sources: (Memory) -> String?, onDismiss: () -> Unit) {
    val store = LocalMemoriesStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var queue by remember { mutableStateOf<List<MemoryReviewItem>>(emptyList()) }
    var loaded by remember { mutableStateOf(false) }
    var index by remember { mutableIntStateOf(0) }
    var editing by remember { mutableStateOf<Memory?>(null) }
    val current = queue.getOrNull(index)

    LaunchedEffect(Unit) {
        store.loadReviewQueue()
        if (queue.isEmpty()) queue = demoQueue() ?: store.reviewQueue
        // -omiDemoMemoryReviewStart <n> opens the demo at its n-th question.
        if (demoQueue() != null) index = DebugLaunch.string("omiDemoMemoryReviewStart")?.toIntOrNull() ?: 0
        loaded = true
    }

    fun answer(item: MemoryReviewItem, answer: MemoryReviewAnswer) {
        haptics.success()
        if (demoQueue() == null) scope.launch { store.answer(item, answer) }
        index += 1
    }

    /** An edited memory counts as right (the user fixed it); an untouched one stays to answer. */
    fun afterEdit() {
        val item = current as? MemoryReviewItem.ForMemory ?: return
        val edited = store.memories.firstOrNull { it.id == item.memory.id } ?: return
        if (edited.content == item.memory.content) return
        haptics.success()
        scope.launch { store.review(item.memory.id, isRight = true) }
        index += 1
    }

    OmiSheet(onDismiss = onDismiss) {
        Box(Modifier.statusBarsPadding().fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = DS.Spacing.sm)) {
            CircleIconButton("xmark", Modifier.align(Alignment.CenterStart), contentDescription = L("close"), onClick = onDismiss)
            if (current != null) {
                Text(L("nativeMemoryReviewProgress", "${index + 1}", "${queue.size}"), style = TextStyles.headline, color = DS.Palette.ink, modifier = Modifier.align(Alignment.Center))
            }
        }
        Column(Modifier.fillMaxSize().padding(horizontal = DS.Spacing.gutter)) {
            AnimatedContent(
                targetState = index,
                transitionSpec = {
                    val spec = tween<androidx.compose.ui.unit.IntOffset>(350)
                    slideInHorizontally(spec) { it } togetherWith slideOutHorizontally(spec) { -it }
                },
                label = "review",
                modifier = Modifier.weight(1f),
            ) { shown ->
                val item = queue.getOrNull(shown)
                Column(Modifier.fillMaxSize()) {
                    if (item != null) {
                        Question(item, sources, onAnswer = { answer(item, it) }, onEdit = { editing = it })
                    } else if (loaded) {
                        Finished(onDismiss)
                    }
                }
            }
        }
    }
    editing?.let { memory ->
        OmiSheet(onDismiss = { editing = null; afterEdit() }, detents = setOf(Detent.Medium, Detent.Large)) {
            EditMemorySheet(memory, onDismiss = { editing = null; afterEdit() })
        }
    }
}

@Composable
private fun ColumnScope.Question(item: MemoryReviewItem, sources: (Memory) -> String?, onAnswer: (MemoryReviewAnswer) -> Unit, onEdit: (Memory) -> Unit) {
    Text(
        questionText(item.question),
        style = DS.Typography.title,
        color = DS.Palette.ink,
        modifier = Modifier.padding(top = DS.Spacing.xl, bottom = DS.Spacing.lg).semantics { heading() },
    )
    val question = item.question
    if (question is MemoryReviewQuestion.WhichIsRight) {
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            question.earlier?.let { earlier -> Option(L("nativeMemoryEarlier"), earlier) { onAnswer(MemoryReviewAnswer.KeepEarlier) } }
            Option(L("nativeMemoryNow"), question.now) { onAnswer(MemoryReviewAnswer.KeepNew) }
        }
        Spacer(Modifier.weight(1f).heightIn(min = DS.Spacing.xl))
        OmiSecondaryButton(L("nativeMemoryNeither"), Modifier.padding(bottom = DS.Spacing.lg)) { onAnswer(MemoryReviewAnswer.Neither) }
    } else {
        Quote(item, sources)
        Spacer(Modifier.weight(1f).heightIn(min = DS.Spacing.xl))
        Column(Modifier.padding(bottom = DS.Spacing.lg), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            OmiPrimaryButton(L("nativeMemoryReviewYes")) { onAnswer(MemoryReviewAnswer.Yes) }
            OmiSecondaryButton(L("nativeMemoryReviewNo")) { onAnswer(MemoryReviewAnswer.No) }
            if (item is MemoryReviewItem.ForMemory) {
                Box(Modifier.fillMaxWidth().heightIn(min = 44.dp).plainButton { onEdit(item.memory) }, contentAlignment = Alignment.Center) {
                    Text(L("edit"), style = DS.Typography.button, color = DS.Palette.inkSecondary)
                }
            }
        }
    }
}

/** The memory under the question, with where it came from. */
@Composable
private fun Quote(item: MemoryReviewItem, sources: (Memory) -> String?) {
    val memory = (item as? MemoryReviewItem.ForMemory)?.memory ?: return
    Column(Modifier.fillMaxWidth().omiCard(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        Text("“${memory.content}”", style = DS.Typography.body, color = DS.Palette.ink)
        Text(meta(memory, sources), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
    }
}

@Composable
private fun Option(label: String, text: String, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth().plainButton(onClick = onClick).omiCard(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
        Text(label, style = DS.Typography.caption.semibold(), color = DS.Palette.agent)
        Text(text, style = DS.Typography.body, color = DS.Palette.ink)
    }
}

@Composable
private fun Finished(onDismiss: () -> Unit) {
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md, Alignment.CenterVertically), horizontalAlignment = Alignment.CenterHorizontally) {
        SFImage("checkmark.circle", size = 40.sp, weight = FontWeight.Light, tint = DS.Palette.success)
        Text(L("nativeMemoryReviewDone"), style = DS.Typography.sectionTitle, color = DS.Palette.ink)
        OmiPillButton(L("done"), prominent = false, onClick = onDismiss)
    }
}

/** The question in the user's language, from why Omi doubts it. */
@Composable
private fun questionText(question: MemoryReviewQuestion): String = when (question) {
    is MemoryReviewQuestion.WhichIsRight -> L("nativeMemoryAskWhich")
    is MemoryReviewQuestion.AboutSomeoneElse -> question.name?.let { L("nativeMemoryAskAboutName", it) } ?: L("nativeMemoryAskAboutSomeone")
    MemoryReviewQuestion.StillTrue -> L("nativeMemoryAskStillTrue")
    MemoryReviewQuestion.HeardOnce -> L("nativeMemoryAskHeardOnce")
    MemoryReviewQuestion.Unclear -> L("nativeMemoryAskUnclear")
}

/** "From Q4 roadmap with Anna · 7 Oct" or just the date. */
@Composable
private fun meta(memory: Memory, sources: (Memory) -> String?): String {
    val date = DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).format(memory.createdAt.atZone(ZoneId.systemDefault()))
    return sources(memory)?.let { L("nativeFromConversation", it) + " · " + date } ?: date
}

/** `-omiDemoMemoryReview YES` (Debug): one question of each kind, answers go nowhere. */
private fun demoQueue(): List<MemoryReviewItem>? {
    if (!DebugLaunch.flag("omiDemoMemoryReview")) return null
    val date = Instant.now().minusSeconds(86_400)
    fun memory(id: String, content: String) = Memory(id, content, null, "interesting", date, null)
    return listOf(
        MemoryReviewItem.Conflict(
            MemoryConflict("demo-c", "demo-new", "Lives in Munich.", listOf("demo-old"), date),
            earlier = memory("demo-old", "Lives in Berlin."),
        ),
        MemoryReviewItem.ForMemory(memory("demo-3p", "Is moving to Lisbon in March."), MemoryReviewQuestion.AboutSomeoneElse("Lena"), null),
        MemoryReviewItem.ForMemory(memory("demo-once", "Prefers flights before 9 am."), MemoryReviewQuestion.HeardOnce, null),
        MemoryReviewItem.ForMemory(memory("demo-stale", "Works on the Q3 launch plan."), MemoryReviewQuestion.StillTrue, null),
    )
}
