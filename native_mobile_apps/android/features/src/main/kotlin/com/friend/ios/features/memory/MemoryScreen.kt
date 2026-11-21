package com.friend.ios.features.memory

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Memory
import com.friend.ios.design.CircleIconButton
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiCircleIcon
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.OmiHairline
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.OmiSearchField
import com.friend.ios.design.SkeletonBlock
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.features.components.OmiToast
import com.friend.ios.design.Detent
import com.friend.ios.design.OmiSheet
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.stores.loadReviewQueue
import com.friend.ios.service.stores.reviewCount
import com.friend.ios.service.LocalMemoriesStore
import com.friend.ios.service.stores.MemoriesStore
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Port of `MemoryScreen.swift`: what Omi knows about me, search on top, kind chips, one row per
 * memory. The header menu holds the memory graph and "make all private/public"; a delete can be
 * undone for a few seconds. [bottomInset] keeps the last rows clear of the Omi bar
 * (`.safeAreaPadding(.bottom, OmiBottomBar.height)` on iOS).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MemoryScreen(
    onOpenConversation: (String) -> Unit,
    modifier: Modifier = Modifier,
    bottomInset: androidx.compose.ui.unit.Dp = 0.dp,
    /** Pushes `MemoryGraphScreen` (`.navigationDestination(isPresented: $showsGraph)`); the shell owns the stack. */
    onOpenGraph: () -> Unit = {},
) {
    val store = LocalMemoriesStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var query by rememberSaveable { mutableStateOf("") }
    var category by rememberSaveable { mutableStateOf<String?>(null) }
    var visibilityResult by remember { mutableStateOf<String?>(null) }
    var refreshing by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<Memory?>(null) }
    var showsNewMemory by remember { mutableStateOf(DebugLaunch.flag("omiNewMemory")) }
    var reviewing by remember { mutableStateOf(DebugLaunch.flag("omiMemoryReview")) }
    val conversations = LocalConversationsStore.current
    val untitled = L("untitledConversation")
    /** The title of the conversation a memory came from, when it is loaded. */
    val source: (Memory) -> String? = { memory ->
        memory.conversationID?.let { id -> conversations.conversations.firstOrNull { it.id == id }?.let { it.title.ifEmpty { untitled } } }
    }

    LaunchedEffect(Unit) { if (store.phase == MemoriesStore.Phase.Idle) store.load() }
    LaunchedEffect(Unit) { store.loadReviewQueue() }
    LaunchedEffect(Unit) { if (DebugLaunch.flag("omiMemoryGraph")) onOpenGraph() }
    DisposableEffect(Unit) { onDispose { scope.launch { store.commitPendingDeletion() } } }

    val allPrivate = L("nativeAllMemoriesPrivate")
    val allPublic = L("nativeAllMemoriesPublic")
    val someFailed = L("nativeSomeMemoriesNotUpdated")
    fun setAll(visibility: Memory.Visibility) = scope.launch {
        val allTook = store.setAllVisibility(visibility)
        visibilityResult = if (!allTook) someFailed else if (visibility == Memory.Visibility.Private) allPrivate else allPublic
    }

    Box(modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            // The search row stays put above the list, at the same place as on Tasks.
            HStack(Modifier.padding(horizontal = DS.Spacing.gutter).padding(bottom = DS.Spacing.xs), spacing = DS.Spacing.sm) {
                OmiSearchField(L("searchMemories"), query, { query = it }, L("cancel"), Modifier.weight(1f))
                OmiMenu(
                    listOf(
                        MenuSection(items = listOf(MenuItem(L("memoryGraph"), "point.3.connected.trianglepath.dotted") { onOpenGraph() })),
                        MenuSection(
                            header = L("nativeMemoryVisibilityCounts", "${store.publicCount}", "${store.privateCount}"),
                            items = listOf(
                                MenuItem(L("makeAllPrivate"), "lock") { setAll(Memory.Visibility.Private) },
                                MenuItem(L("makeAllPublic"), "globe") { setAll(Memory.Visibility.Public) },
                            ),
                        ),
                    ),
                    contentDescription = L("moreOptions"),
                ) { OmiCircleIcon("ellipsis") }
                CircleIconButton("plus", contentDescription = L("createMemoryTooltip")) { showsNewMemory = true }
            }
            PullToRefreshBox(
                isRefreshing = refreshing,
                onRefresh = {
                    scope.launch {
                        refreshing = true
                        store.load()
                        refreshing = false
                    }
                },
                modifier = Modifier.weight(1f),
            ) {
                LazyColumn(
                    Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = DS.Spacing.gutter, end = DS.Spacing.gutter, top = DS.Spacing.sm, bottom = DS.Spacing.section + bottomInset),
                ) {
                    // New memories wait behind one entry instead of asking on every row.
                    val reviewCount = store.reviewCount
                    if (reviewCount > 0 && query.isEmpty()) {
                        item(key = "review") {
                            MemoryReviewEntry(reviewCount, Modifier.padding(bottom = DS.Spacing.md)) { reviewing = true }
                        }
                    }
                    if (store.memories.isNotEmpty()) {
                        item(key = "chips") {
                            Chips(store, query, category, Modifier.padding(bottom = DS.Spacing.sm)) { category = it }
                        }
                    }
                    content(store, query, category, onEdit = { editing = it }, onNew = { showsNewMemory = true }, onOpenConversation = onOpenConversation)
                }
            }
        }
        editing?.let { memory ->
            OmiSheet(onDismiss = { editing = null }, detents = setOf(Detent.Medium, Detent.Large)) {
                EditMemorySheet(memory, onDismiss = { editing = null })
            }
        }
        if (showsNewMemory) {
            OmiSheet(onDismiss = { showsNewMemory = false }, detents = setOf(Detent.Medium)) {
                NewMemorySheet(onDismiss = { showsNewMemory = false })
            }
        }
        if (reviewing) MemoryReviewSheet(sources = source, onDismiss = { reviewing = false })
        // Toasts: undo a delete, or the result of "make all private/public".
        Box(Modifier.align(Alignment.BottomCenter).padding(bottom = DS.Spacing.sm + bottomInset)) {
            AnimatedVisibility(
                visible = store.pendingDeletion != null,
                enter = slideInVertically { it } + fadeIn(),
                exit = slideOutVertically { it } + fadeOut(),
            ) {
                OmiToast(L("memoryDeleted"), "trash", actionTitle = L("undo")) {
                    haptics.tap()
                    store.undoDelete()
                }
            }
            val result = visibilityResult
            AnimatedVisibility(visible = store.pendingDeletion == null && result != null, enter = slideInVertically { it } + fadeIn(), exit = slideOutVertically { it } + fadeOut()) {
                OmiToast(result.orEmpty(), "lock")
            }
            LaunchedEffect(result) {
                if (result != null) {
                    delay(3_000)
                    visibilityResult = null
                }
            }
        }
    }
}

