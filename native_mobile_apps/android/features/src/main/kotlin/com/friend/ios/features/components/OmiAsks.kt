package com.friend.ios.features.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.friend.ios.core.models.DeviceToolRequest
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.L
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.conversations.SheetBar
import com.friend.ios.features.conversations.SheetBarButton
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.stores.DeviceToolChoice
import com.friend.ios.service.stores.PendingDeviceTool
import com.friend.ios.service.stores.answer
import kotlinx.coroutines.launch

/**
 * Port of `OmiAsks.swift`. "Omi asks": the words and choices for a device tool call Omi is waiting
 * on mid-run (a message to send, which contact, a permission). Home's For you card and the run's
 * detail show the same thing; nothing happens until the user taps a choice.
 */
class OmiAsksPresentation(
    val title: String,
    val subtitle: String,
    /** The task it is for, as the card's quiet line. */
    val source: String,
    val choices: List<Choice>,
) {
    class Choice(val title: String, val isPrimary: Boolean, val kind: Kind) {
        sealed interface Kind {
            data class Answer(val choice: DeviceToolChoice) : Kind
            /** Change the message first (`OmiAsksEditSheet`). */
            data object Edit : Kind
        }

        val id: String get() = title
    }

    companion object {
        val kicker: DecisionCard.Kicker
            @Composable get() = DecisionCard.Kicker("questionmark.bubble", L("nativeOmiAsksKicker"), DS.Palette.agent)
    }
}

/** The words and choices for [pending] (`OmiAsksPresentation.init(_:)`). */
@Composable
fun omiAsksPresentation(pending: PendingDeviceTool): OmiAsksPresentation {
    val request = pending.request
    val source = if (pending.taskTitle.isEmpty()) "" else L("nativeOmiAsksFor", pending.taskTitle)
    val notNow = OmiAsksPresentation.Choice(L("notNow"), false, OmiAsksPresentation.Choice.Kind.Answer(DeviceToolChoice.Decline))
    val allow = OmiAsksPresentation.Choice(L("nativeOmiAsksAllow"), true, OmiAsksPresentation.Choice.Kind.Answer(DeviceToolChoice.Allow))
    return when {
        request.tool == DeviceToolRequest.Tool.ProposeMessage -> OmiAsksPresentation(
            title = L("nativeOmiAsksSendTo", request.recipients.joinToString(", ")),
            subtitle = "\u201C${request.text.replace("\n", " ")}\u201D",
            source = source,
            choices = listOf(
                OmiAsksPresentation.Choice(L("nativeOmiAsksSend"), true, OmiAsksPresentation.Choice.Kind.Answer(DeviceToolChoice.Send(request.text))),
                OmiAsksPresentation.Choice(L("edit"), false, OmiAsksPresentation.Choice.Kind.Edit),
                notNow,
            ),
        )
        request.tool == DeviceToolRequest.Tool.SearchContacts && pending.needsContactsAccess ->
            OmiAsksPresentation(L("nativeOmiAsksLookUp", request.query), L("nativeOmiAsksOnlyThePick"), source, listOf(allow, notNow))
        request.tool == DeviceToolRequest.Tool.SearchContacts && pending.matches.isEmpty() -> OmiAsksPresentation(
            L("nativeOmiAsksNoMatch", request.query), L("nativeOmiAsksGoOnWithout"), source,
            listOf(OmiAsksPresentation.Choice(L("nativeOmiAsksGoOn"), true, OmiAsksPresentation.Choice.Kind.Answer(DeviceToolChoice.Decline))),
        )
        request.tool == DeviceToolRequest.Tool.SearchContacts -> OmiAsksPresentation(
            L("nativeOmiAsksWhichOne", request.query), L("nativeOmiAsksOnlyThePick"), source,
            pending.matches.take(2).mapIndexed { index, contact ->
                OmiAsksPresentation.Choice(contact.name, index == 0, OmiAsksPresentation.Choice.Kind.Answer(DeviceToolChoice.Pick(contact)))
            } + notNow,
        )
        request.tool == DeviceToolRequest.Tool.RequestPermission ->
            OmiAsksPresentation(L("nativeOmiAsksContactsAccess"), L("nativeOmiAsksOnlyThePick"), source, listOf(allow, notNow))
        else -> OmiAsksPresentation(
            L("nativeOmiAsksKicker"), "", source,
            listOf(OmiAsksPresentation.Choice(L("notNow"), true, OmiAsksPresentation.Choice.Kind.Answer(DeviceToolChoice.Decline))),
        )
    }
}

