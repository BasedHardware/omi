package com.friend.ios.system

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.runtime.snapshotFlow
import androidx.core.content.pm.ShortcutInfoCompat
import androidx.core.content.pm.ShortcutManagerCompat
import androidx.core.graphics.drawable.IconCompat
import com.friend.ios.MainActivity
import com.friend.ios.R
import com.friend.ios.core.QuickAction
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Conversation
import com.friend.ios.design.Strings
import com.friend.ios.service.stores.ConversationsStore
import com.friend.ios.service.stores.SessionStore
import com.friend.ios.service.stores.TasksStore
import com.friend.ios.system.widgets.LatestSnapshot
import com.friend.ios.system.widgets.UpNextPicker
import com.friend.ios.system.widgets.WidgetPublisher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/**
 * Port of `SystemIntegration.swift` (quick actions) and the widget half of `ExtrasBridge.swift`:
 * keeps what Android shows of Omi in step with the stores, the launcher shortcuts and the home
 * screen widgets. It only observes; nothing in the stores knows about it.
 */
class SystemIntegration(
    private val context: Context,
    private val scope: CoroutineScope,
    private val session: SessionStore,
    private val tasks: TasksStore,
    private val conversations: ConversationsStore,
    private val push: PushNotifications,
    /** The Omi for the battery widget; lazy so the device layer starts only when the shell does. */
    private val devices: () -> com.friend.ios.service.stores.DeviceStore,
) {
    private val widgets = WidgetPublisher(context, scope)
    private var quickActionsShown: Boolean? = null

    fun start() {
        scope.launch {
            snapshotFlow { session.phase }.distinctUntilChanged().collect { phase ->
                push.sessionChanged(phase)
                SupportChat.sessionChanged(phase)
                showQuickActions(phase is SessionStore.Phase.Ready)
                if (phase is SessionStore.Phase.SignedOut) widgets.clear()
            }
        }
        // The battery widget (`ExtrasBridge.publishWidgets`): the paired Omi, its level while connected.
        scope.launch {
            // Not before the shell: the debug extras (`omiFakeDevice`) are read once the activity starts.
            snapshotFlow { session.phase is SessionStore.Phase.Ready }.first { it }
            val store = devices()
            snapshotFlow { Triple(session.phase is SessionStore.Phase.Ready, store.paired, store.connection to store.battery) }
                .distinctUntilChanged()
                .collect { (ready, paired, state) ->
                    if (!ready) return@collect
                    val (connection, battery) = state
                    val connected = connection == com.friend.ios.service.stores.DeviceStore.Connection.Connected
                    widgets.publish(
                        paired?.let {
                            com.friend.ios.system.widgets.DeviceSnapshot(it.name.ifEmpty { "Omi" }, connected, if (connected) battery else null)
                        },
                    )
                }
        }
        scope.launch {
            snapshotFlow { Triple(session.phase is SessionStore.Phase.Ready, tasks.phase, tasks.tasks) }.collect { (ready, phase, items) ->
                if (ready && phase == TasksStore.Phase.Loaded) widgets.publish(upNext(items))
            }
        }
        scope.launch {
            snapshotFlow { Triple(session.phase is SessionStore.Phase.Ready, conversations.phase, conversations.conversations) }.collect { (ready, phase, items) ->
                if (ready && phase == ConversationsStore.Phase.Loaded) widgets.publish(latest(items))
            }
        }
    }

    private fun upNext(items: List<ActionItem>) = UpNextPicker.snapshot(
        items.filter { it.owner != ActionItem.Owner.Other }.map { UpNextPicker.Candidate(it.id, it.description, it.dueAt, !it.isCompleted) },
    )

    private fun latest(items: List<Conversation>): LatestSnapshot? = items.firstOrNull { it.status == Conversation.Status.Completed }?.let {
        LatestSnapshot(it.id, it.title, it.date, it.actionItemCount, it.duration)
    }

    // Quick actions: L("quickActionAskOmi") L("addTask") L("startRecording") L("nativeQuickActionMyOmi")

    private fun showQuickActions(signedIn: Boolean) {
        if (quickActionsShown == signedIn) return
        quickActionsShown = signedIn
        runCatching {
            if (signedIn) {
                ShortcutManagerCompat.setDynamicShortcuts(context, QuickAction.menuOrder.mapIndexed { index, action -> shortcut(action, index) })
            } else {
                ShortcutManagerCompat.removeAllDynamicShortcuts(context)
            }
        }
    }

    private fun shortcut(action: QuickAction, rank: Int): ShortcutInfoCompat {
        val title = Strings.get(
            context,
            when (action) {
                QuickAction.AskOmi -> "quickActionAskOmi"
                QuickAction.AddTask -> "addTask"
                QuickAction.StartRecording -> "startRecording"
                QuickAction.MyOmi -> "nativeQuickActionMyOmi"
            },
        )
        val icon = when (action) {
            QuickAction.AskOmi -> R.drawable.ic_shortcut_ask
            QuickAction.AddTask -> R.drawable.ic_shortcut_task
            QuickAction.StartRecording -> R.drawable.ic_shortcut_record
            QuickAction.MyOmi -> R.drawable.ic_shortcut_device
        }
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(action.link.url), context, MainActivity::class.java)
        return ShortcutInfoCompat.Builder(context, action.rawValue)
            .setShortLabel(title)
            .setRank(rank)
            .setIcon(IconCompat.createWithResource(context, icon))
            .setIntent(intent)
            .build()
    }
}
