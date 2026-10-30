package com.friend.ios.features.agent

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.omiSurface
import com.friend.ios.design.pressable
import com.friend.ios.service.LocalChatStore
import com.friend.ios.service.LocalSessionStore
import kotlinx.coroutines.launch
import java.time.LocalTime

/** Port of `ChatScreen+Empty.swift`: the loading and failed states, the greeting, the starters. */
@Composable
internal fun LoadingOrFailed(modifier: Modifier = Modifier) {
    val chat = LocalChatStore.current
    val scope = rememberCoroutineScope()
    if (chat.historyFailed) {
        Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            HStack(spacing = DS.Spacing.xs + 2.dp) {
                SFImage("wifi.exclamationmark", size = 14.sp, tint = DS.Palette.inkSecondary)
                Text(L("nativeChatHistoryFailed"), style = DS.Typography.callout, color = DS.Palette.inkSecondary)
            }
            OmiPillButton(L("retry")) { scope.launch { chat.retryHistory() } }
        }
    } else {
        Box(modifier) { OmiProgress() }
    }
}

@Composable
internal fun Greeting(modifier: Modifier = Modifier) {
    val chat = LocalChatStore.current
    val app = chat.chatApp
    if (app != null) {
        Text(
            L("nativeChatWithAppGreeting", app.name), style = DS.Typography.title, color = DS.Palette.ink,
            modifier = modifier.padding(top = DS.Spacing.xl).semantics { heading() },
        )
    } else {
        OmiGreeting(modifier)
    }
}

@Composable
private fun OmiGreeting(modifier: Modifier) {
    val session = LocalSessionStore.current
    val hour = LocalTime.now().hour
    val part = if (hour < 12) L("greetingMorning") else if (hour < 18) L("greetingAfternoon") else L("greetingEvening")
    val name = session.displayName?.split(" ")?.firstOrNull().orEmpty()
    val title = (if (name.isEmpty()) part else L("greetingWithName", part, name)) + "."
    Column(modifier.padding(top = DS.Spacing.xl).semantics { heading() }, verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        Text(title, style = DS.Typography.display, color = DS.Palette.ink)
        Text(L("whatDoYouWantToKnow"), style = TextStyles.title3, color = DS.Palette.inkSecondary)
    }
}

/** Omi's suggestions: about my day once there are conversations, otherwise about Omi. */
@Composable
internal fun Starters(hasConversations: Boolean, enabled: Boolean, onSend: (String) -> Unit) {
    val prompts = if (!hasConversations) {
        listOf(L("chatStarterPrompt.capabilities"), L("chatStarterPrompt.goal"))
    } else {
        listOf(L("askSuggestDecide"), L("askSuggestOwe"), L("askSuggestNotice"))
    }
    HStack(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = DS.Spacing.lg), spacing = DS.Spacing.sm) {
        for (prompt in prompts) {
            Box(
                Modifier
                    .pressable(enabled = enabled, pressedScale = 0.97f, pressedAlpha = 0.9f, haptic = false) { onSend(prompt) }
                    .heightIn(min = 40.dp)
                    .omiSurface(CircleShape)
                    .padding(horizontal = DS.Spacing.lg),
                contentAlignment = Alignment.Center,
            ) {
                Text(prompt, style = DS.Typography.callout, color = DS.Palette.ink, maxLines = 1)
            }
        }
    }
}
