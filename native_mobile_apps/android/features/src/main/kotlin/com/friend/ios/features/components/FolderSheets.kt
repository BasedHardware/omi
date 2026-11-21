package com.friend.ios.features.components

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import com.friend.ios.core.models.Folder
import com.friend.ios.core.models.FolderDraft
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.conversations.SheetBar
import com.friend.ios.features.conversations.SheetBarButton
import com.friend.ios.service.LocalConversationsStore
import kotlinx.coroutines.launch

/** Port of `MoveToFolderSheet` (`FolderSheets.swift`): "Move to folder...": the folders, "No folder", and a new one made on the spot. */
@Composable
fun MoveToFolderSheet(ids: List<String>, onDismiss: () -> Unit, onMoved: () -> Unit = {}) {
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var naming by remember { mutableStateOf(false) }
    var newName by remember { mutableStateOf("") }
    LaunchedEffect(Unit) { conversations.loadFolders() }

    /** The folder all the conversations share, if they do. */
    val folders = ids.map { id -> conversations.conversations.firstOrNull { it.id == id }?.folderID }.toSet()
    val current = if (folders.size == 1) folders.first() else null

    fun move(folderID: String?) {
        haptics.tap()
        scope.launch { conversations.move(ids, folderID) }
        onMoved()
        onDismiss()
    }

    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar(L("moveToFolder"), leading = { SheetBarButton(L("cancel"), onClick = onDismiss) })
        val noFolder = L("noFolder")
        val newFolder = L("newFolder")
        OmiGroupedList(contentPadding = androidx.compose.foundation.layout.PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.section)) {
            section {
                conversations.folders.forEach { folder ->
                    row(key = folder.id, onClick = { move(folder.id) }) {
                        FolderLabel(folder, Modifier.weight(1f))
                        if (current == folder.id) SFImage("checkmark", tint = DS.Palette.agent)
                    }
                }
                row(key = "none", onClick = { move(null) }) {
                    HStack(Modifier.weight(1f), spacing = DS.Spacing.sm) {
                        SFImage("tray", tint = DS.Palette.agent)
                        Text(noFolder, style = DS.Typography.body, color = DS.Palette.ink)
                    }
                    if (current == null && ids.size == 1) SFImage("checkmark", tint = DS.Palette.agent)
                }
            }
            section {
                row(key = "new", onClick = {
                    newName = ""
                    naming = true
                }) {
                    HStack(spacing = DS.Spacing.sm) {
                        SFImage("folder.badge.plus", tint = DS.Palette.agent)
                        Text(newFolder, style = DS.Typography.body, color = DS.Palette.agent)
                    }
                }
            }
        }
    }
    if (naming) {
        OmiAlert(
            L("newFolder"),
            listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("save")) {
                    scope.launch { conversations.createFolder(FolderDraft(name = newName))?.let { move(it.id) } }
                },
            ),
            onDismiss = { naming = false },
            textField = L("folderName") to newName,
            onTextChange = { newName = it },
        )
    }
}

/** Port of `FoldersSheet`: folders: new, rename (tap), delete (iOS swipe; a long press here). Omi's own folders stay. */
@Composable
fun FoldersSheet(onDismiss: () -> Unit) {
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    var renaming by remember { mutableStateOf<Folder?>(null) }
    var naming by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    LaunchedEffect(Unit) { conversations.loadFolders() }

    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar(L("nativeFolders"), trailing = { SheetBarButton(L("done"), prominent = true, onClick = onDismiss) })
        val deleteTitle = L("deleteFolder")
        val newFolder = L("newFolder")
        OmiGroupedList(contentPadding = androidx.compose.foundation.layout.PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.section)) {
            section(footer = L("nativeFolderDeleteFooter")) {
                conversations.folders.forEach { folder ->
                    row(key = folder.id) {
                        ContextMenuBox(
                            sections = {
                                if (folder.isSystem) emptyList() else listOf(
                                    MenuSection(
                                        items = listOf(
                                            MenuItem(deleteTitle, "trash", destructive = true) { scope.launch { conversations.deleteFolder(folder.id) } },
                                        ),
                                    ),
                                )
                            },
                            modifier = Modifier.fillMaxWidth(),
                            onTap = {
                                name = folder.name
                                renaming = folder
                            },
                        ) {
                            HStack(Modifier.fillMaxWidth()) {
                                FolderLabel(folder, Modifier.weight(1f))
                                Text("${folder.conversationCount}", style = DS.Typography.body, color = DS.Palette.inkTertiary)
                            }
                        }
                    }
                }
            }
            section {
                row(key = "new", onClick = {
                    name = ""
                    naming = true
                }) {
                    HStack(spacing = DS.Spacing.sm) {
                        SFImage("folder.badge.plus", tint = DS.Palette.agent)
                        Text(newFolder, style = DS.Typography.body, color = DS.Palette.agent)
                    }
                }
            }
        }
    }
    if (naming) {
        OmiAlert(
            L("newFolder"),
            listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("save")) { scope.launch { conversations.createFolder(FolderDraft(name = name)) } },
            ),
            onDismiss = { naming = false },
            textField = L("folderName") to name,
            onTextChange = { name = it },
        )
    }
    renaming?.let { folder ->
        OmiAlert(
            L("editFolder"),
            listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                // The sheet edits the name only, and the draft carries the folder's look along.
                DialogButton(L("save")) { scope.launch { conversations.updateFolder(folder.id, folder.draft.copy(name = name)) } },
            ),
            onDismiss = { renaming = null },
            textField = L("folderName") to name,
            onTextChange = { name = it },
        )
    }
}

/** Port of `FolderLabel`: a folder's emoji (or a folder glyph) and name. */
@Composable
fun FolderLabel(
    folder: Folder,
    modifier: Modifier = Modifier,
    style: TextStyle = DS.Typography.body,
    color: Color = DS.Palette.ink,
    iconTint: Color = DS.Palette.agent,
) {
    HStack(modifier, spacing = DS.Spacing.sm) {
        if (isEmoji(folder.icon)) {
            Text(folder.icon, style = style)
        } else {
            SFImage("folder", size = style.fontSize, tint = iconTint)
        }
        Text(folder.name, style = style, color = color, maxLines = 1)
    }
}

/** `unicodeScalars.first?.properties.isEmojiPresentation`: the icon starts with an emoji. */
internal fun isEmoji(text: String): Boolean {
    if (text.isEmpty()) return false
    val point = text.codePointAt(0)
    return point in 0x1F000..0x1FAFF || point in 0x2600..0x27BF || point in 0x2B00..0x2BFF || point in 0x1F900..0x1F9FF
}
