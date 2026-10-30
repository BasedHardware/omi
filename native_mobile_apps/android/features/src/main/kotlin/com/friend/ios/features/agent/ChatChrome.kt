package com.friend.ios.features.agent

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.size
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.friend.ios.design.CircleIconButton
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiCircleIcon
import com.friend.ios.design.OmiHairline
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.hex
import com.friend.ios.design.LocalOmiDark
import com.friend.ios.design.plainButton
import com.friend.ios.design.semibold
import com.friend.ios.service.LocalChatStore
import com.friend.ios.service.stores.ChatThreadFilter
import kotlinx.coroutines.launch

/**
 * What the app header shows on the Chat tab (iOS `MainTabView` with `tab == .chat`): the thread
 * search and the chat's "…" menu, before the shell's own settings button. The shell turns their
 * taps into [ChatScreenRequest]s for [ChatScreen].
 */
@Composable
fun ChatHeaderActions(onSearch: () -> Unit, onFilter: (ChatThreadFilter) -> Unit) {
    CircleIconButton("magnifyingglass", contentDescription = L("nativeChatSearch"), onClick = onSearch)
    ChatMenu(showsTalkTo = true, onFilter = onFilter)
}

/**
 * Port of `ChatMenu` (`ChatChrome.swift`). The chat's one "…" menu. On the Chat tab it sits in the
 * app header: who you talk to (Omi or a chat app, Flutter `chat_apps_drawer`), what to show (the
 * thread's filters), and Clear chat behind a confirmation (Flutter `chat/page`).
 */
@Composable
fun ChatMenu(modifier: Modifier = Modifier, showsTalkTo: Boolean = true, onFilter: ((ChatThreadFilter) -> Unit)? = null) {
    val chat = LocalChatStore.current
    val voice = com.friend.ios.service.LocalVoicePlaybackStore.current
    val scope = rememberCoroutineScope()
    var confirmsClear by remember { mutableStateOf(false) }
    var clearFailed by remember { mutableStateOf(false) }
    val hasMessages = chat.hasLoaded && chat.messages.isNotEmpty()
    val talkTo = L("nativeTalkTo")
    val noApps = L("nativeNoChatApps")
    val showOnly = L("nativeChatShowOnly")
    val clear = L("clearChat")
    val filterTitles = ChatThreadFilter.entries.associateWith { filterTitle(it) }
    androidx.compose.runtime.LaunchedEffect(showsTalkTo) { if (showsTalkTo) chat.loadChatApps() }

    val sections = buildList {
        if (showsTalkTo) {
            // Omi, or one of the enabled apps that can chat; each keeps its own history.
            val rows = listOf(MenuItem("Omi", if (chat.chatApp == null) "checkmark" else null) { scope.launch { chat.talk(null) } }) +
                chat.chatApps.map { app -> MenuItem(app.name, if (chat.chatApp?.id == app.id) "checkmark" else null) { scope.launch { chat.talk(app) } } } +
                (if (chat.chatApps.isEmpty()) listOf(MenuItem(noApps) {}) else emptyList())
            add(MenuSection(header = talkTo, items = rows))
        }
        if (onFilter != null && hasMessages) {
            add(MenuSection(header = showOnly, items = ChatThreadFilter.entries.map { filter -> MenuItem(filterTitles.getValue(filter), filterSymbol(filter)) { onFilter(filter) } }))
        }
        if (hasMessages) add(MenuSection(items = listOf(MenuItem(clear, "trash", destructive = true) { if (!chat.isStreaming) confirmsClear = true })))
    }
    // Its value says who the chat talks to (iOS `.accessibilityValue`).
    val talksTo = if (showsTalkTo) chat.chatApp?.name ?: "Omi" else ""
    OmiMenu(sections, modifier.semantics { stateDescription = talksTo }, contentDescription = L("moreOptions")) {
        val app = chat.chatApp
        if (app != null && showsTalkTo) {
            // The chosen chat app's picture stands for the menu.
            androidx.compose.foundation.layout.Box(
                androidx.compose.ui.Modifier.size(DS.Size.headerButton),
                contentAlignment = androidx.compose.ui.Alignment.Center,
            ) { ChatAppPicture(app, 26.dp) }
        } else {
            OmiCircleIcon("ellipsis")
        }
    }
    if (confirmsClear) {
        ConfirmationDialog(
            title = clear,
            message = L("clearChatConfirm"),
            action = clear,
            onConfirm = {
                voice?.stop()
                scope.launch { clearFailed = !chat.clearChat() }
            },
            onDismiss = { confirmsClear = false },
        )
    }
    if (clearFailed) {
        AlertDialog(L("nativeChatClearFailed"), L("ok")) { clearFailed = false }
    }
}

