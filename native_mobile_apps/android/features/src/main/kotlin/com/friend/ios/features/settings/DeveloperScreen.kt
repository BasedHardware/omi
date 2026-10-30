package com.friend.ios.features.settings

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.DeveloperKey
import com.friend.ios.core.models.DeveloperWebhook
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.MenuSection
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.CircleShape
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.features.components.OmiGroupedList
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiToggleRow
import com.friend.ios.service.DebugLog
import com.friend.ios.service.LocalDebugLog
import com.friend.ios.service.LocalDeveloperStore
import com.friend.ios.service.LocalSessionStore
import com.friend.ios.service.stores.DeveloperStore
import kotlinx.coroutines.launch

/**
 * Port of `DeveloperScreen.swift`. Settings > Developer (Flutter `developer.dart`): your user ID,
 * webhooks, API and MCP keys, the experimental switches, logs and docs. Shown once Developer mode
 * is on in Help.
 */
@Composable
fun DeveloperScreen(onBack: () -> Unit) {
    val developer = LocalDeveloperStore.current
    val session = LocalSessionStore.current
    val navigator = LocalSettingsNavigator.current
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    val haptics = rememberHaptics()
    var copiedID by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { developer.load() }
    val enabledWebhooks = developer.webhooks.values.count { it.isEnabled }
    val icon = OmiListMetrics.iconSeparatorInset
    val userIdTitle = L("userId")
    val copyUserID = L("nativeCopyUserID")
    val webhooks = L("nativeDevWebhooks")
    val apiKeys = L("nativeDevAPIKeys")
    val mcp = L("nativeDevMCP")
    val tools = L("nativeDevConversationTools")
    val vad = L("nativeDevVADGate")
    val logs = L("nativeDevLogs")
    val appsDocs = L("nativeDevAppsDocs")
    val mcpDocs = L("nativeDevMCPDocs")
    SettingsListPage(L("nativeDeveloper"), onBack) {
        session.userID?.let { uid ->
            section {
                row(onClick = {
                    copyToClipboard(context, uid)
                    haptics.success()
                    copiedID = true
                }) {
                    // `.accessibilityLabel(L("nativeCopyUserID"))`: the row reads as what it does.
                    Row(Modifier.weight(1f).clearAndSetSemantics { contentDescription = copyUserID }, verticalAlignment = Alignment.CenterVertically) {
                        Text(userIdTitle, style = DS.Typography.body, color = DS.Palette.ink)
                        Spacer(Modifier.weight(1f).width(DS.Spacing.md))
                        Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs), verticalAlignment = Alignment.CenterVertically) {
                            Text(shortenedUserID(uid), style = DS.Typography.body.copy(fontFamily = FontFamily.Monospace), color = DS.Palette.inkSecondary)
                            SFImage(if (copiedID) "checkmark" else "doc.on.doc", tint = DS.Palette.inkSecondary)
                        }
                    }
                }
            }
        }
        section {
            row(onClick = { navigator.push(SettingsTopic.Webhooks) }, chevron = true, separatorInset = icon) {
                SettingsRowLabel(webhooks, "arrow.triangle.branch", value = enabledWebhooks.takeIf { it > 0 }?.toString())
            }
            row(onClick = { navigator.push(SettingsRoute.DeveloperKeys(DeveloperKey.Kind.Api.rawValue)) }, chevron = true, separatorInset = icon) {
                SettingsRowLabel(apiKeys, "key", value = developer.apiKeys.size.takeIf { it > 0 }?.toString())
            }
            row(onClick = { navigator.push(SettingsRoute.DeveloperKeys(DeveloperKey.Kind.Mcp.rawValue)) }, chevron = true, separatorInset = icon) {
                SettingsRowLabel(mcp, "server.rack", value = developer.mcpKeys.size.takeIf { it > 0 }?.toString())
            }
        }
        section(header = L("nativeDevExperimental"), footer = L("nativeDevExperimentalFooter")) {
            row { OmiToggleRow(developer.showsConversationTools, { developer.showsConversationTools = it }) { Text(tools, style = DS.Typography.body, color = DS.Palette.ink) } }
            row { OmiToggleRow(developer.vadGate, { developer.vadGate = it }) { Text(vad, style = DS.Typography.body, color = DS.Palette.ink) } }
        }
        section {
            row(onClick = { navigator.push(SettingsTopic.Logs) }, chevron = true, separatorInset = icon) { SettingsRowLabel(logs, "list.bullet.rectangle") }
            row(onClick = { uriHandler.openUri("https://docs.omi.me/doc/developer/apps/Introduction") }) { SettingsButtonText(appsDocs) }
            row(onClick = { uriHandler.openUri("https://docs.omi.me/doc/developer/MCP") }) { SettingsButtonText(mcpDocs) }
        }
    }
}

