package com.friend.ios.system

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import android.text.format.DateUtils
import androidx.compose.runtime.snapshotFlow
import com.friend.ios.R
import com.friend.ios.core.DeepLink
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.system.widgets.WidgetStrings
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Port of `ExtrasBridge.publishAgent` with `AgentViews.swift`: Android's stand-in for the Live
 * Activity of a task Omi works on. While a run is going, an ongoing notification (promoted to a
 * Live Update on Android 16) shows "Omi is working", the task, the time working and the current
 * step, with how many other runs are going. When it ends the card says how it went and stays a
 * few minutes; away from the app the end banner (`AgentNotifications.runEnded`) says it instead.
 */
class AgentRunNotifier(
    private val context: Context,
    private val agent: AgentStore,
    private val scope: CoroutineScope,
    private val now: () -> Long = System::currentTimeMillis,
    private val isInForeground: () -> Boolean = DeviceToolsPerformer::isInForeground,
) {
    /** The run the card follows, until it ends. */
    private var shownRunID: String? = null
    private var sent: LiveActivity.Run? = null
    private var desired: LiveActivity.Run? = null
    private val throttle = ActivityUpdateThrottle()
    private var retry: Job? = null

    fun start() {
        scope.launch { snapshotFlow { agent.runs }.collect { publish() } }
    }

    private fun publish() {
        val active = agent.activeRuns
        val run = active.firstOrNull { it.id == shownRunID } ?: active.firstOrNull()
        if (run != null) {
            shownRunID = run.id
            show(card(run, LiveActivity.Phase.Working, others = active.size - 1))
            return
        }
        val id = shownRunID ?: return
        shownRunID = null
        // Dismissed in the app: nothing left to show.
        val ended = agent.runs[id]
        if (ended == null) {
            end()
            return
        }
        val phase = if (ended.state is AgentStore.RunState.Done) LiveActivity.Phase.Finished else LiveActivity.Phase.Failed
        finish(card(ended, phase, others = 0))
    }

    private fun card(run: AgentStore.Run, phase: LiveActivity.Phase, others: Int): LiveActivity.Run {
        val step = (run.state as? AgentStore.RunState.Working)?.step.orEmpty()
        return LiveActivity.Run.of(run.id, phase, run.startedAt.toEpochMilli(), run.taskTitle, step, others, now())
    }

    /** `LiveActivityController.show`: urgent changes merge bursts, a new step waits its turn. */
    private fun show(card: LiveActivity.Run) {
        desired = card
        if (card == sent) return
        val urgent = sent?.let { !card.isRoutineChange(it) } ?: true
        val wait = throttle.decide(urgent, now())
        if (wait == null) {
            retry?.cancel()
            retry = null
            post(card, ongoing = true)
            sent = card
            throttle.didSend(now())
        } else if (retry == null) {
            retry = scope.launch {
                delay(wait)
                retry = null
                desired?.let(::show)
            }
        }
    }

    /** The last card: in front it stays [LiveActivity.FINISHED_LINGER_MILLIS]; away the end banner says it. */
    private fun finish(card: LiveActivity.Run) {
        retry?.cancel()
        retry = null
        desired = null
        sent = null
        throttle.reset()
        if (isInForeground()) post(card, ongoing = false) else cancel()
    }

    private fun end() {
        retry?.cancel()
        retry = null
        desired = null
        sent = null
        throttle.reset()
        cancel()
    }

    private fun cancel() {
        context.getSystemService(NotificationManager::class.java)?.cancel(TAG, 0)
    }

    private fun post(card: LiveActivity.Run, ongoing: Boolean) {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        createChannel(manager)
        runCatching { manager.notify(TAG, 0, build(card, ongoing)) }
    }

    private fun createChannel(manager: NotificationManager) {
        // Default importance without sound: Android 16 promotes only channels above IMPORTANCE_MIN.
        val channel = NotificationChannel(CHANNEL_ID, widget("Omi is working"), NotificationManager.IMPORTANCE_DEFAULT).apply {
            setShowBadge(false)
            setSound(null, null)
            enableVibration(false)
        }
        manager.createNotificationChannel(channel)
    }

    private fun build(card: LiveActivity.Run, ongoing: Boolean): Notification {
        val working = card.phase == LiveActivity.Phase.Working
        val detail = detail(card)
        val builder = Notification.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_stat_launcher)
            .setContentTitle(widget(heading(card.phase)))
            .setContentText(card.title)
            // The task over its step, as on the lock screen card.
            .setStyle(Notification.BigTextStyle().bigText(listOf(card.title, detail).filter { it.isNotEmpty() }.joinToString("\n")))
            .setOngoing(ongoing)
            .setAutoCancel(!ongoing)
            .setOnlyAlertOnce(true)
            .setCategory(if (working) Notification.CATEGORY_PROGRESS else Notification.CATEGORY_STATUS)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setContentIntent(PushNotifications.openIntent(context, TAG, DeepLink.Task(card.id)))
        if (working) {
            builder.setWhen(card.startedAtMillis).setShowWhen(true).setUsesChronometer(true)
            builder.setProgress(0, 0, true)
        } else {
            builder.setShowWhen(false)
            card.elapsedSeconds?.let { builder.setSubText(DateUtils.formatElapsedTime(it.toLong())) }
            builder.setTimeoutAfter(LiveActivity.FINISHED_LINGER_MILLIS)
        }
        if (ongoing && Build.VERSION.SDK_INT >= 36) {
            // Android 16 Live Updates (see `LiveCaptureNotification`): the chip says "Working".
            builder.addExtras(android.os.Bundle().apply { putBoolean("android.requestPromotedOngoing", true) })
            builder.setShortCriticalText(widget(shortHeading(card.phase)))
        }
        return builder.build()
    }

    /** `AgentSnapshot.detail`: the step (or what to do now), with how many other runs are going. */
    private fun detail(card: LiveActivity.Run): String {
        val base = when (card.phase) {
            LiveActivity.Phase.Finished -> widget("Tap to see what Omi did")
            LiveActivity.Phase.Failed -> widget("Tap to open the task")
            LiveActivity.Phase.Working -> card.step.ifEmpty { widget("Getting started…") }
        }
        if (card.otherRuns <= 0 || card.phase != LiveActivity.Phase.Working) return base
        return "$base · " + WidgetStrings.get(context, "+%d more", card.otherRuns)
    }

    private fun heading(phase: LiveActivity.Phase) = when (phase) {
        LiveActivity.Phase.Finished -> "Omi finished"
        LiveActivity.Phase.Failed -> "Omi couldn't finish"
        LiveActivity.Phase.Working -> "Omi is working"
    }

    /** The status-bar chip's title, where "Omi is working" does not fit. */
    private fun shortHeading(phase: LiveActivity.Phase) = when (phase) {
        LiveActivity.Phase.Finished -> "Done"
        LiveActivity.Phase.Failed -> "Stuck"
        LiveActivity.Phase.Working -> "Working"
    }

    private fun widget(key: String) = WidgetStrings.get(context, key)

    private companion object {
        const val CHANNEL_ID = "omi_agent_runs"
        const val TAG = "omi.agent.live"
    }
}
