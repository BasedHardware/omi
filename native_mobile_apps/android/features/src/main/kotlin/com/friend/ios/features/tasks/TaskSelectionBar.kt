package com.friend.ios.features.tasks

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.disabled
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.DSHaptics
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.SFImage
import com.friend.ios.design.omiSurface
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.deleteWithUndo
import com.friend.ios.service.stores.setCompleted
import kotlinx.coroutines.launch

/** Port of `TaskSelectionBar.swift`: while selecting tasks: how many, then done, export, share, delete (with Undo), finish. */
@Composable
fun TaskSelectionBar(selection: Set<String>?, onSelectionChange: (Set<String>?) -> Unit, onShare: (List<String>) -> Unit, modifier: Modifier = Modifier) {
    val store = LocalTasksStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    // Picked rows still in the list, in list order.
    val chosen = selection ?: emptySet()
    val ids = store.tasks.filter { it.id in chosen }.map { it.id }

    @Composable
    fun Icon(systemImage: String, label: String, tint: Color = DS.Palette.ink, enabled: Boolean = true, action: () -> Unit) {
        val isEnabled = enabled && ids.isNotEmpty()
        SFImage(
            systemImage,
            Modifier.plainButton(enabled = isEnabled, onClick = action),
            size = 17.sp,
            weight = FontWeight.Medium,
            tint = if (isEnabled) tint else DS.Palette.inkDisabled,
            contentDescription = label,
        )
    }

    HStack(
        modifier
            .padding(horizontal = DS.Spacing.lg)
            .fillMaxWidth()
            .heightIn(min = 52.dp)
            .omiSurface(CircleShape)
            .padding(horizontal = DS.Spacing.lg),
        spacing = DS.Spacing.lg,
    ) {
        Text(L("selectedCount", "${ids.size}"), style = DS.Typography.callout.semibold(), color = DS.Palette.ink)
        Spacer(Modifier.weight(1f))
        Icon("checkmark.circle", L("nativeMarkDone")) {
            val picked = ids
            scope.launch { store.setCompleted(picked, true) }
            onSelectionChange(null)
        }
        val export = exportMenuSection("", { ids }, onDone = { onSelectionChange(null) })
        val exportLabel = L("exportButton")
        if (ids.isEmpty()) {
            SFImage("square.and.arrow.up", Modifier.semantics { disabled() }, size = 17.sp, weight = FontWeight.Medium, tint = DS.Palette.inkDisabled, contentDescription = exportLabel)
        } else {
            OmiMenu(listOf(export), contentDescription = exportLabel) {
                SFImage("square.and.arrow.up", size = 17.sp, weight = FontWeight.Medium, tint = DS.Palette.ink)
            }
        }
        // The backend shares at most 20 tasks per link.
        Icon("link", L("nativeShareLink"), enabled = ids.size in 1..20) {
            onShare(ids)
            onSelectionChange(null)
        }
        Icon("trash", L("deleteSelected"), tint = DS.Palette.live) {
            haptics.tap(DSHaptics.Style.Medium)
            store.deleteWithUndo(ids)
            onSelectionChange(null)
        }
        Text(
            L("done"),
            style = DS.Typography.callout.semibold(),
            color = DS.Palette.ink,
            modifier = Modifier.plainButton { onSelectionChange(null) },
        )
    }
}
