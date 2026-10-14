package com.friend.ios.features.today

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationFilter
import com.friend.ios.core.models.DailySummary
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.DSHaptics
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.OmiPendantIllustration
import com.friend.ios.design.SFImage
import com.friend.ios.design.SkeletonBlock
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.ConversationRow
import com.friend.ios.features.components.ConversationRowStyle
import com.friend.ios.features.components.Formatting
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.stores.ConversationsStore
import kotlinx.coroutines.launch
import java.time.LocalDate

/**
 * Port of `ConversationList.swift`: Home's conversations by day, each day led by its recap: quiet
 * rows, no card per row. The long-press menu has star, move, select, reprocess and delete (with
 * undo). One quiet filter button beside the first day: all, starred, a folder.
 * Compose: the list is rows of Home's `LazyColumn`; [ConversationListState] holds the screen's
 * `@State`, [ConversationListSheets] its sheets.
 */
@Stable
class ConversationListState {
    /** The conversations a "Move to folder..." sheet is for (`MoveRequest`). */
    var moving: List<String>? by mutableStateOf(null)
    var showsFolders by mutableStateOf(false)
    var showsMap by mutableStateOf(false)
    /** The one-day page (`ConversationListExtras.swift`). */
    var day: DayRequest? by mutableStateOf(null)
}

@Composable
fun rememberConversationListState(): ConversationListState = remember { ConversationListState() }

/** Where a row's text starts (after the emoji tile): separators begin there, as in iOS lists. */
val ConversationListTextInset = DS.Size.tile + DS.Spacing.md

fun LazyListScope.conversationList(
    conversations: ConversationsStore,
    state: ConversationListState,
    selection: Set<String>?,
    onSelectionChange: (Set<String>?) -> Unit,
    onOpenConversation: (Conversation) -> Unit,
    onOpenRecap: (DailySummary) -> Unit,
) {
    val phase = conversations.phase
    when {
        phase == ConversationsStore.Phase.Loading && conversations.conversations.isEmpty() ->
            items(4) { SkeletonBlock(Modifier.padding(top = DS.Spacing.sm), height = 68.dp) }
        conversations.conversations.isEmpty() && phase is ConversationsStore.Phase.Failed -> item(key = "conversations.failure") {
            val scope = rememberCoroutineScope()
            OmiEmptyState(
                L("nativeCouldNotLoadConversations"), "wifi.exclamationmark", Modifier.padding(top = 72.dp),
                message = phase.message, actionTitle = L("tryAgain"),
            ) { scope.launch { conversations.load() } }
        }
        conversations.conversations.isEmpty() && conversations.filter == ConversationFilter.All -> item(key = "conversations.empty") { Empty() }
        conversations.sections.isEmpty() -> item(key = "conversations.nothing") {
            Column {
                Header(null, state, onSelectionChange)
                Text(
                    if (conversations.isLoadingFiltered) L("loading") else L("nativeNothingHere"),
                    style = DS.Typography.callout,
                    color = DS.Palette.inkSecondary,
                    modifier = Modifier.padding(top = DS.Spacing.md),
                )
            }
        }
        else -> {
            val visible = conversations.visible
            conversations.sections.forEachIndexed { index, section ->
                item(key = "day.${section.day}") {
                    if (index == 0) Header(section.day, state, onSelectionChange) else DayTitle(section.day)
                }
                // Text-first, as in the ChatGPT app: the recap first, then the conversations.
                if (selection == null) {
                    val slot = conversations.recapSlot(section.day)
                    if (slot != null) item(key = "recap.${section.day}") { RecapRow(slot, onOpenRecap) }
                }
                items(section.conversations, key = { it.id }) { conversation ->
                    Row(conversation, selection, onSelectionChange, state, onOpenConversation, isLast = conversation.id == visible.lastOrNull()?.id)
                }
            }
        }
    }
}