/** `abc•••••xyz`, as Flutter shows it; the full id is copied. */
fun shortenedUserID(uid: String): String = if (uid.length > 10) uid.take(3) + "•••••" + uid.takeLast(3) else uid

@Composable
fun webhookTitle(hook: DeveloperWebhook): String = when (hook) {
    DeveloperWebhook.ConversationCreated -> L("nativeDevHookConversation")
    DeveloperWebhook.RealtimeTranscript -> L("nativeDevHookTranscript")
    DeveloperWebhook.AudioBytes -> L("nativeDevHookAudio")
    DeveloperWebhook.DaySummary -> L("nativeDevHookDaySummary")
}

internal fun copyToClipboard(context: Context, text: String) {
    (context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager)?.setPrimaryClip(ClipData.newPlainText(null, text))
}

/** Developer > Webhooks: the four webhooks; edits are saved together (or discarded on the way out). */
@Composable
fun WebhooksScreen(onBack: () -> Unit) {
    val developer = LocalDeveloperStore.current
    val scope = rememberCoroutineScope()
    var confirmsDiscard by remember { mutableStateOf(false) }
    val unsaved = developer.hasUnsavedWebhooks
    BackHandler(enabled = unsaved) { confirmsDiscard = true }
    SettingsListPage(
        L("nativeDevWebhooks"),
        onBack = { if (unsaved) confirmsDiscard = true else onBack() },
        trailing = {
            if (unsaved) {
                Text(
                    L("save"),
                    style = TextStyles.headline,
                    color = if (developer.isSaving) DS.Palette.inkDisabled else DS.Palette.ink,
                    modifier = Modifier.padding(horizontal = DS.Spacing.sm).plainButton(enabled = !developer.isSaving) { scope.launch { developer.saveWebhooks() } },
                )
            }
        },
    ) {
        section(footer = L("nativeDevWebhooksFooter")) {
            DeveloperWebhook.entries.forEach { hook -> row(key = hook.rawValue) { WebhookRow(hook, developer) } }
        }
    }
    if (confirmsDiscard) {
        OmiConfirmationDialog(
            L("nativeDevDiscardQuestion"),
            listOf(
                DialogButton(L("nativeDevDiscard"), DialogButton.Role.Destructive) {
                    developer.discardWebhookEdits()
                    onBack()
                },
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
            ),
            onDismiss = { confirmsDiscard = false },
        )
    }
    val failure = developer.failure
    if (failure != null) {
        val text = when (failure) {
            is DeveloperStore.Failure.InvalidURL -> L("nativeDevInvalidURL", webhookTitle(failure.hook))
            DeveloperStore.Failure.CouldNotSave -> L("nativeDevCouldNotSave")
            DeveloperStore.Failure.CouldNotLoad -> L("nativeDevCouldNotLoad")
        }
        OmiAlert(text, listOf(DialogButton(L("ok"), DialogButton.Role.Cancel)), onDismiss = { developer.failure = null })
    }
}

/** One webhook: its switch (once a URL is saved), the URL, and for audio the interval. */
@Composable
private fun WebhookRow(hook: DeveloperWebhook, developer: DeveloperStore) {
    val scope = rememberCoroutineScope()
    val webhook = developer.webhooks[hook] ?: DeveloperStore.Webhook()
    Column(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xxs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        OmiToggleRow(webhook.isEnabled, { value -> scope.launch { developer.setEnabled(hook, value) } }, enabled = webhook.savedURL.isNotEmpty()) {
            Text(webhookTitle(hook), style = DS.Typography.body, color = DS.Palette.ink)
        }
        Box(Modifier.fillMaxWidth()) {
            if (webhook.url.isEmpty()) Text("https://", style = DS.Typography.callout, color = DS.Palette.inkTertiary)
            BasicTextField(
                webhook.url, { developer.edit(hook, url = it) }, singleLine = true,
                textStyle = DS.Typography.callout.copy(color = DS.Palette.ink), cursorBrush = SolidColor(DS.Palette.agent),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, autoCorrectEnabled = false),
                modifier = Modifier.fillMaxWidth(),
            )
        }
        if (hook == DeveloperWebhook.AudioBytes) {
            // `Stepper(... in: 1 ... 300)`: minus and plus in one capsule.
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(L("nativeDevAudioInterval", "${webhook.seconds}"), style = DS.Typography.callout, color = DS.Palette.ink, modifier = Modifier.weight(1f))
                Stepper(onMinus = { developer.edit(hook, seconds = maxOf(1, webhook.seconds - 1)) }, onPlus = { developer.edit(hook, seconds = minOf(300, webhook.seconds + 1)) })
            }
        }
    }
}

