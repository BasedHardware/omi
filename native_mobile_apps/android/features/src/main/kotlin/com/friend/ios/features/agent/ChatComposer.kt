package com.friend.ios.features.agent

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ChatContext
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.ChatQuote
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.service.LocalChatStore
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private val FIELD_HEIGHT = DS.Size.composer
private val SEND_SIZE = 36.dp

/**
 * Port of `ChatComposer.swift`. The chat's composer, as in Messages: "+" (photo, camera, file) on
 * the left, the rounded field with the send arrow inside it, and one mic on the right. The arrow
 * only shows once something is typed (and as stop while Omi answers); the field keeps room for
 * it, so it never jumps. The mic: tap to dictate into the field (tap again to stop), or hold to
 * talk and let go to send. The chat places it at the bottom inset, so it sits right on the keyboard.
 */
@Composable
fun ChatComposer(
    draft: String,
    onDraftChange: (String) -> Unit,
    focusRequester: FocusRequester,
    onFocusChange: (Boolean) -> Unit,
    isDictating: Boolean,
    canDictate: Boolean,
    canSend: Boolean,
    /** The microphone level while dictating (the stop circle breathes with it). */
    level: Float,
    /** Listening started by holding the mic: letting go sends. */
    sendsAfterDictation: Boolean,
    onSend: () -> Unit,
    /** `thenSend`: held (talk to Omi) rather than tapped (dictate into the field). */
    onDictate: (thenSend: Boolean) -> Unit,
    onStopDictation: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chat = LocalChatStore.current
    Column(
        modifier.padding(horizontal = DS.Spacing.lg).padding(top = DS.Spacing.sm, bottom = DS.Spacing.sm),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        val target = chat.replyingTo
        AnimatedVisibility(target != null, enter = slideInVertically { it } + fadeIn(), exit = slideOutVertically { it } + fadeOut()) {
            if (target != null) ReplyLine(target) { chat.replyingTo = null }
        }
        chat.context?.let { ContextLine(it) { chat.context = null } }
        if (chat.attachments.isNotEmpty()) AttachmentStrip()
        Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm), verticalAlignment = Alignment.Bottom) {
            AttachmentButton()
            Field(draft, onDraftChange, focusRequester, onFocusChange, isDictating, canSend, onSend, Modifier.weight(1f))
            if (canDictate || isDictating) {
                ComposerMic(isDictating, level, sendsAfterDictation, isEnabled = !chat.isStreaming || isDictating, onDictate, onStopDictation)
            }
        }
    }
}

@Composable
private fun Field(
    draft: String,
    onDraftChange: (String) -> Unit,
    focusRequester: FocusRequester,
    onFocusChange: (Boolean) -> Unit,
    isDictating: Boolean,
    canSend: Boolean,
    onSend: () -> Unit,
    modifier: Modifier,
) {
    val shape = ContinuousRoundedShape(FIELD_HEIGHT / 2)
    val style = DS.Typography.bubble.copy(color = DS.Palette.ink)
    Box(
        modifier
            .heightIn(min = FIELD_HEIGHT)
            .background(DS.Palette.card, shape)
            .border(0.5.dp, DS.Palette.cardStroke, shape),
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .padding(start = DS.Spacing.lg, end = SEND_SIZE + DS.Spacing.sm)
                .padding(vertical = 11.dp)
                .align(Alignment.CenterStart),
        ) {
            if (draft.isEmpty()) {
                Text(if (isDictating) L("nativeVoiceListeningPlaceholder") else L("askAnything"), style = style, color = DS.Palette.inkTertiary, maxLines = 1)
            }
            BasicTextField(
                value = draft,
                onValueChange = { value ->
                    // Return sends (`.submitLabel(.send)` + `.onSubmit`): a typed line break is not kept.
                    if (value.length == draft.length + 1 && value.count { it == '\n' } > draft.count { it == '\n' }) {
                        onDraftChange(draft)
                        onSend()
                    } else {
                        onDraftChange(value)
                    }
                },
                textStyle = style,
                minLines = 1,
                maxLines = 6,
                cursorBrush = SolidColor(DS.Palette.agent),
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences, imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { onSend() }),
                modifier = Modifier
                    .fillMaxWidth()
                    .focusRequester(focusRequester)
                    .onFocusChanged { onFocusChange(it.isFocused) },
            )
        }
        SendButton(draft, canSend, onSend, Modifier.align(Alignment.BottomEnd).padding(4.dp))
    }
}

