package com.friend.ios.features.conversations

import android.app.Activity
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import java.io.File
import java.util.UUID

/**
 * Port of `ShareSheet.swift`: what the system share sheet is opened with, and what happens once it
 * closes. [items] are text (`String`) or local files (`File`).
 */
class ShareRequest(
    val items: List<Any>,
    /** `true` when something was actually shared. */
    val onFinish: (Boolean) -> Unit = {},
) {
    val id: String = UUID.randomUUID().toString()
}

/**
 * The system share sheet (`UIActivityViewController`): Android's chooser. Whether the user shared
 * or backed out comes from the chooser's "component chosen" callback, as
 * `completionWithItemsHandler` reports it on iOS. Returns the function that opens it.
 */
@Composable
fun rememberShareSheet(): (ShareRequest) -> Unit {
    val context = LocalContext.current
    val state = remember { ShareState() }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        val request = state.pending ?: return@rememberLauncherForActivityResult
        state.pending = null
        request.onFinish(state.chosen)
    }
    DisposableEffect(context) {
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                state.chosen = true
            }
        }
        ContextCompat.registerReceiver(context, receiver, IntentFilter(state.action), ContextCompat.RECEIVER_NOT_EXPORTED)
        onDispose { runCatching { context.unregisterReceiver(receiver) } }
    }
    return remember(context) {
        { request: ShareRequest ->
            state.pending = request
            state.chosen = false
            val callback = PendingIntent.getBroadcast(
                context, 0, Intent(state.action).setPackage(context.packageName),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
            )
            launcher.launch(Intent.createChooser(sendIntent(context, request.items), null, callback.intentSender))
        }
    }
}

private class ShareState {
    var pending: ShareRequest? = null
    var chosen = false
    val action = "com.friend.ios.SHARE_CHOSEN.${UUID.randomUUID()}"
}

/** `ACTION_SEND` for one text or file, `ACTION_SEND_MULTIPLE` for several files. */
internal fun sendIntent(context: Context, items: List<Any>): Intent {
    val texts = items.filterIsInstance<String>()
    val uris = items.filterIsInstance<File>().map { fileUri(context, it) }
    val intent = when {
        uris.size > 1 -> Intent(Intent.ACTION_SEND_MULTIPLE).putParcelableArrayListExtra(Intent.EXTRA_STREAM, ArrayList(uris))
        uris.size == 1 -> Intent(Intent.ACTION_SEND).putExtra(Intent.EXTRA_STREAM, uris[0])
        else -> Intent(Intent.ACTION_SEND)
    }
    if (texts.isNotEmpty()) intent.putExtra(Intent.EXTRA_TEXT, texts.joinToString("\n\n"))
    intent.type = when {
        uris.isEmpty() -> "text/plain"
        items.filterIsInstance<File>().all { it.extension == "mp3" } -> "audio/mpeg"
        items.filterIsInstance<File>().all { it.extension == "wav" } -> "audio/wav"
        else -> "*/*"
    }
    if (uris.isNotEmpty()) intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    return intent
}

/** A cache file as a `content://` URI the receiving app may read (`omi_shared_files.xml`). */
internal fun fileUri(context: Context, file: File): Uri = FileProvider.getUriForFile(context, "${context.packageName}.omi.files", file)

/** Opens a URL (`openURL`, `Link`); false when nothing can open it. */
internal fun openURL(context: Context, url: String): Boolean = runCatching {
    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
    if (context !is Activity) intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    context.startActivity(intent)
    true
}.getOrDefault(false)
