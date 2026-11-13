package com.friend.ios.features.today

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.platform.LocalContext
import com.friend.ios.core.models.Recommendation
import com.friend.ios.design.AvatarContent
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.features.components.DecisionCard
import com.friend.ios.features.components.Formatting
import com.friend.ios.features.components.TaskCardModern
import com.friend.ios.features.components.displayTitle
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.stores.EntityVisual
import com.friend.ios.service.stores.RecommendationOrigin
import com.friend.ios.service.stores.TaskConsolidation
import com.friend.ios.service.stores.canTakeOver
import com.friend.ios.service.stores.distinctGoalLabel
import com.friend.ios.service.stores.origin
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId

/**
 * Port of `NeedsYouTaskCard.swift` as the Home task card, variant C (docs/HOME_TASK_CARD.md): why
 * now (the meta line), the task, where it was heard; the magic button starts Omi right away (or
 * marks it done where Omi cannot help); a right swipe puts it off until tomorrow, with Undo. Long
 * press for the rest, including "Not a task" (the learning signal).
 */
@Composable
internal fun TaskCard(card: TaskConsolidation.Card, state: NeedsYouState) {
    val actions = rememberNeedsYouActions(state)
    val haptics = rememberHaptics()
    val scope = rememberCoroutineScope()
    val agent = LocalAgentStore.current
    val task = card.task
    // `agent.canTakeOver(task)`.
    val omiCan = agent.canTakeOver(task)
    val isRunning = agent.runs[task.id]?.isActive == true
    val conversation = actions.conversations.source(task)

    /** The long-press "Omi takes over": the hand-over sheet (what Omi will do, then Start). */
    fun takeOver() {
        card.recommendation?.let { actions.decide(it, Recommendation.Decision.DoNow) }
        state.onHandOver(card.task)
    }

    /**
     * The magic button: Omi starts right away (no preview), the same start as the hand-over
     * sheet's primary button; the card shows the run in place.
     */
    fun start() {
        haptics.success()
        card.recommendation?.let {
            // Keeps the card where it is while the run lasts (its recommendation ranks it).
            state.keepRecommendation(task.id, it)
            actions.decide(it, Recommendation.Decision.DoNow)
        }
        actions.takeOver(task)
    }

    fun complete() {
        haptics.success()
        card.recommendation?.let { actions.decide(it, Recommendation.Decision.Complete) }
        scope.launch { actions.tasks.complete(card.group.ids) }
    }

    /** Off Home until tomorrow; the due date stays as it is. */
    fun later() {
        haptics.selection()
        card.recommendation?.let { actions.decide(it, Recommendation.Decision.Later) }
        actions.tasks.snooze(card.group.ids)
    }

    /** The swipe: Later, then "Moved to Later" with Undo at the bottom. */
    fun swipeLater() {
        later()
        state.laterUndo?.show(card.group.ids)
    }

    /** Cancelled on the backend: it disappears, and Omi learns this was no task. */
    fun notTask() {
        haptics.selection()
        card.recommendation?.let { actions.decide(it, Recommendation.Decision.Dismiss) }
        scope.launch { actions.tasks.markNotTask(card.group.ids) }
    }

    val conversationID = card.group.conversationIDs.firstOrNull()
    val menuItems = buildList {
        add(MenuItem(L("nativeMarkDone"), "checkmark.circle") { complete() })
        if (omiCan && !isRunning) add(MenuItem(L("nativeOmiTakesOver"), "sparkles") { takeOver() })
        if (card.snoozedUntil == null) {
            add(MenuItem(L("nativeForYouLater"), "clock") { later() })
        } else {
            add(MenuItem(L("nativeForYouBackToNeedsYou"), "arrow.uturn.up") { actions.tasks.unsnooze(card.group.ids) })
        }
        if (conversationID != null) add(MenuItem(L("openConversation"), "text.bubble") { state.onOpenConversation(conversationID) })
    }
    val menu = listOf(
        MenuSection(items = menuItems),
        MenuSection(items = listOf(MenuItem(L("nativeNotATask"), "xmark.circle", destructive = true) { notTask() })),
    )
    val visual = EntityVisual.forTask(task, conversation)
    TaskCardModern(
        avatar = visual.avatar(),
        avatarFallback = (if (visual is EntityVisual.Brand) conversation?.emoji?.let { AvatarContent.Emoji(it, conversation.category) } else null)
            ?: AvatarContent.Symbol(EntityVisual.categorySymbol(conversation?.category)),
        title = task.description,
        status = TaskCardWording.kicker(card),
        source = compactSource(card, actions),
        canTakeOver = omiCan,
        isRunning = isRunning,
        onMagic = { if (omiCan) start() else complete() },
        // The task's own screen; while Omi works, the hand-over sheet in progress.
        onTap = { if (isRunning) state.onOpenRun(task.id) else state.onOpenTask(task) },
        menu = { menu },
        onSwipeLater = if (card.snoozedUntil == null) ({ swipeLater() }) else null,
    )
    // Debug launches (`--es omiTakeOverFirst demo|real`) start Omi on the first card it can take.
    DebugTakeOver(card, omiCan, isRunning) { demo -> if (demo) agent.showDemoRun(task) else start() }
}

