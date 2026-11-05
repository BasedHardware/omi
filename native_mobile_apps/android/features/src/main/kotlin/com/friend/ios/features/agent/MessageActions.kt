package com.friend.ios.features.agent

import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.copyToClipboard
import com.friend.ios.service.LocalChatStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

/** Wire keys the backend stores for a "not helpful" rating (Flutter `FeedbackReason`). */
private val feedbackReasons = listOf(
    "too_verbose" to "feedbackReasonTooVerbose",
    "incorrect_or_hallucination" to "feedbackReasonIncorrect",
    "not_helpful_or_irrelevant" to "feedbackReasonNotHelpful",
    "didnt_follow_instructions" to "feedbackReasonIgnoredInstructions",
    "other" to "cancelReasonOther",
)

/** An answer's menu: its sections, and the reasons behind "Not helpful" (iOS: a submenu). */
internal class AnswerMenuActions(val sections: () -> List<MenuSection>, val reasons: List<MenuSection>)

/**
 * Port of `AnswerMenu` (`MessageActions.swift`). An answer's long-press menu, everything Flutter's
 * `MessageActionBar` offered and more, so the thread carries no rows of icons: reply, copy,
 * share, read aloud, the rating with its reasons, and delete on this phone. [title] (when it was
 * sent) heads the menu.
 */
@Composable
internal fun answerMenu(
    message: ChatMessage,
    onReply: () -> Unit,
    onDelete: () -> Unit,
    title: String,
    scope: CoroutineScope,
    onNotHelpful: () -> Unit,
): AnswerMenuActions {
    val chat = LocalChatStore.current
    val context = LocalContext.current
    val haptics = rememberHaptics()
    val labels = MenuLabels.current()
    val share = L("share")
    val voice = com.friend.ios.service.LocalVoicePlaybackStore.current
    val reading = voice?.playingID == message.id
    val readAloud = if (reading) L("nativeStopReading") else L("nativeReadAloud")
    val helpful = L("helpful")
    val notHelpful = L("notHelpful")
    val reasonTitles = feedbackReasons.map { L(it.second) }

    fun rate(value: Int, reason: String? = null) = scope.launch {
        if (chat.rate(message.id, value, reason) && value != 0) haptics.success()
    }

    val sections = {
        buildList {
            add(
                MenuSection(
                    header = title,
                    items = listOf(
                        MenuItem(labels.reply, "arrowshape.turn.up.left", action = onReply),
                        MenuItem(labels.copy, "doc.on.doc") {
                            copyToClipboard(context, message.text)
                            haptics.success()
                        },
                        MenuItem(share, "square.and.arrow.up") {
                            val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, message.text)
                            context.startActivity(Intent.createChooser(send, null).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        },
                        MenuItem(readAloud, if (reading) "stop.fill" else "speaker.wave.2") {
                            haptics.selection()
                            voice?.toggle(message)
                        },
                    ),
                ),
            )
            if (message.serverID != null) {
                add(
                    MenuSection(
                        items = listOf(
                            MenuItem(helpful, if (message.rating == 1) "hand.thumbsup.fill" else "hand.thumbsup") { rate(if (message.rating == 1) 0 else 1) },
                            if (message.rating == -1) {
                                MenuItem(notHelpful, "hand.thumbsdown.fill") { rate(0) }
                            } else {
                                MenuItem(notHelpful, "hand.thumbsdown", action = onNotHelpful)
                            },
                        ),
                    ),
                )
            }
            add(MenuSection(items = listOf(MenuItem(labels.hide, "eye.slash", action = onDelete))))
        }
    }
    val reasons = listOf(
        MenuSection(header = notHelpful, items = feedbackReasons.mapIndexed { index, (key, _) -> MenuItem(reasonTitles[index]) { rate(-1, key) } }),
    )
    return AnswerMenuActions(sections, reasons)
}
