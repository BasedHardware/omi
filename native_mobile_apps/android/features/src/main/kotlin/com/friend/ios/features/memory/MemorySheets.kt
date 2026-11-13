package com.friend.ios.features.memory

import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.graphics.layer.GraphicsLayer
import androidx.compose.ui.graphics.rememberGraphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.friend.ios.core.models.Memory
import com.friend.ios.design.CircleIconButton
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiColorScheme
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiPushedScreen
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.KnowledgeGraphView
import com.friend.ios.features.components.OmiGroupedList
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiRowGlyph
import com.friend.ios.features.components.OmiToggleRow
import com.friend.ios.service.LocalMemoriesStore
import com.friend.ios.service.stores.KnowledgeGraphStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** Port of `EditMemorySheet` (`MemorySheets.swift`): edit a memory's text, pin it as a baseline, keep it private (Flutter `memory_edit_sheet`). */
@Composable
fun EditMemorySheet(memory: Memory, onDismiss: () -> Unit) {
    val store = LocalMemoriesStore.current
    val scope = rememberCoroutineScope()
    var text by remember { mutableStateOf(memory.content) }
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { if (!memory.isLocked) focus.requestFocus() }
    val current = store.memories.firstOrNull { it.id == memory.id } ?: memory
    val canSave = text.isNotBlank() && text != memory.content

    Column {
        MemorySheetBar(
            title = L("editMemoryTitle"),
            canSave = canSave,
            onCancel = onDismiss,
            onSave = {
                scope.launch { store.edit(memory.id, text) }
                onDismiss()
            },
        )
        val placeholder = L("editMemoryTitle")
        val baseline = L("baselineMemory")
        val private = L("nativeMemoryPrivate")
        OmiGroupedList(contentPadding = PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.section)) {
            section {
                row { MemoryTextField(text, { text = it }, placeholder, focus, enabled = !memory.isLocked) }
            }
            section(footer = L("nativeMemoryPrivateFooter")) {
                row(separatorInset = OmiListMetrics.iconSeparatorInset) {
                    OmiToggleRow(current.isBaseline, { pinned -> scope.launch { store.setBaseline(memory.id, pinned) } }) {
                        MemoryLabel(baseline, "pin")
                    }
                }
                row(separatorInset = OmiListMetrics.iconSeparatorInset) {
                    OmiToggleRow(current.visibility == Memory.Visibility.Private, { isPrivate ->
                        scope.launch { store.setVisibility(memory.id, if (isPrivate) Memory.Visibility.Private else Memory.Visibility.Public) }
                    }) { MemoryLabel(private, "lock") }
                }
            }
        }
    }
}

/** Port of `NewMemorySheet`: tell Omi something by hand; it is stored as a manual memory. */
@Composable
fun NewMemorySheet(onDismiss: () -> Unit) {
    val store = LocalMemoriesStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var text by remember { mutableStateOf("") }
    var isSaving by remember { mutableStateOf(false) }
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { focus.requestFocus() }

    Column {
        MemorySheetBar(
            title = L("newMemoryTitle"),
            canSave = text.isNotBlank() && !isSaving,
            onCancel = onDismiss,
            onSave = {
                isSaving = true
                scope.launch {
                    if (store.add(text)) {
                        haptics.success()
                        onDismiss()
                    }
                    isSaving = false
                }
            },
        )
        val placeholder = L("nativeWhatShouldOmiRemember")
        OmiGroupedList(contentPadding = PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.section)) {
            section {
                row { MemoryTextField(text, { text = it }, placeholder, focus) }
                store.lastError?.let { error -> row { Text(error, style = DS.Typography.caption, color = DS.Palette.live) } }
            }
        }
    }
}

/** The inline navigation bar of a sheet: Cancel, the title, Save (bold, dimmed while it cannot save). */
@Composable
internal fun MemorySheetBar(title: String, canSave: Boolean, onCancel: () -> Unit, onSave: () -> Unit) {
    Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = DS.Spacing.lg)) {
        Text(L("cancel"), style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.align(Alignment.CenterStart).plainButton(onClick = onCancel))
        Text(title, style = TextStyles.headline, color = DS.Palette.ink, modifier = Modifier.align(Alignment.Center))
        Text(
            L("save"), style = TextStyles.headline, color = if (canSave) DS.Palette.ink else DS.Palette.inkDisabled,
            modifier = Modifier.align(Alignment.CenterEnd).plainButton(enabled = canSave, onClick = onSave),
        )
    }
}

