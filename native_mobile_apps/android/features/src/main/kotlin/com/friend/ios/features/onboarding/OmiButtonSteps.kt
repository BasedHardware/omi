package com.friend.ios.features.onboarding

import com.friend.ios.service.stores.NoAskOmi
import com.friend.ios.service.stores.DoubleTapAction
import com.friend.ios.service.stores.DeviceStore
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.TextStyles
import com.friend.ios.design.bold
import com.friend.ios.design.medium
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.service.stores.AskOmi
import com.friend.ios.service.stores.ButtonTutorialStore
import com.friend.ios.service.stores.VoicePlaybackStore

/**
 * "Ask Omi a question" (Flutter `single_press_step`): press once, speak, pause (or press again).
 * The words show as they are said, the question really goes to Omi, and its answer shows here
 * (the next step can read it aloud). A question without an answer says why; Skip stays.
 */
@Composable
internal fun AskOmiStep(tutorial: ButtonTutorialStore, onContinue: () -> Unit) {
    val ask = tutorial.askOmi ?: NoAskOmi
    val devices = tutorial.devices
    val haptics = rememberHaptics()
    /** The exchange from before this step: only a new one counts. */
    val earlier = remember { ask.lastExchange }
    var started by remember { mutableStateOf(false) }
    val answer = ask.lastExchange?.takeIf { started && it != earlier && ask.phase == AskOmi.Phase.Idle }
    OnboardingLayout(
        kicker = L("nativeKickerYourOmi"),
        title = if (answer == null) L("nativePressOnceTitle") else L("nativeOmiAnswered"),
        subtitle = if (answer == null) L("nativePressOnceShort") else null,
        button = StepButton(L("continueButton"), isEnabled = answer != null, action = onContinue),
        secondary = if (answer == null) StepButton(L("skip"), action = onContinue) else null,
    ) {
        if (answer != null) {
            AnswerCard(answer)
        } else {
            PendantImage(120.dp) {
                Text(
                    L("deviceOnboardingAllSetSinglePressBadge"),
                    style = TextStyles.footnote.bold().copy(fontFeatureSettings = "tnum"),
                    color = DS.Palette.onAccent,
                    modifier = Modifier.background(DS.Palette.ink, CircleShape).padding(horizontal = DS.Spacing.sm, vertical = DS.Spacing.xxs),
                )
            }
            Live(ask, devices)
        }
    }
    DisposableEffect(tutorial) {
        started = true
        tutorial.begin(ButtonTutorialStore.Lesson.Ask)
        onDispose { tutorial.end(ButtonTutorialStore.Lesson.Ask) }
    }
    LaunchedEffect(answer != null) { if (answer != null) haptics.success() }
    ConnectsPairedOmi()
}

/** What happens right now: a hint, the words of the question, Omi thinking, or why it failed. */
@Composable
private fun Live(ask: AskOmi, devices: DeviceStore) {
    when (ask.phase) {
        is AskOmi.Phase.Listening -> QuestionCard(L("nativeListening"), ask.question, L("nativeAskYourQuestion"), thinking = false)
        AskOmi.Phase.Sending -> QuestionCard(L("nativeOmiThinking"), ask.question, "", thinking = true)
        AskOmi.Phase.Idle -> {
            val line = when {
                devices.connection != DeviceStore.Connection.Connected ->
                    StatusLine(L("nativeOmiOnAndNearby"), "antenna.radiowaves.left.and.right.slash", DS.Palette.warning)
                ask.problem == AskOmi.Problem.NothingHeard -> StatusLine(L("nativeAskNothingHeard"), "ear", DS.Palette.warning)
                ask.problem == AskOmi.Problem.NoAnswer -> StatusLine(L("nativeAskNoAnswer"), "exclamationmark.bubble", DS.Palette.warning)
                else -> StatusLine(L("nativePressOnceToAsk"), "hand.tap", DS.Palette.inkSecondary)
            }
            line.View(Modifier.padding(horizontal = DS.Spacing.gutter))
        }
    }
}

