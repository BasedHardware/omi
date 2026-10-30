package com.friend.ios.features.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
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
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.cleanUpCandidates
import com.friend.ios.service.stores.deletePeople
import kotlinx.coroutines.launch

/**
 * Port of `PeopleCleanUpScreen.swift`: review before a bulk delete. Everyone Omi is unsure about
 * starts ticked; pinned people are never listed (Flutter `people_clean_up_page`).
 */
@Composable
fun PeopleCleanUpScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var ticked by remember { mutableStateOf<Set<String>?>(null) }
    var confirms by remember { mutableStateOf(false) }
    val candidates = settings.cleanUpCandidates
    val ids = candidates.map { it.id }.toSet()
    val selected = (ticked ?: ids).intersect(ids)
    val allSelected = selected.size == candidates.size
    SettingsListPage(
        L("cleanUpTitle"),
        onBack,
        trailing = {
            if (candidates.isNotEmpty()) {
                Text(
                    if (allSelected) L("deselectAll") else L("selectAll"),
                    style = DS.Typography.body,
                    color = DS.Palette.ink,
                    modifier = Modifier.padding(end = DS.Spacing.sm).plainButton { ticked = if (allSelected) emptySet() else ids },
                )
            }
        },
    ) {
        if (candidates.isEmpty()) {
            section {
                plainRow { OmiEmptyState(L("cleanUpNothingTitle"), "checkmark.circle", Modifier.padding(top = 72.dp), message = L("cleanUpNothingMessage")) }
            }
        } else {
            section(header = L("nativeCleanUpLead"), footer = L("cleanUpPinnedNote")) {
                candidates.forEach { person ->
                    row(key = person.id, onClick = {
                        haptics.selection()
                        ticked = if (person.id in selected) selected - person.id else selected + person.id
                    }, separatorInset = 56.dp) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                            val on = person.id in selected
                            SFImage(if (on) "checkmark.circle.fill" else "circle", size = 20.sp, tint = if (on) DS.Palette.ink else DS.Palette.inkTertiary)
                            PersonRow(person)
                        }
                    }
                }
            }
            section {
                row(onClick = { confirms = true }, enabled = selected.isNotEmpty()) {
                    Text(
                        L("nativeDeleteSelectedPeople", selected.size.toString()),
                        style = DS.Typography.body,
                        color = if (selected.isEmpty()) DS.Palette.inkDisabled else DS.Palette.live,
                    )
                }
            }
        }
    }
    if (confirms) {
        OmiConfirmationDialog(
            L("nativeDeletePeopleQuestion", selected.size.toString()),
            listOf(
                DialogButton(L("nativeDeleteSelectedPeople", selected.size.toString()), DialogButton.Role.Destructive) {
                    scope.launch {
                        settings.deletePeople(selected)
                        if (settings.lastError == null) onBack()
                    }
                },
            ),
            onDismiss = { confirms = false },
            message = L("nativeDeletePersonMessage"),
        )
    }
}
