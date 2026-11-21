package com.friend.ios.features.tasks

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
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
import com.friend.ios.core.models.SharedTasks
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiPrimaryButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.Formatting
import com.friend.ios.features.components.OmiFlatList
import com.friend.ios.features.components.relativeDay
import com.friend.ios.features.conversations.SheetBar
import com.friend.ios.features.conversations.SheetBarButton
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.acceptShare
import kotlinx.coroutines.launch

/**
 * Port of `SharedTasksSheet.swift`: someone shared tasks by link (Flutter `AcceptSharedTasksSheet`):
 * what they are, and one button to add them to my list. The share-link "ActivitySheet" is
 * `rememberShareSheet` (`conversations/ShareSheet.kt`).
 */
@Composable
fun SharedTasksSheet(share: SharedTasks, onDismiss: () -> Unit) {
    val store = LocalTasksStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var isAdding by remember { mutableStateOf(false) }
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar(
            L("nativeSharedBy", share.senderName ?: L("sharedTasksUnknownSender")),
            leading = { SheetBarButton(L("cancel"), onClick = onDismiss) },
        )
        Box(Modifier.weight(1f, fill = false)) {
            OmiFlatList(contentPadding = PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.lg)) {
                section(header = L("addToYourTaskList")) {
                    share.tasks.forEachIndexed { index, item ->
                        row(key = index) {
                            HStack(alignment = Alignment.Top, spacing = DS.Spacing.md) {
                                SFImage("circle", Modifier.padding(top = 2.dp), tint = DS.Palette.inkTertiary)
                                Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                                    Text(item.description, style = DS.Typography.body, color = DS.Palette.ink)
                                    item.dueAt?.let { due ->
                                        Text(L("taskDueDate", Formatting.relativeDay(due)), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        Box(Modifier.fillMaxWidth().padding(DS.Spacing.lg), contentAlignment = Alignment.Center) {
            if (isAdding) {
                OmiProgress(Modifier.size(24.dp))
            } else {
                OmiPrimaryButton(L("nativeAddSharedTasks")) {
                    isAdding = true
                    scope.launch {
                        if (store.acceptShare()) haptics.success()
                        isAdding = false
                        onDismiss()
                    }
                }
            }
        }
    }
}
