package com.friend.ios.features.conversations

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.DailySummary
import com.friend.ios.core.models.Memory
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.OmiNavBar
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.SkeletonBlock
import com.friend.ios.design.TextStyles
import com.friend.ios.design.omiSurface
import com.friend.ios.design.plainButton
import com.friend.ios.design.pressable
import com.friend.ios.features.components.ConversationRow
import com.friend.ios.features.components.ConversationRowStyle
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.features.components.Formatting
import com.friend.ios.features.components.TaskRow
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.ConversationsStore
import com.friend.ios.service.stores.SearchStore
import kotlinx.coroutines.launch

/**
 * Port of `SearchScreen.swift`: Search (the magnifying glass on Home): recent searches and every
 * conversation by day until something is typed or filtered, then one list of matching
 * conversations, recaps, tasks and memories. Loaded matches show at once; the backend adds
 * conversations it finds by what was said. Filters (starred, a person, a date range) narrow it to
 * conversations. Compose: the pushed page draws its own bar (the filter menu is its toolbar item)
 * and the `.searchable` field under it.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SearchScreen(
    store: SearchStore,
    onBack: () -> Unit,
    onOpenConversation: (Conversation) -> Unit,
    onOpenRecap: ((DailySummary) -> Unit)? = null,
) {
    val search = store
    val conversations = LocalConversationsStore.current
    val tasks = LocalTasksStore.current
    val settings = LocalSettingsStore.current
    val scope = rememberCoroutineScope()
    var query by rememberSaveable { mutableStateOf(DebugLaunch.string("omiSearchQuery") ?: "") }
    var pickingDates by remember { mutableStateOf(false) }
    var refreshing by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { search.loadSources() }
    LaunchedEffect(Unit) { if (query.isNotEmpty()) search.update(query) }
    LaunchedEffect(Unit) { settings.loadPeople() }
    // Opening a result (or leaving) keeps the typed query among the recent searches.
    val current by rememberUpdatedState(search)
    DisposableEffect(Unit) { onDispose { current.remember() } }

    val untitled = L("untitledConversation")
    /** The loaded conversation's title, "Untitled" when it has none; null when it is not loaded. */
    fun titleOf(id: String): String? = conversations.conversations.firstOrNull { it.id == id }?.let { it.title.ifEmpty { untitled } }

    fun open(conversationID: String) {
        search.remember()
        scope.launch { conversations.conversation(conversationID)?.let(onOpenConversation) }
    }

    Column(Modifier.fillMaxSize()) {
        OmiNavBar(L("search"), onBack, Modifier.statusBarsPadding()) {
            SearchFilterMenu(search) { pickingDates = true }
        }
        SearchField(query, onChange = {
            query = it
            search.update(it)
        }, onSubmit = { search.remember() })
        Box(Modifier.weight(1f)) {
            PullToRefreshBox(
                isRefreshing = refreshing,
                onRefresh = {
                    scope.launch {
                        refreshing = true
                        conversations.load()
                        refreshing = false
                    }
                },
                modifier = Modifier.fillMaxSize(),
            ) {
                LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = DS.Spacing.section)) {
                    if (search.filter.isActive) item(key = "filters") { ActiveFilters(search) }
                    if (search.isActive) {
                        results(search, onOpenConversation, onOpenRecap, ::titleOf, ::open) { id, done -> scope.launch { tasks.setCompleted(id, done) } }
                    } else {
                        idle(search, conversations, onRecent = {
                            query = it
                            search.update(it)
                            search.remember(it)
                        }, onOpenConversation = onOpenConversation)
                    }
                    if (conversations.isLoadingMore && !search.isActive) {
                        item(key = "more") { Box(Modifier.fillMaxWidth().padding(DS.Spacing.md), contentAlignment = Alignment.Center) { OmiProgress() } }
                    }
                }
                EmptyState(search, conversations)
            }
        }
    }
    if (pickingDates) DateRangeSheet(search, onDismiss = { pickingDates = false })
}