@Composable
private fun Stepper(onMinus: () -> Unit, onPlus: () -> Unit) {
    Row(
        Modifier.heightIn(min = 32.dp).background(DS.Palette.fill, CircleShape),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.width(46.dp).plainButton(onClick = onMinus), contentAlignment = Alignment.Center) { SFImage("minus", size = 15.sp, tint = DS.Palette.ink) }
        Box(Modifier.width(1.dp).heightIn(min = 18.dp).background(DS.Palette.hairline))
        Box(Modifier.width(46.dp).plainButton(onClick = onPlus), contentAlignment = Alignment.Center) { SFImage("plus", size = 15.sp, tint = DS.Palette.ink) }
    }
}

/** Developer > API keys or MCP: the keys of one kind (`DeveloperKeysScreen` + `DeveloperKeysSection.swift`). */
@Composable
fun DeveloperKeysScreen(kind: String, onBack: () -> Unit) {
    val keyKind = DeveloperKey.Kind.from(kind) ?: DeveloperKey.Kind.Api
    val developer = LocalDeveloperStore.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var naming by remember { mutableStateOf(false) }
    var revoking by remember { mutableStateOf<DeveloperKey?>(null) }
    val keys = if (keyKind == DeveloperKey.Kind.Api) developer.apiKeys else developer.mcpKeys
    val isApi = keyKind == DeveloperKey.Kind.Api
    val serverTitle = L("nativeDevMCPServer")
    val newTitle = if (isApi) L("nativeDevNewAPIKey") else L("nativeDevNewMCPKey")
    val revokeTitle = L("nativeDevRevoke")
    SettingsListPage(if (isApi) L("nativeDevAPIKeys") else L("nativeDevMCP"), onBack) {
        section(header = if (isApi) L("nativeDevAPIKeys") else L("nativeDevMCP"), footer = if (isApi) L("nativeDevAPIKeysFooter") else L("nativeDevMCPFooter")) {
            if (!isApi) {
                row {
                    Text(serverTitle, style = DS.Typography.body, color = DS.Palette.ink)
                    Spacer(Modifier.weight(1f).width(DS.Spacing.md))
                    Text(developer.mcpServerURL, style = DS.Typography.caption, color = DS.Palette.agent, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.plainButton { copyToClipboard(context, developer.mcpServerURL) })
                }
            }
            keys.forEach { key ->
                row(key = key.id) {
                    // `.swipeActions` / `.contextMenu`: Revoke on a long press.
                    ContextMenuBox({ listOf(MenuSection(items = listOf(com.friend.ios.design.MenuItem(revokeTitle, "trash", destructive = true) { revoking = key }))) }, Modifier.fillMaxWidth()) {
                        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(key.name, style = DS.Typography.body, color = DS.Palette.ink)
                            Text("${key.prefix} · ${key.createdAt?.let(::mediumDate).orEmpty()}", style = DS.Typography.caption.copy(fontFamily = FontFamily.Monospace), color = DS.Palette.inkSecondary)
                        }
                    }
                }
            }
            row(onClick = { naming = true }) { Text(newTitle, style = DS.Typography.body, color = DS.Palette.agent) }
        }
    }
    if (naming) CreateKeySheet(keyKind, developer) { naming = false }
    val created = developer.createdKey
    if (created != null && developer.createdKeyKind == keyKind) CreatedKeySheet(created, keyKind, developer) { developer.createdKey = null }
    revoking?.let { key ->
        OmiConfirmationDialog(
            L("nativeDevRevokeQuestion", key.name),
            listOf(DialogButton(revokeTitle, DialogButton.Role.Destructive) { scope.launch { developer.revoke(keyKind, key.id) } }),
            onDismiss = { revoking = null },
            message = L("nativeDevRevokeWarning"),
        )
    }
}

