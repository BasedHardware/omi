package com.friend.ios.features.settings

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ImportJob
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.Formatted
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.rememberHaptics
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.ImportStore
import com.friend.ios.service.stores.makeImportStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Port of `ImportScreen.swift`. Memory > Import history (Flutter `import_history_page`): pick a
 * Limitless export zip, Omi turns it into conversations in the background; past imports with
 * their progress and counts.
 */
@Composable
fun ImportScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val store = remember { settings.makeImportStore() }
    var started by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { store.load() }
    DisposableEffect(Unit) { onDispose { store.stopPolling() } }
    // `.fileImporter(allowedContentTypes: [.zip])`.
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val (name, bytes) = withContext(Dispatchers.IO) { read(context, uri) }
            started = store.importZip(bytes, name, settings.spokenLanguage ?: "en")
            if (started) haptics.success()
        }
    }

    SettingsListPage(L("nativeSettingsImportHistory"), onBack) {
        section(footer = L("nativeImportFooter")) {
            row(onClick = { picker.launch(arrayOf("application/zip", "application/x-zip-compressed")) }, enabled = !store.isUploading) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                    SFImage("doc.zipper", size = 22.sp, weight = FontWeight.Light, tint = DS.Palette.inkSecondary)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                        Text("Limitless", style = DS.Typography.cardTitle, color = DS.Palette.ink)
                        Text(L("nativeImportLimitlessHint"), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                    }
                    if (store.isUploading) OmiProgress()
                }
            }
            val error = store.lastError
            if (started) {
                row { Text(L("nativeImportStarted"), style = DS.Typography.caption, color = DS.Palette.inkSecondary) }
            } else if (error != null) {
                row { Text(if (error == "tooLarge") L("nativeImportTooLarge") else L("nativeImportFailed"), style = DS.Typography.caption, color = DS.Palette.live) }
            }
        }
        section(header = L("nativeImportsSoFar")) {
            when (store.phase) {
                ImportStore.Phase.Idle, ImportStore.Phase.Loading -> row { Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { OmiProgress() } }
                ImportStore.Phase.Failed -> row { Text(L("couldNotLoadImportHistory"), style = DS.Typography.body, color = DS.Palette.inkSecondary) }
                ImportStore.Phase.Loaded -> if (store.jobs.isEmpty()) {
                    row { Text(L("noImportsYet"), style = DS.Typography.body, color = DS.Palette.inkSecondary) }
                } else {
                    store.jobs.forEach { job ->
                        row(key = job.id) {
                            // `.swipeActions` (Cancel or Delete) on iOS; a long press offers it here.
                            val action = if (job.isRunning) MenuItem(L("cancel"), "xmark") { scope.launch { store.cancel(job.id) } }
                            else MenuItem(L("delete"), "trash", destructive = true) { scope.launch { store.delete(job.id) } }
                            ContextMenuBox({ listOf(MenuSection(items = listOf(action))) }, Modifier.fillMaxWidth()) { ImportJobRow(job) }
                        }
                    }
                }
            }
        }
    }
}

/** The picked file's name and bytes (null when unreadable). */
private fun read(context: Context, uri: Uri): Pair<String, ByteArray?> {
    val name = runCatching {
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        }
    }.getOrNull() ?: uri.lastPathSegment ?: "import.zip"
    val bytes = runCatching { context.contentResolver.openInputStream(uri)?.use { it.readBytes() } }.getOrNull()
    return name to bytes
}

@Composable
private fun ImportJobRow(job: ImportJob) {
    Column(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xxs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            val status = when (job.status) {
                ImportJob.Status.Pending -> L("statusPending")
                ImportJob.Status.Processing -> L("statusProcessing")
                ImportJob.Status.Completed -> L("statusCompleted")
                ImportJob.Status.Failed -> L("statusFailed")
                ImportJob.Status.Cancelled -> L("nativeImportCancelled")
            }
            Text(status, style = DS.Typography.cardTitle, color = DS.Palette.ink)
            Spacer(Modifier.weight(1f).width(DS.Spacing.sm))
            job.createdAt?.let {
                Text(Formatted.abbreviatedDate(it) + ", " + Formatted.shortTime(it), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
            }
        }
        val progress = job.progress
        if (job.isRunning && progress != null) {
            // `ProgressView(value:)` tinted ink.
            Box(Modifier.fillMaxWidth().height(4.dp).background(DS.Palette.fill, CircleShape)) {
                Box(Modifier.fillMaxWidth(progress.toFloat()).height(4.dp).background(DS.Palette.ink, CircleShape))
            }
            val total = job.totalFiles
            val done = job.processedFiles
            if (total != null && done != null) {
                Text(L("nativeImportFiles", done.toString(), total.toString()), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
            }
        }
        job.created?.let { created ->
            Text(L("nativeImportCounts", created.toString(), (job.skipped ?: 0).toString()), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
        }
        val error = job.error
        if (job.status == ImportJob.Status.Failed && error != null) {
            Text(error, style = DS.Typography.caption, color = DS.Palette.live, maxLines = 2)
        }
    }
}
