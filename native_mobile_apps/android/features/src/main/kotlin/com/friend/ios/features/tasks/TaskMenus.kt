package com.friend.ios.features.tasks

import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Integration
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiCircleIcon
import com.friend.ios.design.OmiMenu
import com.friend.ios.features.components.TaskToastsText
import com.friend.ios.service.LocalCapabilitiesStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.CapabilitiesStore
import com.friend.ios.service.stores.canIndent
import com.friend.ios.service.stores.canOutdent
import com.friend.ios.service.stores.clearCompleted
import com.friend.ios.service.stores.deleteWithUndo
import com.friend.ios.service.stores.descendants
import com.friend.ios.service.stores.export
import com.friend.ios.service.stores.exportAllOpen
import com.friend.ios.service.stores.indent
import com.friend.ios.service.stores.outdent
import kotlinx.coroutines.launch

/**
 * Port of `TaskMenus.swift`: the task apps the user connected (Capabilities), by backend key.
 * Apple Reminders has no Android counterpart, so it is never a target here.
 */
fun exportTargets(capabilities: CapabilitiesStore): List<String> =
    capabilities.integrations.filter { it.kind == Integration.Kind.TaskApp && it.isConnected }.map { it.id }

/**
 * `ExportMenu`: "Export to ..." for the given tasks: one entry per connected app; a hint when none
 * is connected. Compose menus have no nested `Menu`, so several apps become one section headed
 * [title] (or "Export") with an entry per app. The hint row does nothing (iOS shows it disabled).
 */
@Composable
fun exportMenuSection(title: String, ids: () -> List<String>, all: Boolean = false, onDone: () -> Unit = {}): MenuSection {
    val store = LocalTasksStore.current
    val capabilities = LocalCapabilitiesStore.current
    val scope = rememberCoroutineScope()
    val targets = exportTargets(capabilities)
    fun item(app: String, label: String) = MenuItem(label, "square.and.arrow.up") {
        val chosen = ids()
        scope.launch { if (all) store.exportAllOpen(app) else store.export(chosen, app) }
        onDone()
    }
    return when {
        targets.isEmpty() -> MenuSection(items = listOf(MenuItem(L("connectTaskAppToExport"), "square.and.arrow.up") {}))
        targets.size == 1 -> MenuSection(
            items = listOf(item(targets[0], title.ifEmpty { L("nativeExportTo", TaskToastsText.appName(targets[0])) })),
        )
        else -> MenuSection(
            header = title.ifEmpty { L("exportButton") },
            items = targets.map { item(it, TaskToastsText.appName(it)) },
        )
    }
}

/**
 * `TaskContextMenu`: long press on a task: edit, done, indent / outdent, export, share link,
 * select, delete.
 */
@Composable
fun taskContextMenu(
    task: ActionItem,
    onEdit: () -> Unit,
    onShare: (List<String>) -> Unit,
    onSelect: (Set<String>) -> Unit,
): List<MenuSection> {
    val store = LocalTasksStore.current
    val scope = rememberCoroutineScope()
    val main = buildList {
        add(MenuItem(L("editActionItem"), "pencil", action = onEdit))
        add(
            if (task.isCompleted) MenuItem(L("nativeMarkOpen"), "circle") { scope.launch { store.setCompleted(task.id, false) } }
            else MenuItem(L("nativeMarkDone"), "checkmark.circle") { scope.launch { store.setCompleted(task.id, true) } },
        )
        if (store.canIndent(task.id)) add(MenuItem(L("indentTask"), "increase.indent") { scope.launch { store.indent(task.id) } })
        if (store.canOutdent(task.id)) add(MenuItem(L("outdentTask"), "decrease.indent") { scope.launch { store.outdent(task.id) } })
    }
    val export = if (!task.isExported && task.owner != ActionItem.Owner.Other) exportMenuSection("", { listOf(task.id) }) else null
    val rest = listOf(
        MenuItem(L("nativeShareLink"), "link") { onShare(listOf(task.id)) },
        MenuItem(L("selectOption"), "checkmark.circle") { onSelect((listOf(task.id) + store.descendants(task.id)).toSet()) },
        MenuItem(L("delete"), "trash", destructive = true) { store.deleteWithUndo(listOf(task.id)) },
    )
    // One flat menu on iOS; the export entries sit in their own group here (no nested menus).
    return listOfNotNull(MenuSection(items = main), export, MenuSection(items = rest))
}

/**
 * `TasksHeaderMenu`: the Tasks header's "...": select, export all open, clear completed, goals.
 * iOS also offers "Sync with Reminders" (RemindersSyncStore, EventKit); Apple Reminders is iOS
 * only, so Android leaves it out and exports to the connected task apps instead.
 */
@Composable
fun TasksHeaderMenu(onSelect: () -> Unit, onGoals: () -> Unit) {
    val store = LocalTasksStore.current
    val sections = listOf(
        MenuSection(
            items = listOf(
                MenuItem(L("selectOption"), "checkmark.circle") { if (store.tasks.isNotEmpty()) onSelect() },
            ),
        ),
        exportMenuSection(L("nativeExportAllOpen"), { emptyList() }, all = true),
        MenuSection(
            items = listOf(
                MenuItem(L("nativeClearCompleted"), "trash", destructive = true) {
                    if (store.tasks.any { it.isCompleted }) store.clearCompleted()
                },
            ),
        ),
        MenuSection(items = listOf(MenuItem(L("goals"), "flag", action = onGoals))),
    )
    OmiMenu(sections, contentDescription = L("moreOptions")) { OmiCircleIcon("ellipsis") }
}
