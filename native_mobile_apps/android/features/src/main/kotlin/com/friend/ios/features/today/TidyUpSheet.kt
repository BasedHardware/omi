package com.friend.ios.features.today

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiPrimaryButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.OmiGroupedList
import com.friend.ios.features.components.OmiToggleRow
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.TaskTidyUp
import kotlinx.coroutines.launch

/** Port of `TidyUpSheet.swift`: the tidy-up's changes, each with Omi's reason and a switch; nothing changes until "Apply". */
@Composable
internal fun TidyUpSheet(onDismiss: () -> Unit) {
    val tasks = LocalTasksStore.current
    val haptics = rememberHaptics()
    val scope = rememberCoroutineScope()
    /** Changes the user switched off. */
    var skipped by remember { mutableStateOf(setOf<String>()) }
    var isApplying by remember { mutableStateOf(false) }
    val edits = tasks.currentTidyUp?.edits.orEmpty()
    val kept = edits.filter { it.id !in skipped }

    fun text(id: String): String = tasks.tasks.firstOrNull { it.id == id }?.description ?: ""

    fun apply(edits: List<TaskTidyUp.Edit>) {
        isApplying = true
        scope.launch {
            tasks.applyTidyUp(edits)
            haptics.success()
            isApplying = false
            onDismiss()
        }
    }

    OmiSheet(onDismiss = onDismiss) {
        Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = DS.Spacing.lg)) {
            Text(L("cancel"), style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.align(Alignment.CenterStart).plainButton(onClick = onDismiss))
            Text(L("nativeTidyUpSheetTitle"), style = TextStyles.headline, color = DS.Palette.ink, modifier = Modifier.align(Alignment.Center))
        }
        Column(Modifier.weight(1f)) {
            OmiGroupedList(Modifier.weight(1f), contentPadding = PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.lg)) {
                val groups = listOf(
                    L("nativeTidyUpSectionMerge") to edits.filter { it.kind is TaskTidyUp.Edit.Kind.Merge },
                    L("nativeTidyUpSectionDone") to edits.filter { it.kind == TaskTidyUp.Edit.Kind.Done },
                    L("nativeTidyUpSectionNotTask") to edits.filter { it.kind == TaskTidyUp.Edit.Kind.NotTask },
                )
                groups.filter { it.second.isNotEmpty() }.forEach { (title, list) ->
                    section(header = title, key = title) {
                        list.forEach { edit ->
                            row(key = edit.id) {
                                OmiToggleRow(edit.id !in skipped, { on -> skipped = if (on) skipped - edit.id else skipped + edit.id }) {
                                    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                                        Text(text(edit.taskID), style = DS.Typography.body, color = DS.Palette.ink)
                                        (edit.kind as? TaskTidyUp.Edit.Kind.Merge)?.let { merge ->
                                            Text(L("nativeTidyUpInto", text(merge.into)), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                                        }
                                        if (edit.why.isNotEmpty()) Text(edit.why, style = DS.Typography.caption, color = DS.Palette.inkTertiary)
                                    }
                                }
                            }
                        }
                    }
                }
                section(footer = L("nativeTidyUpFooter")) {}
            }
            // `.safeAreaInset(edge: .bottom)`: the Apply button under the list.
            Box(Modifier.padding(DS.Spacing.lg), contentAlignment = Alignment.Center) {
                OmiPrimaryButton(if (isApplying) "" else L("nativeTidyUpApply", "${kept.size}"), enabled = kept.isNotEmpty() && !isApplying) { apply(kept) }
                if (isApplying) OmiProgress()
            }
        }
    }
}

/** Port of `TidyUpWording` (`TidyUpSheet.swift`): "Tidy up: merge 6, mark 4 done". */
object TidyUpWording {
    @Composable
    fun title(proposal: TaskTidyUp.Proposal): String {
        val parts = buildList {
            if (proposal.mergedCount > 0) add(L("nativeTidyUpMerge", "${proposal.mergedCount}"))
            if (proposal.done.isNotEmpty()) add(L("nativeTidyUpDone", "${proposal.done.size}"))
            if (proposal.notTask.isNotEmpty()) add(L("nativeTidyUpNotTasks", "${proposal.notTask.size}"))
        }
        return L("nativeTidyUpTitle", parts.joinToString(", "))
    }
}