@Composable
private fun Chips(store: MemoriesStore, query: String, category: String?, modifier: Modifier, onSelect: (String?) -> Unit) {
    HStack(modifier.horizontalScroll(rememberScrollState()).padding(bottom = DS.Spacing.xs), spacing = DS.Spacing.sm) {
        Chip(L("filterAll"), selected = category == null, count = store.visible(query).size) { onSelect(null) }
        // Empty kinds ("Manual 0") are noise; a chosen one stays so it can be cleared.
        store.filterChips(query).filter { it.second > 0 || it.first == category }.forEach { (value, count) ->
            Chip(MemoryKind.title(value), selected = category == value, count = count) { onSelect(value) }
        }
    }
}

@Composable
private fun Chip(title: String, selected: Boolean, count: Int, onClick: () -> Unit) {
    val style = DS.Typography.label.copy(letterSpacing = DS.Tracking.label.sp)
    HStack(
        Modifier
            .plainButton(onClick = onClick)
            .heightIn(min = 32.dp)
            .background(if (selected) DS.Palette.accent else DS.Palette.card, CircleShape)
            .then(if (selected) Modifier else Modifier.border(1.dp, DS.Palette.cardStroke, CircleShape))
            .padding(horizontal = DS.Spacing.md),
        spacing = DS.Spacing.xs,
    ) {
        Text(title, style = style, color = if (selected) DS.Palette.onAccent else DS.Palette.ink)
        Text("$count", style = style, color = if (selected) DS.Palette.onAccent.copy(alpha = 0.6f) else DS.Palette.inkTertiary)
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.content(
    store: MemoriesStore,
    query: String,
    category: String?,
    onEdit: (Memory) -> Unit,
    onNew: () -> Unit,
    onOpenConversation: (String) -> Unit,
) {
    when {
        store.phase == MemoriesStore.Phase.Loading && store.memories.isEmpty() ->
            items(5) { SkeletonBlock(Modifier.padding(bottom = DS.Spacing.sm), height = 64.dp) }
        store.memories.isEmpty() && store.phase == MemoriesStore.Phase.Loaded -> item(key = "empty") {
            OmiEmptyState(
                L("noMemoriesYet"),
                "brain.head.profile",
                Modifier.padding(top = 72.dp),
                message = L("createYourFirstMemory"),
                actionTitle = L("createMemoryTooltip"),
                action = onNew,
            )
        }
        else -> {
            val memories = store.visible(query, category)
            items(memories, key = { it.id }) { memory ->
                Column(Modifier.animateItem()) {
                    val sections = memoryActions(memory, onEdit, onOpenConversation)
                    ContextMenuBox(sections = { sections }, onTap = { onEdit(memory) }) {
                        MemoryCard(memory)
                    }
                    if (memory.id != memories.lastOrNull()?.id) OmiHairline()
                }
            }
        }
    }
}

/** The long-press menu of a memory (`actions(for:)`). */
@Composable
private fun memoryActions(memory: Memory, onEdit: (Memory) -> Unit, onOpenConversation: (String) -> Unit): List<MenuSection> {
    val store = LocalMemoriesStore.current
    val scope = rememberCoroutineScope()
    val items = buildList {
        memory.conversationID?.let { id -> add(MenuItem(L("openConversation"), "bubble.left") { onOpenConversation(id) }) }
        add(MenuItem(L("edit"), "pencil") { onEdit(memory) })
        add(
            if (memory.isBaseline) MenuItem(L("unpinAsBaseline"), "pin.slash") { scope.launch { store.setBaseline(memory.id, false) } }
            else MenuItem(L("pinAsBaseline"), "pin") { scope.launch { store.setBaseline(memory.id, true) } },
        )
        add(
            if (memory.visibility == Memory.Visibility.Private) MenuItem(L("nativeMakePublic"), "globe") { scope.launch { store.setVisibility(memory.id, Memory.Visibility.Public) } }
            else MenuItem(L("nativeMakePrivate"), "lock") { scope.launch { store.setVisibility(memory.id, Memory.Visibility.Private) } },
        )
        add(MenuItem(L("delete"), "trash", destructive = true) { store.deleteWithUndo(memory.id) })
    }
    return listOf(MenuSection(items = items))
}
