package com.friend.ios.features.conversations

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import com.friend.ios.core.models.ChatContext
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.shareURL
import com.friend.ios.design.DSHaptics
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.features.components.copyToClipboard
import com.friend.ios.service.LocalChatStore
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalDeveloperStore
import kotlinx.coroutines.launch

// Port of `ConversationDetailMenu.swift`: the detail page's two toolbar buttons: Share (link, text,
// audio) and "..." (everything else). The actions live on `ConversationDetailState` (the screen's
// `@State`), so the menus, the page and the sheets share them.

/** The share button's menu: public link, text, SMS, audio. */
@Composable
fun shareMenu(state: ConversationDetailState): List<MenuSection> {
    val items = buildList {
        add(MenuItem(L("sharePublicLink"), "link") { state.requestShareLink() })
        add(MenuItem(L("nativeShareAsText"), "text.alignleft") { state.shareText() })
        add(MenuItem(L("shareViaSms"), "message") { state.extras.sharesBySMS = true })
        if (state.store.detail?.hasAudio == true) add(MenuItem(L("shareAudio"), "waveform") { state.shareAudio() })
    }
    return listOf(MenuSection(items = items))
}

/** The "..." menu. */
@Composable
fun detailMenu(state: ConversationDetailState): List<MenuSection> {
    val conversations = LocalConversationsStore.current
    val developer = LocalDeveloperStore.current
    val context = LocalContext.current
    val conversation = state.conversation
    val store = state.store
    val summaryCopied = L("summaryCopiedToClipboard")
    val transcriptCopied = L("transcriptCopiedToClipboard")
    val idCopied = L("nativeConversationIDCopied")
    val first = buildList {
        add(MenuItem(L("nativeAskOmiAboutThis"), "sparkles") { state.askOmi() })
        if (store.detail?.transcript?.isNotEmpty() == true) {
            add(
                MenuItem(L("nativeSearchTranscript"), "magnifyingglass") {
                    state.page = ConversationDetailState.Page.Transcript
                    state.searchesTranscript = true
                },
            )
        }
    }
    val organize = listOf(
        if (conversation.isStarred) {
            MenuItem(L("unstarConversation"), "star.slash") { state.scope.launch { conversations.setStarred(conversation.id, false) } }
        } else {
            MenuItem(L("starConversation"), "star") { state.scope.launch { conversations.setStarred(conversation.id, true) } }
        },
        MenuItem(L("moveToFolder"), "folder") { state.moving = true },
        MenuItem(L("renameConversation"), "pencil") {
            state.newTitle = conversation.title
            state.renaming = true
        },
    )
    val work = buildList {
        // Disabled while it runs: the item is left out (Compose menus have no disabled rows).
        if (!(store.isReprocessing || conversation.status == Conversation.Status.Processing)) {
            add(MenuItem(L("reprocessConversation"), "arrow.clockwise") { state.reprocess() })
        }
        addAll(extraMenuItems(state))
        add(MenuItem(L("copySummary"), "doc.on.doc") { state.copy(context, store.summaryText, summaryCopied) })
        if (store.detail?.transcript?.isNotEmpty() == true) {
            add(MenuItem(L("copyTranscript"), "text.quote") { state.copy(context, store.detail?.transcriptText ?: "", transcriptCopied) })
        }
        if (developer.showsConversationTools) {
            add(MenuItem(L("nativeCopyConversationID"), "number") { state.copy(context, conversation.id, idCopied) })
            add(MenuItem(L("testPrompt"), "text.badge.checkmark") { state.extras.testsPrompt = true })
        }
        if (conversation.visibility != Conversation.Visibility.Private) {
            add(MenuItem(L("makePrivate"), "lock") { state.scope.launch { conversations.setVisibility(conversation.id, Conversation.Visibility.Private) } })
        }
    }
    val delete = MenuItem(L("deleteConversation"), "trash", destructive = true) {
        // No dialog: Home shows "Conversation deleted · Undo" for a few seconds.
        val id = conversation.id
        state.onBack()
        conversations.deleteWithUndo(listOf(id))
    }
    return listOf(MenuSection(items = first), MenuSection(items = organize), MenuSection(items = work), MenuSection(items = listOf(delete)))
}

/** Points the chat at this conversation, then the shell opens it. */
@Composable
fun rememberAskOmi(state: ConversationDetailState, onAskOmi: () -> Unit): () -> Unit {
    val chat = LocalChatStore.current
    val untitled = L("untitledConversation")
    return {
        val conversation = state.conversation
        chat.context = ChatContext(ChatContext.Kind.Conversation, conversation.id, conversation.title.ifEmpty { untitled })
        onAskOmi()
    }
}

internal fun ConversationDetailState.copy(context: Context, text: String, notice: String) {
    if (text.isEmpty()) return
    copyToClipboard(context, text)
    haptics?.success()
    show(notice)
}

// Sharing

/** A private conversation asks first ("Anyone with the link can view"). */
internal fun ConversationDetailState.requestShareLink() {
    if (conversation.visibility == Conversation.Visibility.Private) confirmsShareLink = true else scope.launch { shareLink() }
}

/** Makes the link work, opens the share sheet, and goes back to private if nothing was shared. */
internal suspend fun ConversationDetailState.shareLink() {
    val list = conversations
    val id = conversation.id
    val wasPrivate = conversation.visibility == Conversation.Visibility.Private
    if (wasPrivate && !list.setVisibility(id, Conversation.Visibility.Shared)) {
        show(strings.urlNotShared)
        return
    }
    share(ShareRequest(listOf(Conversation.shareURL(id))) { shared ->
        if (wasPrivate && !shared) scope.launch { list.setVisibility(id, Conversation.Visibility.Private) }
    })
}

internal fun ConversationDetailState.shareText() {
    val text = listOf(conversation.title, store.summaryText).filter { it.isNotEmpty() }.joinToString("\n\n")
    share(ShareRequest(listOf(text)))
}

internal fun ConversationDetailState.shareAudio() {
    scope.launch {
        if (store.audio == com.friend.ios.service.stores.ConversationDetailStore.AudioState.Idle) {
            show(strings.preparingAudio)
            store.loadAudio()
        }
        val file = store.exportAudio() ?: return@launch show(strings.audioDownloadFailed)
        share(ShareRequest(listOf(file)))
    }
}

internal fun ConversationDetailState.reprocess() {
    haptics?.tap(DSHaptics.Style.Light)
    scope.launch { store.reprocess(conversations) }
}