private fun EntityVisual.avatar(): AvatarContent = when (this) {
    is EntityVisual.Brand -> AvatarContent.Logo(domain, bundled)
    is EntityVisual.Person -> AvatarContent.Monogram(name)
    is EntityVisual.Emoji -> AvatarContent.Emoji(emoji, category)
    is EntityVisual.Symbol -> AvatarContent.Symbol(systemName)
}

/** "Pricing sync · Wed", or "Pricing sync +1" for a merged card (no "From:"). */
@Composable
private fun compactSource(card: TaskConsolidation.Card, actions: NeedsYouActions): String? {
    val context = LocalContext.current
    val ids = card.group.conversationIDs
    val sources = card.group.all.mapNotNull { actions.conversations.source(it) }
    val first = ids.firstNotNullOfOrNull { id -> sources.firstOrNull { it.id == id } }
    if (first != null) {
        val title = first.displayTitle(context)
        return if (ids.size > 1) "$title +${ids.size - 1}" else "$title · ${Formatting.weekday(first.createdAt)}"
    }
    return card.recommendation?.let { TaskCardWording.origin(it) }
}

/** Debug builds only (`DebugLaunch` is empty otherwise): Omi on the first eligible card, once. */
@Composable
private fun DebugTakeOver(card: TaskConsolidation.Card, omiCan: Boolean, isRunning: Boolean, start: (Boolean) -> Unit) {
    val mode = DebugLaunch.string("omiTakeOverFirst") ?: return
    LaunchedEffect(card.id) {
        if (!omiCan || isRunning || DebugTakeOverOnce.used) return@LaunchedEffect
        DebugTakeOverOnce.used = true
        start(mode == "demo")
    }
}

private object DebugTakeOverOnce {
    var used = false
}

/** The words on a task card. */
object TaskCardWording {
    @Composable
    fun kicker(card: TaskConsolidation.Card): DecisionCard.Kicker {
        if (card.snoozedUntil != null) return DecisionCard.Kicker("clock", L("nativeForYouLater"), DS.Palette.inkSecondary)
        return when (val kicker = card.kicker) {
            TaskConsolidation.Card.Kicker.Overdue -> DecisionCard.Kicker("exclamationmark.circle", L("nativeOverdue"), DS.Palette.live)
            TaskConsolidation.Card.Kicker.DueToday -> DecisionCard.Kicker("calendar", L("nativeForYouDueToday"), DS.Palette.warning)
            is TaskConsolidation.Card.Kicker.DueSoon ->
                DecisionCard.Kicker("calendar", L("nativeForYouDueOn", day(kicker.date)), DS.Palette.inkSecondary)
            TaskConsolidation.Card.Kicker.Waiting -> DecisionCard.Kicker("hourglass", L("nativeForYouSomeoneWaits"), DS.Palette.warning)
            TaskConsolidation.Card.Kicker.Suggestion -> DecisionCard.Kicker("sparkles", L("nativeForYouSuggestion"), DS.Palette.agent)
        }
    }

    /** "tomorrow" or "Sat" after "Due". */
    @Composable
    private fun day(date: Instant, now: Instant = Instant.now(), zone: ZoneId = ZoneId.systemDefault()): String {
        val tomorrow = now.atZone(zone).toLocalDate().plusDays(1)
        if (date.atZone(zone).toLocalDate() == tomorrow) return L("nativeTomorrow").lowercase()
        return Formatting.weekday(date)
    }

    /** Where a backend suggestion comes from when no conversation says it. */
    @Composable
    fun origin(recommendation: Recommendation): String? {
        val parts = buildList {
            when (val origin = recommendation.origin) {
                RecommendationOrigin.AddedByYou -> add(L("nativeForYouAddedByYou"))
                RecommendationOrigin.WaitingOnYou -> add(L("nativeForYouWaitingOnYou"))
                is RecommendationOrigin.Text -> add(origin.text)
                null -> Unit
            }
            recommendation.distinctGoalLabel?.let(::add)
        }
        return if (parts.isEmpty()) null else parts.joinToString(" · ")
    }
}
