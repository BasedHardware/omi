package com.friend.ios.features.agent

import android.content.ClipboardManager
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import com.friend.ios.service.stores.ChatStore
import com.friend.ios.service.stores.attachImage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.disabled
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.service.LocalChatStore
import com.friend.ios.service.stores.PendingAttachment

/**
 * Port of `AttachmentButton` (`ChatAttachments.swift`). The composer's "+": a photo from the
 * library, a new photo, a file (Flutter `selectImage`, camera, `selectFile`), or a photo on the
 * clipboard. Each one uploads as soon as it is picked; photos go up as JPEG (`ChatImageEncoder`:
 * the backend refuses HEIC). The camera writes into the cache through the app's FileProvider.
 */
@Composable
fun AttachmentButton() {
    val chat = LocalChatStore.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val resolver = context.contentResolver

    /** Reads a picked file and attaches it: photos as JPEG, anything else as it is. */
    fun attachURI(uri: Uri) = scope.launch {
        val read = withContext(Dispatchers.IO) {
            runCatching { resolver.openInputStream(uri)?.use { it.readBytes() } }.getOrNull()
        } ?: return@launch
        val name = displayName(context, uri)
        val mimeType = resolver.getType(uri) ?: "application/octet-stream"
        if (mimeType.startsWith("image/") && chat.attachImage(read, name)) return@launch
        chat.attach(read, name ?: "file", mimeType, null)
    }

    // Library photos are often HEIC: converted to JPEG on the way up.
    val library = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(ChatStore.MAX_ATTACHMENTS)) { uris ->
        uris.take(ChatStore.MAX_ATTACHMENTS - chat.attachments.size).forEach { attachURI(it) }
    }
    var cameraFile by remember { mutableStateOf<File?>(null) }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { saved ->
        val file = cameraFile ?: return@rememberLauncherForActivityResult
        cameraFile = null
        if (!saved) return@rememberLauncherForActivityResult
        scope.launch {
            val bytes = withContext(Dispatchers.IO) { runCatching { file.readBytes() }.getOrNull().also { file.delete() } } ?: return@launch
            chat.attachImage(bytes)
        }
    }
    val files = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        uris.take(ChatStore.MAX_ATTACHMENTS - chat.attachments.size).forEach { attachURI(it) }
    }
    val clipboard = remember { context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager }
    val hasCamera = remember { context.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY) }

    val sections = listOf(
        MenuSection(
            items = buildList {
                add(MenuItem(L("photoLibrary"), "photo.on.rectangle") {
                    library.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                })
                if (hasCamera) {
                    add(MenuItem(L("takePhoto"), "camera") {
                        val file = File(context.cacheDir, "camera").apply { mkdirs() }.resolve("photo-${System.currentTimeMillis()}.jpg")
                        cameraFile = file
                        runCatching { camera.launch(FileProvider.getUriForFile(context, "${context.packageName}.omi.files", file)) }
                    })
                }
                add(MenuItem(L("chooseFile"), "doc") { files.launch(fileTypes) })
                // Photos or screenshots copied elsewhere, as they are on the clipboard.
                if (clipboardImages(clipboard).isNotEmpty()) {
                    add(MenuItem(L("nativeChatPastePhoto"), "doc.on.clipboard") {
                        clipboardImages(clipboard).take(ChatStore.MAX_ATTACHMENTS - chat.attachments.size).forEach { attachURI(it) }
                    })
                }
            },
        ),
    )
    val enabled = chat.canAttach
    val circle = Modifier
        .size(DS.Size.composer)
        .background(DS.Palette.card, CircleShape)
        .border(0.5.dp, DS.Palette.cardStroke, CircleShape)
    val label = L("nativeAttach")
    if (enabled) {
        OmiMenu(sections, contentDescription = label) {
            // A round chip beside the field, the same size as the mic on the other side.
            Box(circle, contentAlignment = Alignment.Center) { SFImage("plus", size = 18.sp, tint = DS.Palette.ink) }
        }
    } else {
        Box(circle.semantics { contentDescription = label; disabled() }, contentAlignment = Alignment.Center) {
            SFImage("plus", size = 18.sp, tint = DS.Palette.inkDisabled)
        }
    }
}

/** The document types Flutter offers, plus any image. */
private val fileTypes = arrayOf(
    "image/*", "application/pdf", "text/plain", "text/markdown", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

/** Image URIs on the clipboard (`UIPasteboard.hasImages`). */
private fun clipboardImages(clipboard: ClipboardManager): List<Uri> {
    val clip = clipboard.primaryClip ?: return emptyList()
    val description = clip.description
    val isImage = (0 until description.mimeTypeCount).any { description.getMimeType(it).startsWith("image/") }
    if (!isImage) return emptyList()
    return (0 until clip.itemCount).mapNotNull { clip.getItemAt(it).uri }
}

/** The file's name as the provider shows it. */
private fun displayName(context: Context, uri: Uri): String? = runCatching {
    context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        if (cursor.moveToFirst()) cursor.getString(0) else null
    }
}.getOrNull() ?: uri.lastPathSegment

/**
 * What is attached to the next message: thumbnails with a spinner while uploading, a warning when
 * the upload failed, and a remove button.
 */
@Composable
fun AttachmentStrip() {
    val chat = LocalChatStore.current
    Row(
        Modifier.horizontalScroll(rememberScrollState()).padding(top = DS.Spacing.sm, end = DS.Spacing.sm),
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        for (attachment in chat.attachments) {
            Box {
                val shape = ContinuousRoundedShape(DS.Radius.sm)
                if (attachment.preview != null) {
                    AttachmentThumbnail(attachment.preview, modifier = Modifier.size(56.dp).clip(shape))
                } else {
                    DocumentChip(attachment.filename, Modifier.height(56.dp).clip(shape))
                }
                Box(Modifier.align(Alignment.Center)) {
                    when (attachment.state) {
                        PendingAttachment.State.Uploading -> OmiProgress(Modifier.size(16.dp))
                        PendingAttachment.State.Failed -> SFImage("exclamationmark.triangle.fill", tint = DS.Palette.live, contentDescription = L("nativeAttachmentFailed"))
                        is PendingAttachment.State.Uploaded -> Unit
                    }
                }
                Box(
                    Modifier
                        .align(Alignment.TopEnd)
                        .offset(6.dp, (-6).dp)
                        .plainButton { chat.removeAttachment(attachment.id) }
                        .background(Color.Black.copy(alpha = 0.6f), CircleShape),
                ) {
                    SFImage("xmark.circle.fill", tint = Color.White, contentDescription = L("nativeRemoveAttachment"))
                }
            }
        }
    }
}