/** The `.searchable` field under the bar: a capsule with the magnifier, search on the keyboard. */
@Composable
private fun SearchField(text: String, onChange: (String) -> Unit, onSubmit: () -> Unit) {
    val focus = LocalFocusManager.current
    Row(
        Modifier
            .padding(horizontal = DS.Spacing.gutter)
            .padding(bottom = DS.Spacing.sm)
            .fillMaxWidth()
            .heightIn(min = DS.Size.searchField)
            .omiSurface(CircleShape)
            .padding(horizontal = DS.Spacing.lg),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        SFImage("magnifyingglass", size = 15.sp, tint = DS.Palette.inkTertiary)
        Box(Modifier.weight(1f)) {
            if (text.isEmpty()) Text(L("search"), style = DS.Typography.body, color = DS.Palette.inkTertiary, maxLines = 1)
            BasicTextField(
                value = text,
                onValueChange = onChange,
                singleLine = true,
                textStyle = DS.Typography.body.copy(color = DS.Palette.ink),
                cursorBrush = SolidColor(DS.Palette.agent),
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false, imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = {
                    onSubmit()
                    focus.clearFocus()
                }),
                modifier = Modifier.fillMaxWidth(),
            )
        }
        if (text.isNotEmpty()) {
            SFImage("xmark.circle.fill", Modifier.plainButton { onChange("") }, size = 15.sp, tint = DS.Palette.inkTertiary, contentDescription = L("nativeClearSearch"))
        }
    }
}

/** A small gray label over each group of results (`Section(title)` in the grouped list). */
@Composable
private fun SectionTitle(title: String, trailing: @Composable () -> Unit = {}) {
    HStack(Modifier.fillMaxWidth().padding(start = DS.Spacing.gutter, end = DS.Spacing.gutter, top = DS.Spacing.lg, bottom = DS.Spacing.xs)) {
        Text(title, style = DS.Typography.sectionLabel, color = DS.Palette.inkSecondary)
        Spacer(Modifier.weight(1f))
        trailing()
    }
}

/** A conversation row that opens it, text-first as on Home. */
@Composable
private fun ConversationLink(conversation: Conversation, onOpen: (Conversation) -> Unit) {
    ConversationRow(
        conversation,
        Modifier
            .pressable { onOpen(conversation) }
            .padding(horizontal = DS.Spacing.gutter, vertical = DS.Spacing.sm + 1.dp),
        style = ConversationRowStyle.Plain,
    )
}

private fun LazyListScope.idle(
    search: SearchStore,
    conversations: ConversationsStore,
    onRecent: (String) -> Unit,
    onOpenConversation: (Conversation) -> Unit,
) {
    if (search.recents.isNotEmpty()) {
        item(key = "recents.header") {
            SectionTitle(L("recent")) {
                Text(
                    L("nativeClearRecents"),
                    style = DS.Typography.caption,
                    color = DS.Palette.agent,
                    modifier = Modifier.plainButton { search.clearRecents() },
                )
            }
        }
        items(search.recents, key = { "recent.$it" }) { recent ->
            val delete = L("delete")
            ContextMenuBox(
                sections = { listOf(MenuSection(items = listOf(MenuItem(delete, "trash", destructive = true) { search.removeRecent(recent) }))) },
                modifier = Modifier.fillMaxWidth(),
                onTap = { onRecent(recent) },
            ) {
                HStack(Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.gutter, vertical = DS.Spacing.md), spacing = DS.Spacing.md) {
                    SFImage("clock.arrow.circlepath", tint = DS.Palette.agent)
                    Text(recent, style = DS.Typography.body, color = DS.Palette.ink, maxLines = 1)
                }
            }
        }
    }
    when {
        conversations.phase == ConversationsStore.Phase.Loading && conversations.conversations.isEmpty() ->
            items(4) { SkeletonBlock(Modifier.padding(horizontal = DS.Spacing.gutter, vertical = DS.Spacing.sm)) }
        conversations.phase is ConversationsStore.Phase.Failed && conversations.conversations.isEmpty() ->
            item(key = "failed") { OmiEmptyState(L("nativeCouldNotLoad"), "wifi.exclamationmark", Modifier.padding(top = 72.dp)) }
        else -> conversations.sections.forEach { section ->
            item(key = "day.${section.day}") { SectionTitle(Formatting.dayTitle(section.day)) }
            items(section.conversations, key = { "c.${it.id}" }) { conversation ->
                ConversationLink(conversation, onOpenConversation)
                if (conversation.id == conversations.conversations.lastOrNull()?.id) {
                    LaunchedEffect(conversation.id) { conversations.loadMore() }
                }
            }
        }
    }
}

@Composable
private fun ActiveFilters(search: SearchStore) {
    val range = DateRangeSheet.title(search.filter)
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = DS.Spacing.gutter, vertical = DS.Spacing.sm),
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        if (search.filter.starred) FilterChip(L("starred"), "star.fill") { search.filter = search.filter.copy(starred = false) }
        search.filter.person?.let { person -> FilterChip(person.name, "person.fill") { search.filter = search.filter.copy(person = null) } }
        if (range != null) FilterChip(range, "calendar") { search.filter = search.filter.copy(start = null, end = null) }
    }
}