@Composable
fun filterTitle(filter: ChatThreadFilter): String = when (filter) {
    ChatThreadFilter.Approvals -> L("nativeChatFilterApprovals")
    ChatThreadFilter.Drafts -> L("nativeChatFilterDrafts")
    ChatThreadFilter.Jobs -> L("nativeChatFilterJobs")
    ChatThreadFilter.Files -> L("nativeChatFilterFiles")
}

fun filterSymbol(filter: ChatThreadFilter): String = when (filter) {
    ChatThreadFilter.Approvals -> "checkmark.seal"
    ChatThreadFilter.Drafts -> "square.and.pencil"
    ChatThreadFilter.Jobs -> "sparkles"
    ChatThreadFilter.Files -> "paperclip"
}

/** Under the header while the phone has no connection (Flutter `ChatOfflineHint`). */
@Composable
fun OfflineHint(modifier: Modifier = Modifier) {
    HStack(
        modifier
            .fillMaxWidth()
            .background(DS.Palette.fill, CircleShape)
            .padding(horizontal = DS.Spacing.md, vertical = DS.Spacing.sm),
        spacing = DS.Spacing.xs + 2.dp,
    ) {
        Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
            HStack(spacing = DS.Spacing.xs + 2.dp) {
                SFImage("wifi.slash", size = 12.sp, tint = DS.Palette.inkSecondary)
                Text(L("chatOfflineHint"), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
            }
        }
    }
}

/** `NetworkMonitor`: whether the phone has no usable connection, kept current while on screen. */
@Composable
fun rememberIsOffline(): Boolean {
    val context = LocalContext.current
    var offline by remember { mutableStateOf(false) }
    DisposableEffect(context) {
        val manager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
        fun current(): Boolean {
            val caps = manager?.getNetworkCapabilities(manager.activeNetwork) ?: return true
            return !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        }
        offline = runCatching { current() }.getOrDefault(false)
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) { offline = false }
            override fun onLost(network: Network) { offline = runCatching { current() }.getOrDefault(false) }
            override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                offline = !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            }
        }
        runCatching { manager?.registerDefaultNetworkCallback(callback) }
        onDispose { runCatching { manager?.unregisterNetworkCallback(callback) } }
    }
    return offline
}

/** `.confirmationDialog(titleVisibility: .visible)`: the iOS action sheet at the bottom. */
@Composable
fun ConfirmationDialog(title: String, message: String, action: String, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    val dark = LocalOmiDark.current
    val sheet = if (dark) hex(0x2C2C2E) else hex(0xF9F9F9)
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Box(Modifier.fillMaxSize().plainButton(onClick = onDismiss), contentAlignment = Alignment.BottomCenter) {
            Column(Modifier.navigationBarsPadding().padding(horizontal = DS.Spacing.sm, vertical = DS.Spacing.sm), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                Column(Modifier.fillMaxWidth().background(sheet, ContinuousRoundedShape(14.dp))) {
                    Column(Modifier.fillMaxWidth().padding(DS.Spacing.lg), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                        Text(title, style = TextStyles.footnote.semibold(), color = DS.Palette.inkTertiary, textAlign = TextAlign.Center)
                        Text(message, style = TextStyles.footnote, color = DS.Palette.inkTertiary, textAlign = TextAlign.Center)
                    }
                    OmiHairline()
                    SheetButton(action, DS.Palette.live) {
                        onDismiss()
                        onConfirm()
                    }
                }
                Box(Modifier.fillMaxWidth().background(sheet, ContinuousRoundedShape(14.dp))) {
                    SheetButton(L("cancel"), DS.Palette.agent, semibold = true, onClick = onDismiss)
                }
            }
        }
    }
}

@Composable
private fun SheetButton(title: String, color: Color, semibold: Boolean = false, onClick: () -> Unit) {
    Box(Modifier.fillMaxWidth().heightIn(min = 57.dp).plainButton(onClick = onClick), contentAlignment = Alignment.Center) {
        Text(title, style = if (semibold) TextStyles.title3.semibold() else TextStyles.title3, color = color)
    }
}

/** `.alert(title) { OK }`. */
@Composable
fun AlertDialog(title: String, ok: String, onDismiss: () -> Unit) {
    val dark = LocalOmiDark.current
    Dialog(onDismissRequest = onDismiss) {
        Column(Modifier.background(if (dark) hex(0x2C2C2E) else hex(0xF2F2F2), ContinuousRoundedShape(14.dp))) {
            Text(title, style = TextStyles.headline, color = DS.Palette.ink, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(DS.Spacing.lg))
            OmiHairline()
            Box(Modifier.fillMaxWidth().heightIn(min = 44.dp).plainButton(onClick = onDismiss), contentAlignment = Alignment.Center) {
                Text(ok, style = TextStyles.body.semibold(), color = DS.Palette.agent)
            }
        }
    }
}