/** Sends what is typed; stops while Omi answers. Hidden while there is nothing to send. */
@Composable
private fun SendButton(draft: String, canSend: Boolean, onSend: () -> Unit, modifier: Modifier) {
    val chat = LocalChatStore.current
    val shows = chat.isStreaming || draft.isNotBlank()
    val visibility by animateFloatAsState(if (shows) 1f else 0f, DS.Motion.snappy(), label = "send")
    val label = if (chat.isStreaming) L("nativeStopAnswer") else L("nativeSend")
    Box(
        modifier
            .graphicsLayer {
                alpha = visibility
                val scale = 0.85f + 0.15f * visibility
                scaleX = scale
                scaleY = scale
            }
            .size(SEND_SIZE)
            // Hidden from TalkBack while there is nothing to send.
            .then(if (shows) Modifier.plainButton(enabled = canSend || chat.isStreaming, onClick = onSend) else Modifier.clearAndSetSemantics {})
            .background(DS.Palette.agent.copy(alpha = if (canSend || chat.isStreaming) 1f else 0.35f), CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        SFImage(
            if (chat.isStreaming) "stop.fill" else "arrow.up",
            size = if (chat.isStreaming) 12.sp else 15.sp,
            weight = FontWeight.Bold,
            tint = DS.Palette.onAgent,
            contentDescription = label,
        )
    }
}

/** The message the question replies to, removable. */
@Composable
private fun ReplyLine(target: ChatMessage, onCancel: () -> Unit) {
    HStack(Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.sm), spacing = DS.Spacing.sm) {
        QuoteLine(ChatQuote.replyingTo(target), Modifier.weight(1f))
        SFImage("xmark.circle.fill", tint = DS.Palette.inkTertiary, modifier = Modifier.plainButton(onClick = onCancel), contentDescription = L("nativeChatCancelReply"))
    }
}

/** What the question is about (a conversation or a task), removable. */
@Composable
private fun ContextLine(context: ChatContext, onRemove: () -> Unit) {
    HStack(Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.sm).padding(top = DS.Spacing.xs), spacing = DS.Spacing.xs + 2.dp) {
        SFImage(if (context.kind == ChatContext.Kind.Conversation) "bubble.left" else "checklist", size = 12.sp, tint = DS.Palette.agent)
        Text(context.title, style = DS.Typography.caption, color = DS.Palette.agent, maxLines = 1, modifier = Modifier.weight(1f))
        SFImage("xmark.circle.fill", size = 13.sp, tint = DS.Palette.agent, modifier = Modifier.plainButton(onClick = onRemove), contentDescription = L("nativeRemoveContext"))
    }
}

/**
 * The one voice button: tap to dictate into the field (tap again to stop), hold to talk and let
 * go to send. While listening it turns into the stop circle and breathes with the voice.
 */
@Composable
private fun ComposerMic(
    isDictating: Boolean,
    level: Float,
    sendsAfterDictation: Boolean,
    isEnabled: Boolean,
    onDictate: (Boolean) -> Unit,
    onStop: () -> Unit,
) {
    var isPressed by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val label = if (isDictating) (if (sendsAfterDictation) L("nativeSend") else L("nativeStopDictation")) else L("nativeDictate")
    val hint = if (isDictating) "" else L("nativeChatHoldToTalk")
    val scale by animateFloatAsState(if (isDictating) 1f + minOf(0.15f, level * 3) else if (isPressed) 0.92f else 1f, DS.Motion.snappy(), label = "mic")
    Box(
        Modifier
            .graphicsLayer {
                scaleX = scale
                scaleY = scale
            }
            .alpha(if (isEnabled) 1f else 0.4f)
            // One button for TalkBack: a double tap dictates (or stops), the hint tells about holding.
            .semantics {
                role = Role.Button
                contentDescription = label
                if (hint.isNotEmpty()) stateDescription = hint
                if (isEnabled) {
                    onClick {
                        if (isDictating) onStop() else onDictate(false)
                        true
                    }
                }
            }
            .size(DS.Size.composer)
            .background(if (isDictating) DS.Palette.ink else DS.Palette.card, CircleShape)
            .then(if (isDictating) Modifier else Modifier.border(0.5.dp, DS.Palette.cardStroke, CircleShape))
            .pointerInput(isEnabled, isDictating) {
                if (!isEnabled) return@pointerInput
                detectTapGestures(onPress = {
                    isPressed = true
                    var holding = false
                    var hold: Job? = null
                    if (!isDictating) {
                        hold = scope.launch {
                            delay(350)
                            holding = true
                            onDictate(true)
                        }
                    }
                    tryAwaitRelease()
                    isPressed = false
                    hold?.cancel()
                    when {
                        // Letting go ends listening; the question goes out (`sendsAfterDictation`).
                        holding -> onStop()
                        isDictating -> onStop()
                        else -> onDictate(false)
                    }
                })
            },
        contentAlignment = Alignment.Center,
    ) {
        SFImage(
            if (isDictating) "stop.fill" else "mic",
            size = if (isDictating) 13.sp else 18.sp,
            weight = if (isDictating) FontWeight.Bold else FontWeight.Normal,
            tint = if (isDictating) DS.Palette.onAccent else DS.Palette.ink,
        )
    }
}