/** The name (and for API keys full access), then Create. */
@Composable
private fun CreateKeySheet(kind: DeveloperKey.Kind, developer: DeveloperStore, onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf("") }
    var fullAccess by remember { mutableStateOf(false) }
    val isApi = kind == DeveloperKey.Kind.Api
    OmiSheet(onDismiss = onDismiss, detents = setOf(com.friend.ios.design.Detent.Medium)) {
        SheetBar(if (isApi) L("nativeDevNewAPIKey") else L("nativeDevNewMCPKey"), L("cancel"), onDismiss, L("nativeDevCreate"), name.isNotBlank()) {
            scope.launch { if (developer.createKey(kind, name, fullAccess)) onDismiss() }
        }
        val placeholder = L("nativeDevKeyName")
        val full = L("nativeDevFullAccess")
        OmiGroupedList(contentPadding = androidx.compose.foundation.layout.PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.section)) {
            section(footer = if (isApi) L("nativeDevFullAccessFooter") else L("nativeDevMCPKeyFooter")) {
                row {
                    Box(Modifier.fillMaxWidth()) {
                        if (name.isEmpty()) Text(placeholder, style = DS.Typography.body, color = DS.Palette.inkTertiary)
                        BasicTextField(name, { name = it }, singleLine = true, textStyle = DS.Typography.body.copy(color = DS.Palette.ink), cursorBrush = SolidColor(DS.Palette.agent), modifier = Modifier.fillMaxWidth())
                    }
                }
                if (isApi) row { OmiToggleRow(fullAccess, { fullAccess = it }) { Text(full, style = DS.Typography.body, color = DS.Palette.ink) } }
            }
        }
    }
}

/** The secret, once: copy it (and for MCP the client config). */
@Composable
private fun CreatedKeySheet(key: DeveloperKey, kind: DeveloperKey.Kind, developer: DeveloperStore, onDone: () -> Unit) {
    val context = LocalContext.current
    var copied by remember { mutableStateOf<String?>(null) }
    OmiSheet(onDismiss = {}) {
        SheetBar(key.name, null, {}, L("done"), true, onDone)
        val secret = key.secret
        val copyKey = L("nativeDevCopyKey")
        val copyConfig = L("nativeDevCopyConfig")
        val copiedTitle = L("copied")
        OmiGroupedList(contentPadding = androidx.compose.foundation.layout.PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.section)) {
            section(footer = L("nativeDevKeyShownOnce")) {
                row { Text(secret ?: key.prefix, style = DS.Typography.callout.copy(fontFamily = FontFamily.Monospace), color = DS.Palette.ink) }
                row(onClick = { copyToClipboard(context, secret.orEmpty()); copied = "key" }) {
                    CopyLabel(if (copied == "key") copiedTitle else copyKey, copied == "key")
                }
            }
            if (kind == DeveloperKey.Kind.Mcp && secret != null) {
                section(header = L("nativeDevMCPConfig"), footer = L("nativeDevMCPConfigFooter")) {
                    row { Text(developer.mcpConfig(secret), style = DS.Typography.caption.copy(fontFamily = FontFamily.Monospace), color = DS.Palette.ink) }
                    row(onClick = { copyToClipboard(context, developer.mcpConfig(secret)); copied = "config" }) {
                        CopyLabel(if (copied == "config") copiedTitle else copyConfig, copied == "config")
                    }
                }
            }
        }
    }
}

@Composable
private fun CopyLabel(title: String, done: Boolean) {
    Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm), verticalAlignment = Alignment.CenterVertically) {
        SFImage(if (done) "checkmark" else "doc.on.doc", tint = DS.Palette.agent)
        Text(title, style = DS.Typography.body, color = DS.Palette.agent)
    }
}

/** A sheet's inline bar: cancel on the left, the title, the confirming action on the right. */
@Composable
private fun SheetBar(title: String, cancel: String?, onCancel: () -> Unit, confirm: String, confirmEnabled: Boolean, onConfirm: () -> Unit) {
    Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = DS.Spacing.lg)) {
        cancel?.let { Text(it, style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.align(Alignment.CenterStart).plainButton(onClick = onCancel)) }
        Text(title, style = TextStyles.headline, color = DS.Palette.ink, modifier = Modifier.align(Alignment.Center))
        Text(
            confirm,
            style = TextStyles.headline,
            color = if (confirmEnabled) DS.Palette.ink else DS.Palette.inkDisabled,
            modifier = Modifier.align(Alignment.CenterEnd).plainButton(enabled = confirmEnabled, onClick = onConfirm),
        )
    }
}