/** The sheets and full-screen pages the list opens. */
@Composable
fun ConversationListSheets(state: ConversationListState, onSelectionChange: (Set<String>?) -> Unit, onOpenConversation: (Conversation) -> Unit) {
    val conversations = LocalConversationsStore.current
    LaunchedEffect(Unit) { conversations.loadFolders() }
    state.moving?.let { ids ->
        com.friend.ios.features.components.MoveToFolderSheet(ids, onDismiss = { state.moving = null }, onMoved = { onSelectionChange(null) })
    }
    if (state.showsFolders) com.friend.ios.features.components.FoldersSheet(onDismiss = { state.showsFolders = false })
    LaunchedEffect(Unit) { DayConversationsScreen.requestForDebugging()?.let { state.day = it } }
    state.day?.let { request ->
        val store = androidx.compose.runtime.remember(request) { conversations.makeDayStore(request.day) }
        DayConversationsScreen(store, request.picksDay, onOpenConversation = { conversation ->
            state.day = null
            onOpenConversation(conversation)
        }, onDismiss = { state.day = null })
    }
    if (state.showsMap) {
        ConversationMapScreen(conversations.conversations, onOpenConversation = { conversation ->
            state.showsMap = false
            onOpenConversation(conversation)
        }, onDismiss = { state.showsMap = false })
    }
}

// Rows

@Composable
private fun Row(
    conversation: Conversation,
    selection: Set<String>?,
    onSelectionChange: (Set<String>?) -> Unit,
    state: ConversationListState,
    onOpenConversation: (Conversation) -> Unit,
    isLast: Boolean,
) {
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    fun toggle() {
        haptics.selection()
        val current = selection ?: return
        onSelectionChange(if (conversation.id in current) current - conversation.id else current + conversation.id)
    }
    val menu = rowMenu(conversation, state, onSelectionChange)
    Box {
        // Star and delete live in the long-press menu: a horizontal row swipe would fight the
        // sideways swipe between Home, Tasks and Memories.
        ContextMenuBox(
            sections = { if (selection == null) menu else emptyList() },
            onTap = { if (selection != null) toggle() else onOpenConversation(conversation) },
        ) {
            ConversationRow(
                conversation,
                Modifier.padding(vertical = DS.Spacing.sm + 1.dp),
                isSelected = selection?.contains(conversation.id),
                style = ConversationRowStyle.Plain,
            )
        }
        // Behind the paywall: frosted, and a tap opens the plans.
        if (conversation.isLocked && selection == null) LockedRowCover(Modifier.matchParentSize())
        if (conversation.summaryFailed && selection == null) {
            Text(
                L("retry"),
                style = DS.Typography.callout.semibold(),
                color = DS.Palette.ink,
                modifier = Modifier
                    .align(Alignment.CenterEnd)
                    .plainButton { scope.launch { conversations.reprocess(conversation.id) } }
                    .background(DS.Palette.fill, CircleShape)
                    .padding(horizontal = DS.Spacing.md, vertical = DS.Spacing.xs + 2.dp),
            )
        }
    }
    if (isLast) LaunchedEffect(conversation.id) { conversations.loadMore() }
}

@Composable
private fun rowMenu(conversation: Conversation, state: ConversationListState, onSelectionChange: (Set<String>?) -> Unit): List<MenuSection> {
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val items = buildList {
        add(
            if (conversation.isStarred) MenuItem(L("unstarConversation"), "star.slash") { scope.launch { conversations.setStarred(conversation.id, false) } }
            else MenuItem(L("starConversation"), "star") { scope.launch { conversations.setStarred(conversation.id, true) } },
        )
        add(MenuItem(L("moveToFolder"), "folder") { state.moving = listOf(conversation.id) })
        add(MenuItem(L("selectOption"), "checkmark.circle") { onSelectionChange(setOf(conversation.id)) })
        if (conversation.summaryFailed || conversation.status == Conversation.Status.Completed) {
            add(MenuItem(L("reprocessConversation"), "arrow.clockwise") { scope.launch { conversations.reprocess(conversation.id) } })
        }
    }
    return listOf(
        MenuSection(items = items),
        MenuSection(
            items = listOf(
                MenuItem(L("delete"), "trash", destructive = true) {
                    haptics.tap(DSHaptics.Style.Medium)
                    conversations.deleteWithUndo(listOf(conversation.id))
                },
            ),
        ),
    )
}

// Header and filter

