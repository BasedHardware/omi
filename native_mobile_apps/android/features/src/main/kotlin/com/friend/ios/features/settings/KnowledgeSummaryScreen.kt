package com.friend.ios.features.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.KnowledgeGraphView
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.design.plainButton
import com.friend.ios.service.LocalMemoriesStore
import com.friend.ios.service.LocalSessionStore
import com.friend.ios.service.stores.KnowledgeGraphStore
import com.friend.ios.service.stores.MemoriesStore
import com.friend.ios.service.stores.makeGraphStore
import kotlinx.coroutines.launch

/**
 * Port of `KnowledgeSummaryScreen.swift`. How Omi helps > Memory (Flutter's onboarding
 * `knowledge_graph_step`, kept here instead of in onboarding): the map of people, places and things
 * Omi learned with a few counts, what it knows about you directly, importing history from another
 * device, and deleting all memories. Memory visibility lives in the Memories screen's menu.
 */
@Composable
fun KnowledgeSummaryScreen(onBack: () -> Unit) {
    val memories = LocalMemoriesStore.current
    val session = LocalSessionStore.current
    val navigator = LocalSettingsNavigator.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val graph = remember { memories.makeGraphStore(session.displayName) }
    var confirmDeleteMemories by remember { mutableStateOf(false) }
    var deletedMemories by remember { mutableStateOf<Boolean?>(null) }
    LaunchedEffect(Unit) { if (memories.phase == MemoriesStore.Phase.Idle) memories.load() }
    LaunchedEffect(Unit) { graph.load() }

    SettingsListPage(L("nativeSettingsMemory"), onBack) {
        section {
            row {
                Column(Modifier.padding(vertical = DS.Spacing.xs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                    Text(L("onboardingWhatIKnowAboutYouTitle"), style = DS.Typography.sectionTitle, color = DS.Palette.ink)
                    Text(L("nativeWhatIKnowDescription"), style = DS.Typography.callout, color = DS.Palette.inkSecondary)
                }
            }
            row { GraphPreview(graph) { scope.launch { graph.load() } } }
            row { Counts(memories, graph) }
        }
        val aboutYou = memories.visible(category = "system").take(5)
        if (aboutYou.isNotEmpty()) {
            section(header = L("nativeMemoryKindAboutYou")) {
                aboutYou.forEach { memory ->
                    row(key = memory.id) { Text(memory.content, style = DS.Typography.callout, color = DS.Palette.ink, maxLines = 3, overflow = TextOverflow.Ellipsis) }
                }
            }
        }
        section(footer = L("nativeSettingsImportFooter")) {
            row(onClick = { navigator.push(SettingsTopic.ImportHistory) }, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
                SettingsRowLabel(L("nativeSettingsImportHistory"), "square.and.arrow.down")
            }
        }
        val deleted = deletedMemories
        val disabled = memories.phase == MemoriesStore.Phase.Loaded && memories.memories.isEmpty()
        section(footerContent = deleted?.let {
            {
                Text(
                    if (it) L("nativeAllMemoriesDeleted") else L("nativeCouldNotDeleteMemories"),
                    style = com.friend.ios.design.TextStyles.footnote,
                    color = if (it) DS.Palette.inkSecondary else DS.Palette.live,
                )
            }
        }) {
            row(onClick = { confirmDeleteMemories = true }, enabled = !disabled) {
                SettingsButtonText(L("nativeDeleteAllMemories"), if (disabled) DS.Palette.inkDisabled else DS.Palette.live)
            }
        }
    }

    if (confirmDeleteMemories) {
        OmiConfirmationDialog(
            L("nativeDeleteAllMemoriesQuestion", memories.memories.size.toString()),
            listOf(
                DialogButton(L("nativeDeleteAllMemories"), DialogButton.Role.Destructive) {
                    scope.launch {
                        val deleted = memories.deleteAll()
                        if (deleted) haptics.success()
                        deletedMemories = deleted
                    }
                },
            ),
            onDismiss = { confirmDeleteMemories = false },
            message = L("nativeDeleteAllMemoriesWarning"),
        )
    }
}

@Composable
private fun GraphPreview(graph: KnowledgeGraphStore, onRetry: () -> Unit) {
    when (graph.phase) {
        KnowledgeGraphStore.Phase.Loaded -> if (!graph.isEmpty) {
            Box(Modifier.fillMaxWidth().height(260.dp)) { KnowledgeGraphView(graph, interactive = false) }
        } else {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                SFImage("point.3.connected.trianglepath.dotted", tint = DS.Palette.inkSecondary)
                Text(L("noKnowledgeGraphYet"), style = DS.Typography.body, color = DS.Palette.inkSecondary)
            }
        }
        KnowledgeGraphStore.Phase.Failed -> Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
            Text(L("couldNotLoadKnowledgeGraph"), style = DS.Typography.body, color = DS.Palette.inkSecondary)
            Text(L("tryAgain"), style = DS.Typography.body, color = DS.Palette.agent, modifier = Modifier.plainButton(onClick = onRetry))
        }
        else -> Column(Modifier.fillMaxWidth().heightIn(min = 120.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm, Alignment.CenterVertically)) {
            OmiProgress()
            Text(L("loadingKnowledgeGraph"), style = DS.Typography.callout, color = DS.Palette.inkSecondary)
        }
    }
}

/** Memories by kind, and people and places on the map, as one row of numbers. */
@Composable
private fun Counts(memories: MemoriesStore, graph: KnowledgeGraphStore) {
    fun count(category: String) = memories.memories.count { it.category == category }.toString()
    Row(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xs)) {
        Number(count("system"), L("nativeMemoryKindAboutYou"), Modifier.weight(1f))
        Number(count("interesting"), L("filterInteresting"), Modifier.weight(1f))
        if (graph.phase == KnowledgeGraphStore.Phase.Loaded) {
            Number(graph.nodes.count { it.node.kind == "person" }.toString(), L("people"), Modifier.weight(1f))
            Number(graph.nodes.count { it.node.kind == "place" }.toString(), L("nativePlaces"), Modifier.weight(1f))
        } else {
            Number(count("manual"), L("filterManual"), Modifier.weight(1f))
        }
    }
}

@Composable
private fun Number(value: String, label: String, modifier: Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
        Text(value, style = DS.Typography.sectionTitle.copy(fontFeatureSettings = "tnum"), color = DS.Palette.ink)
        Text(label, style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 1)
    }
}
