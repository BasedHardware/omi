package com.friend.ios.features.onboarding

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiColorScheme
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.service.stores.ButtonTutorialStore
import com.friend.ios.service.stores.OnboardingStore
import com.friend.ios.service.stores.OnboardingStore.Step
import com.friend.ios.service.stores.VoicePlaybackStore

/**
 * The onboarding steps after the voice sample: the Omi's button (ask, hear the answer, double
 * press) and the watch. A step whose store is missing passes straight on.
 */
@Composable
internal fun OmiButtonAndWatchSteps(store: OnboardingStore, step: Step) {
    when (step) {
        Step.AskOmi -> store.buttonTutorial?.let { AskOmiStep(it, onContinue = store::next) } ?: PassOn(store::next)
        Step.VoiceReply -> {
            VoiceReplyStep(
                mode = store.voiceReplyMode ?: VoicePlaybackStore.ReplyMode.Off,
                lastAnswer = store.buttonTutorial?.askOmi?.lastExchange?.answer,
                voice = store.playback,
                onChoose = store::chooseVoiceReply,
                onContinue = store::next,
            )
            DisposableEffect(Unit) {
                store.showVoiceReply()
                onDispose {}
            }
        }
        Step.DoublePress -> store.buttonTutorial?.let { DoublePressStep(it, onContinue = store::next) } ?: PassOn(store::next)
        else -> WatchStep(store.watch, onContinue = store::next)
    }
}

/**
 * Port of `OmiButtonTutorialScreen.swift`. My Devices > How to use your Omi (Flutter's device
 * tutorial, reopened from device settings): the three button lessons again, over the app,
 * closable at any point.
 */
@Composable
fun OmiButtonTutorialScreen(tutorial: ButtonTutorialStore, voice: VoicePlaybackStore, onDismiss: () -> Unit) {
    var lesson by remember { mutableStateOf(Lesson.Ask) }
    var mode by remember { mutableStateOf(voice.replyMode) }
    OmiColorScheme(dark = true) {
        Column(Modifier.fillMaxSize().background(DS.Palette.background).systemBarsPadding()) {
            HStack(Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.lg).padding(top = DS.Spacing.sm).height(36.dp), spacing = DS.Spacing.md) {
                OnboardingProgress((Lesson.entries.indexOf(lesson) + 1).toDouble() / Lesson.entries.size, Modifier.weight(1f))
                Box(Modifier.size(36.dp).plainButton(onClick = onDismiss), contentAlignment = Alignment.Center) {
                    SFImage("xmark", size = 17.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkSecondary, contentDescription = L("close"))
                }
            }
            AnimatedContent(
                targetState = lesson,
                transitionSpec = { fadeIn(tween(280)).togetherWith(fadeOut(tween(280))) },
                modifier = Modifier.fillMaxWidth().weight(1f),
                label = "tutorial-lesson",
            ) { current ->
                when (current) {
                    Lesson.Ask -> AskOmiStep(tutorial) { lesson = Lesson.VoiceReply }
                    Lesson.VoiceReply -> VoiceReplyStep(
                        mode = mode, lastAnswer = tutorial.askOmi?.lastExchange?.answer, voice = voice,
                        onChoose = { chosen ->
                            mode = chosen
                            voice.setReplyMode(chosen)
                        },
                        onContinue = { lesson = Lesson.DoublePress },
                    )
                    Lesson.DoublePress -> DoublePressStep(tutorial, onContinue = onDismiss)
                }
            }
        }
    }
    DisposableEffect(tutorial) {
        onDispose {
            tutorial.end()
            voice.stop()
        }
    }
}

private enum class Lesson { Ask, VoiceReply, DoublePress }