/** The first day's title with the filter beside it (or just the filter when nothing matches). */
@Composable
private fun Header(day: LocalDate?, state: ConversationListState, onSelectionChange: (Set<String>?) -> Unit) {
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    HStack(Modifier.fillMaxWidth().padding(top = DS.Spacing.md, bottom = DS.Spacing.xxs), spacing = DS.Spacing.sm) {
        if (day != null) Text(Formatting.dayTitle(day), style = DS.Typography.sectionLabel, color = DS.Palette.inkSecondary)
        Spacer(Modifier.weight(1f))
        if (conversations.filter != ConversationFilter.All) {
            val name = filterName()
            val clear = L("nativeClearFilter", name)
            HStack(
                Modifier
                    .plainButton { scope.launch { conversations.setFilter(ConversationFilter.All) } }
                    .clearAndSetSemantics {
                        contentDescription = clear
                        role = Role.Button
                        onClick { scope.launch { conversations.setFilter(ConversationFilter.All) }; true }
                    }
                    .background(DS.Palette.agentSoft, CircleShape)
                    .padding(horizontal = DS.Spacing.md, vertical = DS.Spacing.xs + 2.dp),
                spacing = DS.Spacing.xs,
            ) {
                Text(name, style = DS.Typography.caption.semibold(), color = DS.Palette.agent)
                SFImage("xmark", size = 10.sp, weight = FontWeight.Bold, tint = DS.Palette.agent)
            }
        }
        FilterMenu(state, onSelectionChange)
    }
}

@Composable
private fun DayTitle(day: LocalDate) {
    Text(
        Formatting.dayTitle(day),
        style = DS.Typography.sectionLabel,
        color = DS.Palette.inkSecondary,
        modifier = Modifier.padding(top = DS.Spacing.lg, bottom = DS.Spacing.xxs),
    )
}

@Composable
private fun FilterMenu(state: ConversationListState, onSelectionChange: (Set<String>?) -> Unit) {
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    fun filterItem(title: String, systemImage: String, filter: ConversationFilter) =
        MenuItem(title, if (conversations.filter == filter) "checkmark" else systemImage) { scope.launch { conversations.setFilter(filter) } }
    val sections = listOf(
        MenuSection(items = listOf(filterItem(L("nativeAllConversations"), "tray.full", ConversationFilter.All), filterItem(L("starred"), "star", ConversationFilter.Starred))),
        MenuSection(
            header = L("nativeFolders"),
            items = conversations.folders.map { filterItem(it.name, "folder", ConversationFilter.Folder(it.id)) } +
                MenuItem(L("nativeEditFolders"), "folder.badge.gearshape") { state.showsFolders = true },
        ),
    ) + displayOptionsMenu() + MenuSection(
        items = listOf(
            MenuItem(L("filterByDate"), "calendar") { state.day = DayRequest(LocalDate.now(), picksDay = true) },
            MenuItem(L("conversationMap"), "map") { state.showsMap = true },
            MenuItem(L("selectOption"), "checkmark.circle") { onSelectionChange(emptySet()) },
        ),
    )
    OmiMenu(sections, contentDescription = L("nativeFilterConversations")) {
        Box(Modifier.size(36.dp), contentAlignment = Alignment.Center) {
            SFImage(
                "line.3.horizontal.decrease",
                size = 16.sp,
                tint = if (conversations.filter == ConversationFilter.All) DS.Palette.inkSecondary else DS.Palette.agent,
            )
        }
    }
}

@Composable
private fun filterName(): String {
    val conversations = LocalConversationsStore.current
    return when (val filter = conversations.filter) {
        ConversationFilter.All -> L("nativeAllConversations")
        ConversationFilter.Starred -> L("starred")
        is ConversationFilter.Folder -> conversations.folder(filter.id)?.name ?: L("nativeFolders")
    }
}

// Empty and failure

/** Nothing recorded yet: the pendant as a hero, a serif line, one calm sentence. */
@Composable
private fun Empty() {
    Column(
        Modifier.fillMaxWidth().padding(top = DS.Spacing.section),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.md),
    ) {
        OmiPendantIllustration(132.dp, Modifier.padding(bottom = DS.Spacing.lg))
        Text(L("nativeNoConversationsYet"), style = DS.Typography.title, color = DS.Palette.ink, textAlign = TextAlign.Center)
        Text(
            L("nativeNoConversationsToday"),
            style = DS.Typography.callout,
            color = DS.Palette.inkSecondary,
            textAlign = TextAlign.Center,
            modifier = Modifier.widthIn(max = 300.dp),
        )
    }
}
