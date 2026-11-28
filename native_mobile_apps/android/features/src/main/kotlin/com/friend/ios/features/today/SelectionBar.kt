package com.friend.ios.features.today

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.DSHaptics
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.omiSurface
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.features.components.OmiToast
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.stores.ConversationsStore
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Port of `SelectionBar.swift`: while selecting conversations: how many, then move, merge
 * (after a titled confirmation), delete, done.
 */
@Composable
fun SelectionBar(selection: Set<String>, onSelectionChange: (Set<String>?) -> Unit, state: ConversationListState, modifier: Modifier = Modifier) {
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var message by remember { mutableStateOf<String?>(null) }
    var confirmsMerge by remember { mutableStateOf(false) }
    // Oldest first, the order the merged transcript reads in.
    val ids = conversations.visible.filter { it.id in selection }.sortedBy { it.date }.map { it.id }
    val texts = MergeTexts(L("nativeMergeStarted"), L("nativeMergeNeedsTwo"), L("nativeMergeNotReady"), L("nativeMergeFailed"))

    suspend fun show(text: String) {
        message = text
        delay(3_000)
        if (message == text) message = null
    }

    fun merge() = scope.launch {
        when (val outcome = conversations.merge(ids)) {
            is ConversationsStore.MergeOutcome.Started -> {
                haptics.success()
                // The rows now say "Merging"; the bar stays for the message, then leaves.
                onSelectionChange(emptySet())
                show(outcome.warning ?: texts.started)
                onSelectionChange(null)
            }
            ConversationsStore.MergeOutcome.NeedsTwo -> show(texts.needsTwo)
            ConversationsStore.MergeOutcome.NotReady -> show(texts.notReady)
            ConversationsStore.MergeOutcome.Failed -> show(texts.failed)
        }
    }

    Column(modifier.padding(bottom = DS.Spacing.sm), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        AnimatedVisibility(message != null, enter = fadeIn(), exit = fadeOut()) { OmiToast(message.orEmpty(), "arrow.triangle.merge") }
        HStack(
            Modifier
                .padding(horizontal = DS.Spacing.lg)
                .fillMaxWidth()
                .heightIn(min = 52.dp)
                .omiSurface(CircleShape)
                .padding(horizontal = DS.Spacing.lg),
            spacing = DS.Spacing.lg,
        ) {
            Text(L("selectedCount", "${ids.size}"), style = DS.Typography.callout.semibold().copy(fontFeatureSettings = "tnum"), color = DS.Palette.ink)
            Spacer(Modifier.weight(1f))
            Icon("folder", L("moveToFolder"), ids.isEmpty()) { state.moving = ids }
            Icon("arrow.triangle.merge", L("merge"), ids.isEmpty()) { confirmsMerge = true }
            Icon("trash", L("deleteSelected"), ids.isEmpty(), tint = DS.Palette.live) {
                haptics.tap(DSHaptics.Style.Medium)
                conversations.deleteWithUndo(ids)
                onSelectionChange(null)
            }
            Text(L("done"), style = DS.Typography.callout.semibold(), color = DS.Palette.ink, modifier = Modifier.plainButton { onSelectionChange(null) })
        }
    }
    if (confirmsMerge) {
        OmiConfirmationDialog(
            L("mergeConversations"),
            listOf(DialogButton(L("merge")) { merge() }),
            onDismiss = { confirmsMerge = false },
            message = L("mergeConversationsMessage", "${ids.size}"),
        )
    }
}

private data class MergeTexts(val started: String, val needsTwo: String, val notReady: String, val failed: String)

@Composable
private fun Icon(systemImage: String, label: String, disabled: Boolean, tint: Color = DS.Palette.ink, onClick: () -> Unit) {
    SFImage(
        systemImage,
        Modifier.plainButton(enabled = !disabled, onClick = onClick),
        size = 17.sp,
        weight = FontWeight.Medium,
        tint = if (disabled) DS.Palette.inkDisabled else tint,
        contentDescription = label,
    )
}
