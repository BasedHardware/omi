package com.friend.ios.features.components

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.service.LocalSyncStore
import com.friend.ios.service.PendingRecording
import com.friend.ios.service.stores.audioFile
import com.friend.ios.service.stores.process
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import kotlin.math.roundToLong

/**
 * Port of `PendingRecordingRow.swift`: a recording still on the phone (from the Omi or the phone's
 * microphone): when and how long, play it, share it as a WAV, or process it now (Flutter
 * `sync_page`, `recording_detail_sheet`). The WAV is decoded on demand (`SyncStore.audioFile`; an
 * Omi recording's Opus through the platform decoder).
 */
@Composable
fun PendingRecordingRow(recording: PendingRecording, player: AudioClipPlayer, modifier: Modifier = Modifier) {
    val sync = LocalSyncStore.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var unavailable by remember { mutableStateOf(false) }
    val playing = player.playingID == recording.filename
    HStack(modifier.fillMaxWidth(), spacing = DS.Spacing.md) {
        SFImage(
            if (playing) "stop.circle.fill" else "play.circle.fill",
            Modifier.plainButton { scope.launch { unavailable = !player.toggle(recording.filename) { sync.audioFile(recording.filename) } } },
            size = 22.sp,
            tint = DS.Palette.ink,
            contentDescription = if (playing) L("nativeRecordingStop") else L("play"),
        )
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            val startedAt = Instant.ofEpochMilli((recording.startedAt * 1000).toLong())
            Text(
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT).format(startedAt.atZone(ZoneId.systemDefault())),
                style = DS.Typography.body,
                color = DS.Palette.ink,
            )
            Text(duration(recording.seconds), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
        }
        Spacer(Modifier.weight(1f))
        if (recording.jobID != null) {
            Text(L("nativeRecordingProcessing"), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
        } else {
            OmiMenu(
                listOf(
                    MenuSection(
                        items = listOf(
                            MenuItem(L("nativeRecordingProcessNow"), "arrow.up.circle") { scope.launch { sync.process(recording.filename) } },
                            MenuItem(L("share"), "square.and.arrow.up") {
                                scope.launch { if (!share(context, recording.filename, sync.audioFile(recording.filename))) unavailable = true }
                            },
                            MenuItem(L("delete"), "trash", destructive = true) { sync.delete(recording.filename) },
                        ),
                    ),
                ),
                contentDescription = L("moreOptions"),
            ) {
                SFImage("ellipsis.circle", size = 20.sp, tint = DS.Palette.inkSecondary)
            }
        }
    }
    if (unavailable) {
        OmiAlert(L("nativeRecordingUnavailable"), listOf(DialogButton(L("ok"), DialogButton.Role.Cancel)), onDismiss = { unavailable = false })
    }
}

/** The share sheet with the decoded WAV (the features module's FileProvider, the cache dir). */
private suspend fun share(context: Context, filename: String, wav: ByteArray?): Boolean {
    wav ?: return false
    val file = withContext(Dispatchers.IO) {
        runCatching { File(context.cacheDir, filename.substringBeforeLast('.') + ".wav").apply { writeBytes(wav) } }.getOrNull()
    } ?: return false
    return runCatching {
        val send = com.friend.ios.features.conversations.sendIntent(context, listOf(file))
        context.startActivity(Intent.createChooser(send, null).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }.isSuccess
}

/** `Duration.seconds(...).formatted(.units(allowed: [.hours, .minutes, .seconds]))`: "1 hr, 2 min, 5 sec". */
private fun duration(seconds: Double): String {
    val total = seconds.roundToLong()
    val parts = mutableListOf<String>()
    if (total >= 3600) parts += "${total / 3600} hr"
    if (total % 3600 >= 60) parts += "${total % 3600 / 60} min"
    if (total % 60 > 0 || parts.isEmpty()) parts += "${total % 60} sec"
    return parts.joinToString(", ")
}