/** The question as it is spoken (or sent), in quotes, with a small label above it. */
@Composable
private fun QuestionCard(label: String, question: String, placeholder: String, thinking: Boolean) {
    Column(Modifier.padding(horizontal = DS.Spacing.gutter).onboardingCard(padding = DS.Spacing.xl), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        HStack(spacing = DS.Spacing.sm) {
            if (thinking) OmiProgress(Modifier.size(14.dp)) else Box(Modifier.size(7.dp).background(DS.Palette.live, CircleShape))
            Text(label, style = TextStyles.footnote.semibold(), color = DS.Palette.inkSecondary)
        }
        Text(
            if (question.isEmpty()) placeholder else "“$question”",
            style = TextStyles.title3.medium(),
            color = if (question.isEmpty()) DS.Palette.inkTertiary else DS.Palette.ink,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

/** The question, a hairline, Omi's answer. */
@Composable
private fun AnswerCard(exchange: AskOmi.Exchange) {
    Column(Modifier.padding(horizontal = DS.Spacing.gutter).onboardingCard(padding = DS.Spacing.xl), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        if (exchange.question.isNotEmpty()) {
            Text("“${exchange.question}”", style = TextStyles.subheadline, color = DS.Palette.inkSecondary, maxLines = 2)
            Box(Modifier.fillMaxWidth().height(0.5.dp).background(DS.Palette.ink.copy(alpha = 0.08f)))
        }
        Text(VoicePlaybackStore.speakableText(exchange.answer), style = TextStyles.body, color = DS.Palette.ink, maxLines = 9)
    }
}

/**
 * "Customize double tap" (Flutter `double_press_config_step`): the same choice as My Devices >
 * Controls > Double tap, then a press to try it. Practice presses only count; nothing ends or mutes.
 */
@Composable
internal fun DoublePressStep(tutorial: ButtonTutorialStore, onContinue: () -> Unit) {
    val haptics = rememberHaptics()
    val devices = tutorial.devices
    OnboardingLayout(
        kicker = L("nativeKickerYourOmi"),
        title = L("nativePressTwiceTitle"),
        subtitle = L("nativeDoublePressShort"),
        button = StepButton(L("continueButton"), action = onContinue),
    ) {
        val action = tutorial.doublePressAction
        RowList(
            listOf(
                { ChoiceRow("stop.circle", L("nativePressTwiceEnd"), action == DoubleTapAction.EndConversation) { tutorial.choose(DoubleTapAction.EndConversation) } },
                { ChoiceRow("mic.slash", L("nativePressTwiceMute"), action == DoubleTapAction.ToggleMute) { tutorial.choose(DoubleTapAction.ToggleMute) } },
                { ChoiceRow("star", L("nativePressTwiceStar"), action == DoubleTapAction.Star) { tutorial.choose(DoubleTapAction.Star) } },
            ),
        )
        val line = when {
            devices.connection != DeviceStore.Connection.Connected ->
                StatusLine(L("nativeOmiOnAndNearby"), "antenna.radiowaves.left.and.right.slash", DS.Palette.warning)
            tutorial.singlePressHint -> StatusLine(L("nativeDoublePressSingleHint"), "hand.tap", DS.Palette.warning)
            tutorial.doublePresses > 0 -> StatusLine(L("nativeDoublePressWorked"), "checkmark.circle.fill", DS.Palette.success)
            else -> StatusLine(L("nativePressTwiceTry"), "hand.tap", DS.Palette.inkSecondary)
        }
        line.View(Modifier.padding(horizontal = DS.Spacing.gutter))
    }
    DisposableEffect(tutorial) {
        tutorial.begin(ButtonTutorialStore.Lesson.DoublePress)
        onDispose { tutorial.end(ButtonTutorialStore.Lesson.DoublePress) }
    }
    LaunchedEffect(tutorial.doublePresses) { if (tutorial.doublePresses > 0) haptics.success() }
    ConnectsPairedOmi()
}
