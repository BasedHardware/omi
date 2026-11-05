package com.friend.ios.features.onboarding

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.FiniteAnimationSpec
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiColorScheme
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.service.LocalSessionStore
import com.friend.ios.service.stores.OnboardingStore
import com.friend.ios.service.stores.OnboardingStore.Step
import kotlinx.coroutines.delay

internal object OnboardingScreenDefaults {
    /** Quick and crisp: no bounce, done in about 0.3 s, so a tap feels answered at once. */
    fun <T> stepAnimation(): FiniteAnimationSpec<T> = spring(dampingRatio = 1f, stiffness = DS.Motion.stiffness(0.3f))
}

/**
 * Port of `OnboardingScreen.swift`. First run, after consent (PLAN.md 4.6). About you (name,
 * language, how you heard of Omi), then your Omi: with one, pair it, learn its light and whisper
 * to it; without one the phone microphone stands in. Either way the voice sample is recorded
 * through what the user will actually wear, then permissions and "Setting up your Omi".
 *
 * The look is calm and dark: a quiet label over a large headline, at most one line under it,
 * soft rounded boxes, the pendant still (nothing blinks or pulses), a thin progress line and one
 * white button at the same place on every step. Steps change in about 0.3 s; only the content
 * changes, the chrome stays.
 */
@Composable
fun OnboardingScreen(store: OnboardingStore) {
    val session = LocalSessionStore.current
    // Onboarding is always dark and pure black, whatever the app's appearance (design decision, 2026-10-07).
    OmiColorScheme(dark = true) {
        Column(Modifier.fillMaxSize().background(Color.Black).systemBarsPadding().imePadding()) {
            if (store.step != Step.Setup && store.step != Step.Ready) Chrome(store)
            val shift = with(LocalDensity.current) { 24.dp.roundToPx() }
            AnimatedContent(
                targetState = store.step,
                transitionSpec = {
                    // The old step is gone in a tenth of a second, so two headlines never sit on top
                    // of each other; the new one slides in from the side it comes from.
                    val forward = targetState.ordinal >= initialState.ordinal
                    (fadeIn(tween(300, delayMillis = 60)) + slideInHorizontally(OnboardingScreenDefaults.stepAnimation()) { if (forward) shift else -shift })
                        .togetherWith(fadeOut(tween(100)))
                },
                modifier = Modifier.fillMaxWidth().weight(1f),
                label = "onboarding-step",
            ) { step ->
                Box(Modifier.fillMaxSize()) {
                    when (step) {
                        Step.Name -> NameStep(store)
                        Step.Language -> LanguageStep(store)
                        Step.FoundOmi -> SourceStep(store)
                        Step.HasOmi -> HasOmiStep(store)
                        Step.Pair -> PairStep(store)
                        Step.Lights -> LightsStep(onContinue = store::next)
                        Step.Hello -> HelloStep(store)
                        Step.Voice -> VoiceStep(store)
                        Step.AskOmi, Step.VoiceReply, Step.DoublePress, Step.Watch -> OmiButtonAndWatchSteps(store, step)
                        Step.Permissions -> PermissionsStep(onContinue = store::next)
                        Step.Setup -> SetupStep(onFinished = {
                            session.saveOnboardingCompleted()
                            store.next()
                        })
                        Step.Ready -> ReadyFlow(name = store.givenName, hasOmi = store.hasOmi == true) { topic ->
                            session.settingsAfterIntroduction = topic
                            session.completeOnboarding()
                        }
                    }
                }
            }
        }
    }
    DisposableEffect(store) { onDispose { store.voice?.stop() } }
    // Replayed from Settings: what is said here is practice, not a conversation. The app restarts
    // capture from a connected Omi when it opens again.
    val capture = com.friend.ios.service.LocalCaptureStore.current
    LaunchedEffect(Unit) { if (capture.isLive) capture.stop() }
    LaunchedEffect(store) {
        // --es omiOnboardingAutoAdvance <seconds>: walks forward on its own, then back once
        // (QA of the step transitions, recorded without tapping).
        val seconds = DebugLaunch.string("omiOnboardingAutoAdvance")?.toDoubleOrNull() ?: return@LaunchedEffect
        if (seconds <= 0) return@LaunchedEffect
        for (forward in listOf(true, true, true, false)) {
            delay((seconds * 1000).toLong())
            if (forward) store.next() else store.back()
        }
    }
}

/**
 * Back on the left, the progress line across. Back stays in its slot when hidden so the
 * line never jumps.
 */
@Composable
private fun Chrome(store: OnboardingStore) {
    val first = store.step == Step.Name
    HStack(
        Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.lg).padding(top = DS.Spacing.sm).height(36.dp),
        spacing = DS.Spacing.md,
    ) {
        Box(
            Modifier.size(36.dp).alpha(if (first) 0f else 1f).plainButton(enabled = !first) {
                store.voice?.stop()
                store.back()
            },
            contentAlignment = Alignment.Center,
        ) {
            SFImage("chevron.left", size = 17.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkSecondary, contentDescription = if (first) null else L("back"))
        }
        OnboardingProgress(store.progress, Modifier.weight(1f))
        Box(Modifier.width(36.dp).height(1.dp))
    }
}

/**
 * `ConnectsPairedOmi`: the Omi steps work with a connected Omi: one paired but not connected (a
 * replay, or a step opened directly) is connected on arrival.
 */
@Composable
internal fun ConnectsPairedOmi() {
    val device = com.friend.ios.service.LocalDeviceStore.current
    LaunchedEffect(device) {
        if (device.paired != null && device.connection == com.friend.ios.service.stores.DeviceStore.Connection.Disconnected) device.start()
    }
}

/** A step whose store is missing passes straight on (`Color.clear.onAppear(perform: store.next)`). */
@Composable
internal fun PassOn(next: () -> Unit) {
    var passed by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        if (!passed) {
            passed = true
            next()
        }
    }
}