/** `TextField(axis: .vertical).lineLimit(2 ... 8)`. */
@Composable
private fun MemoryTextField(text: String, onChange: (String) -> Unit, placeholder: String, focus: FocusRequester, enabled: Boolean = true) {
    Box(Modifier.fillMaxWidth().heightIn(min = 44.dp)) {
        if (text.isEmpty()) Text(placeholder, style = DS.Typography.body, color = DS.Palette.inkTertiary)
        BasicTextField(
            text, onChange, enabled = enabled, minLines = 2, maxLines = 8,
            textStyle = DS.Typography.body.copy(color = if (enabled) DS.Palette.ink else DS.Palette.inkTertiary),
            cursorBrush = SolidColor(DS.Palette.agent),
            modifier = Modifier.fillMaxWidth().focusRequester(focus),
        )
    }
}

/** `Label(title, systemImage:)` in a Form row. */
@Composable
private fun MemoryLabel(title: String, systemImage: String) {
    HStack(spacing = DS.Spacing.md) {
        OmiRowGlyph(systemImage)
        Text(title, style = DS.Typography.body, color = DS.Palette.ink)
    }
}

/** Port of `MemoryGraphScreen`: Memories > Memory graph, the knowledge graph full screen, shared as an image. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MemoryGraphScreen(graph: KnowledgeGraphStore, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var refreshing by remember { mutableStateOf(false) }
    val card = rememberGraphicsLayer()
    val canShare = graph.phase == KnowledgeGraphStore.Phase.Loaded && !graph.isEmpty
    LaunchedEffect(graph) { graph.load() }
    val message = L("checkOutMyMemoryGraph")
    val shareTitle = L("memoryGraph")

    OmiPushedScreen(L("memoryGraphTitle"), onBack, trailing = {
        if (canShare) {
            CircleIconButton("square.and.arrow.up", contentDescription = L("share")) {
                scope.launch { shareGraph(context, card, message, shareTitle) }
            }
        }
    }) {
        PullToRefreshBox(
            isRefreshing = refreshing,
            onRefresh = {
                scope.launch {
                    refreshing = true
                    graph.load()
                    refreshing = false
                }
            },
            modifier = Modifier.weight(1f).fillMaxWidth(),
        ) {
            when {
                graph.phase == KnowledgeGraphStore.Phase.Idle || graph.phase == KnowledgeGraphStore.Phase.Loading ->
                    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                        OmiProgress()
                        Text(L("loadingKnowledgeGraph"), style = DS.Typography.callout, color = DS.Palette.inkSecondary, modifier = Modifier.padding(top = DS.Spacing.sm))
                    }
                graph.phase == KnowledgeGraphStore.Phase.Failed -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    OmiEmptyState(
                        L("couldNotLoadKnowledgeGraph"), "point.3.connected.trianglepath.dotted",
                        actionTitle = L("tryAgain"), action = { scope.launch { graph.load() } },
                    )
                }
                graph.isEmpty -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    OmiEmptyState(L("noKnowledgeGraphYet"), "point.3.connected.trianglepath.dotted", message = L("nativeGraphBuildsItself"))
                }
                else -> Box(Modifier.fillMaxSize()) {
                    // The share picture, recorded off screen (never drawn here).
                    ShareCard(graph, card, Modifier.align(Alignment.Center))
                    KnowledgeGraphView(graph, Modifier.padding(DS.Spacing.lg))
                }
            }
        }
    }
}

/** A square picture with "omi.me" on top, like Flutter's share (1080 px, always dark). */
@Composable
private fun ShareCard(graph: KnowledgeGraphStore, layer: GraphicsLayer, modifier: Modifier) {
    val density = LocalDensity.current
    val side = with(density) { 1080f.toDp() }
    val padding = with(density) { 60f.toDp() }
    val spacing = with(density) { 24f.toDp() }
    val titleSize = with(density) { 48f.toSp() }
    OmiColorScheme(dark = true) {
        Column(
            modifier
                .requiredSize(side)
                .drawWithContent { layer.record { this@drawWithContent.drawContent() } }
                .background(Color.Black)
                .padding(padding),
            verticalArrangement = Arrangement.spacedBy(spacing),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("omi.me", style = TextStyles.system(48, FontWeight.Bold).copy(fontSize = titleSize), color = Color.White)
            KnowledgeGraphView(graph, Modifier.weight(1f), interactive = false)
        }
    }
}

/** `ShareLink(item: image, message:)`: the picture through the system share sheet. */
private suspend fun shareGraph(context: Context, layer: GraphicsLayer, message: String, title: String) {
    val bitmap = layer.toImageBitmap().asAndroidBitmap()
    val file = withContext(Dispatchers.IO) {
        File(context.cacheDir, "shared").apply { mkdirs() }.resolve("memory-graph.png").also { file ->
            file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
    }
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.omi.files", file)
    val send = Intent(Intent.ACTION_SEND).apply {
        type = "image/png"
        putExtra(Intent.EXTRA_STREAM, uri)
        putExtra(Intent.EXTRA_TEXT, message)
        clipData = ClipData.newRawUri(title, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(send, title))
}