private fun LazyListScope.results(
    search: SearchStore,
    onOpenConversation: (Conversation) -> Unit,
    onOpenRecap: ((DailySummary) -> Unit)?,
    titleOf: (String) -> String?,
    open: (String) -> Unit,
    onToggle: (String, Boolean) -> Unit,
) {
    val conversations = search.conversations
    if (conversations.isNotEmpty() || search.phase == SearchStore.Phase.Searching) {
        item(key = "results.conversations") { SectionTitle(L("conversations")) }
        items(conversations, key = { "r.${it.id}" }) { ConversationLink(it, onOpenConversation) }
        if (search.phase == SearchStore.Phase.Searching) {
            item(key = "searching") {
                HStack(Modifier.padding(horizontal = DS.Spacing.gutter, vertical = DS.Spacing.sm), spacing = DS.Spacing.md) {
                    OmiProgress(Modifier.width(18.dp))
                    Text(L("nativeSearching"), style = DS.Typography.callout, color = DS.Palette.inkSecondary)
                }
            }
        }
    }
    if (search.recaps.isNotEmpty()) {
        item(key = "results.recaps") { SectionTitle(L("recaps")) }
        items(search.recaps, key = { "recap.${it.id}" }) { recap ->
            HStack(
                Modifier
                    .fillMaxWidth()
                    .pressable(enabled = onOpenRecap != null) {
                        search.remember()
                        onOpenRecap?.invoke(recap)
                    }
                    .padding(horizontal = DS.Spacing.gutter, vertical = DS.Spacing.sm),
                spacing = DS.Spacing.md,
            ) {
                Box(Modifier.width(30.dp), contentAlignment = Alignment.Center) { Text(recap.emoji ?: "📅", style = TextStyles.system(22)) }
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(recap.headline, style = DS.Typography.cardTitle, color = DS.Palette.ink, maxLines = 2)
                    Text(recap.day?.let { Formatting.dayTitle(it) } ?: recap.date, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                }
            }
        }
    }
    val matchingTasks = search.tasks
    if (matchingTasks.isNotEmpty()) {
        item(key = "results.tasks") { SectionTitle(L("tasks")) }
        items(matchingTasks, key = { "t.${it.id}" }) { task ->
            Box(Modifier.fillMaxWidth().plainButton { task.conversationID?.let(open) }.padding(horizontal = DS.Spacing.gutter)) {
                TaskRow(
                    task,
                    source = task.conversationID?.let(titleOf),
                    onToggle = { onToggle(task.id, !task.isCompleted) },
                )
            }
        }
    }
    val memories = search.memories
    if (memories.isNotEmpty()) {
        item(key = "results.memories") { SectionTitle(L("memories")) }
        items(memories, key = { "m.${it.id}" }) { memory ->
            val id = memory.conversationID
            MemoryResult(
                memory,
                id?.let(titleOf),
                Modifier
                    .then(if (id != null) Modifier.plainButton { open(id) } else Modifier)
                    .padding(horizontal = DS.Spacing.gutter, vertical = DS.Spacing.sm),
            )
        }
    }
}

@Composable
private fun EmptyState(search: SearchStore, conversations: ConversationsStore) {
    val modifier = Modifier.fillMaxSize()
    when {
        !search.isActive && conversations.phase == ConversationsStore.Phase.Loaded && conversations.conversations.isEmpty() ->
            Box(modifier, contentAlignment = Alignment.Center) {
                OmiEmptyState(L("nativeNoConversationsYet"), "waveform", message = L("nativeNoConversationsToday"))
            }
        search.isActive && search.phase == SearchStore.Phase.Failed && !search.hasResults ->
            Box(modifier, contentAlignment = Alignment.Center) { OmiEmptyState(L("nativeCouldNotLoad"), "wifi.exclamationmark") }
        search.isActive && search.phase == SearchStore.Phase.Done && !search.hasResults ->
            Box(modifier, contentAlignment = Alignment.Center) { OmiEmptyState(L("noResultsFound"), "magnifyingglass") }
    }
}

/** A matching memory: its text, and the conversation it came from when that is loaded. */
@Composable
private fun MemoryResult(memory: Memory, source: String?, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(vertical = DS.Spacing.xxs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        Text(memory.content, style = DS.Typography.callout, color = DS.Palette.ink)
        Text(
            source?.let { L("nativeFromConversation", it) } ?: memory.category.replaceFirstChar { it.titlecase() },
            style = DS.Typography.caption,
            color = DS.Palette.inkSecondary,
            maxLines = 1,
        )
    }
}