/**
 * "Omi asks" as a decision card: the question, the message or what it needs, the task it is for,
 * and the choices. Edit opens the message to change before the messaging app. A run's question
 * goes back to its run (`AgentStore`); the chat passes its own [onAnswer] (and gets the compact card).
 *
 * @param onOpen the tap on the card when it has several choices (Home: the run it belongs to).
 */
@Composable
fun OmiAsksCard(
    pending: PendingDeviceTool,
    modifier: Modifier = Modifier,
    onOpen: (() -> Unit)? = null,
    onAnswer: (suspend (DeviceToolChoice) -> Unit)? = null,
) {
    val agent = LocalAgentStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var editing by remember(pending.id) { mutableStateOf(false) }
    val presentation = omiAsksPresentation(pending)

    fun answer(choice: DeviceToolChoice) {
        scope.launch { if (onAnswer != null) onAnswer(choice) else agent.answer(pending, choice) }
    }

    fun choose(choice: OmiAsksPresentation.Choice) {
        when (val kind = choice.kind) {
            OmiAsksPresentation.Choice.Kind.Edit -> editing = true
            is OmiAsksPresentation.Choice.Kind.Answer -> {
                haptics.selection()
                answer(kind.choice)
            }
        }
    }

    val pills = presentation.choices.map { choice -> DecisionCard.Pill(choice.title, choice.isPrimary) { choose(choice) } }
    DecisionCard(
        kicker = OmiAsksPresentation.kicker,
        title = presentation.title,
        subtitle = presentation.subtitle,
        source = presentation.source,
        pills = if (pills.size > 1) pills else emptyList(),
        compact = onAnswer != null,
        onTap = if (pills.size == 1) ({ presentation.choices.firstOrNull()?.let { choose(it) }; Unit }) else onOpen,
        modifier = modifier.testTag("omiAsks.${pending.id}"),
    )
    if (editing) {
        OmiAsksEditSheet(pending, onDismiss = { editing = false }) { text -> answer(DeviceToolChoice.Send(text)) }
    }
}

/** The proposed message, editable, before the messaging app opens (where the user sends it). */
@Composable
fun OmiAsksEditSheet(pending: PendingDeviceTool, onDismiss: () -> Unit, onSend: (String) -> Unit) {
    var text by rememberSaveable(pending.id) { mutableStateOf(pending.request.text) }
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar(
            title = L("edit"),
            leading = { SheetBarButton(L("cancel"), onClick = onDismiss) },
            trailing = {
                SheetBarButton(L("nativeOmiAsksSend"), enabled = text.isNotBlank(), prominent = true) {
                    val message = text
                    onDismiss()
                    onSend(message)
                }
            },
        )
        Column(Modifier.fillMaxWidth().padding(DS.Spacing.gutter), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            androidx.compose.material3.Text(
                L("nativeOmiAsksSendTo", pending.request.recipients.joinToString(", ")),
                style = DS.Typography.caption, color = DS.Palette.inkSecondary,
            )
            BasicTextField(
                value = text,
                onValueChange = { text = it },
                textStyle = DS.Typography.body.copy(color = DS.Palette.ink),
                cursorBrush = SolidColor(DS.Palette.accent),
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 160.dp)
                    .background(DS.Palette.card, ContinuousRoundedShape(DS.Radius.card))
                    .padding(DS.Spacing.sm),
            )
            androidx.compose.material3.Text(L("nativeOmiAsksComposerHint"), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
        }
    }
}