/** Developer > Logs: writing the log to a file, sharing it, the recent events, clearing. */
@Composable
fun DeveloperLogsScreen(onBack: () -> Unit) {
    val log = LocalDebugLog.current
    val context = LocalContext.current
    var showsEvents by rememberSaveable { mutableStateOf(false) }
    val toFile = L("nativeDevLogToFile")
    val share = L("nativeDevShareLog")
    val recent = L("nativeDevRecentEvents")
    val clear = L("nativeDevClearLog")
    SettingsSubPageHost(
        page = if (showsEvents) Unit else null,
        onClose = { showsEvents = false },
        base = {
            SettingsListPage(L("nativeDevLogs"), onBack) {
                section(footer = L("nativeDevLogsFooter")) {
                    row { OmiToggleRow(log.writesToFile, { log.writesToFile = it }) { Text(toFile, style = DS.Typography.body, color = DS.Palette.ink) } }
                    log.files.firstOrNull()?.let { file ->
                        row(onClick = { shareLogFile(context, file) }, separatorInset = OmiListMetrics.iconSeparatorInset) {
                            SettingsRowLabel(share, "square.and.arrow.up", tint = DS.Palette.agent, titleColor = DS.Palette.agent)
                        }
                    }
                    row(chevron = true, onClick = { showsEvents = true }) { Text(recent, style = DS.Typography.body, color = DS.Palette.ink) }
                }
                section {
                    val enabled = log.entries.isNotEmpty() || log.files.isNotEmpty()
                    row(enabled = enabled, onClick = { log.clear() }) { SettingsButtonText(clear, if (enabled) DS.Palette.live else DS.Palette.inkDisabled) }
                }
            }
        },
    ) { DebugLogScreen(source = null) { showsEvents = false } }
}

/** `ShareLink(item: file)`: the newest log file, through the share sheet (a copy in the cache dir). */
private fun shareLogFile(context: Context, file: java.io.File) {
    runCatching {
        val copy = file.copyTo(java.io.File(context.cacheDir, file.name), overwrite = true)
        val send = android.content.Intent(android.content.Intent.ACTION_SEND).setType("text/plain")
            .putExtra(android.content.Intent.EXTRA_STREAM, com.friend.ios.features.conversations.fileUri(context, copy))
            .addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
        context.startActivity(android.content.Intent.createChooser(send, null).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}

/** The recent log entries, newest first; [source] narrows it (the transcription log, `stt`). */
@Composable
fun DebugLogScreen(source: String?, onBack: () -> Unit) {
    val log = LocalDebugLog.current
    val context = LocalContext.current
    val entries = (source?.let { log.entries(it) } ?: log.entries).asReversed()
    val time = remember { java.text.DateFormat.getTimeInstance(java.text.DateFormat.MEDIUM) }
    val title = if (source == "stt") L("nativeTranscriptionLog") else L("nativeDevRecentEvents")
    val copy = L("copy")
    val trailing: @Composable androidx.compose.foundation.layout.RowScope.() -> Unit = {
        Text(
            copy,
            style = TextStyles.headline,
            color = if (entries.isEmpty()) DS.Palette.inkDisabled else DS.Palette.ink,
            modifier = Modifier.plainButton(enabled = entries.isNotEmpty()) { copyToClipboard(context, DebugLog.text(entries.asReversed())) },
        )
    }
    if (entries.isEmpty()) {
        SettingsPage(title, onBack, trailing = trailing) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                OmiEmptyState(L("nativeDevNoEvents"), "list.bullet.rectangle")
            }
        }
        return
    }
    SettingsListPage(title, onBack, trailing = trailing) {
        section {
            entries.forEach { entry ->
                row(key = entry.id) {
                    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm), verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                entry.level.rawValue,
                                style = DS.Typography.caption.copy(fontWeight = FontWeight.SemiBold),
                                color = if (entry.level == DebugLog.Entry.Level.Info) DS.Palette.inkSecondary else DS.Palette.live,
                            )
                            Text(entry.source, style = DS.Typography.caption, color = DS.Palette.inkTertiary)
                            Spacer(Modifier.weight(1f))
                            Text(time.format(java.util.Date.from(entry.date)), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
                        }
                        SelectionContainer { Text(entry.message, style = DS.Typography.callout, color = DS.Palette.ink) }
                    }
                }
            }
        }
    }
}
