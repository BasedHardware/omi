package com.friend.ios.features.onboarding

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.medium
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.service.stores.OnboardingStore
import com.friend.ios.service.stores.VoiceIntroStore
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * "Whisper to your Omi" (or "Say something" on the phone): everything said appears live, word
 * by word, utterance after utterance. The session keeps running into the voice step.
 */
@Composable
internal fun HelloStep(store: OnboardingStore) {
    val voice = store.voice ?: return PassOn(store::next)
    val haptics = rememberHaptics()
    val heard = voice.heardSomething
    val device = store.voiceSource == VoiceIntroStore.Source.Device
    OnboardingLayout(
        kicker = L("nativeKickerTryIt"),
        title = if (heard) L("nativeOmiHearsYouTitle") else if (device) L("nativeWhisperToYourOmi") else L("nativeSaySomethingTitle"),
        subtitle = if (heard) L("nativeOmiHearsYouBody") else L("nativeWhisperShort"),
        button = StepButton(L("continueButton"), isEnabled = heard, action = store::next),
        secondary = if (heard) null else StepButton(L("skip"), action = store::next),
    ) {
        VoiceLiveCard(voice, voice.transcript, if (device) L("nativeWhisperPlaceholder") else L("saySomething"))
    }
    LaunchedEffect(Unit) { voice.start(store.voiceSource, store.language) }
    LaunchedEffect(heard) { if (heard) haptics.success() }
}

/** Three sentences out loud through the same microphone; the audio becomes the voice profile. */
@Composable
internal fun VoiceStep(store: OnboardingStore) {
    val voice = store.voice ?: return PassOn(store::next)
    VoiceFlow(voice, store.voiceSource, store.language, savesAnswers = true, onDone = store::next, onSkip = store::next, laterTitle = L("nativeSetUpVoiceLater"))
}

/**
 * Makes the listening session of Settings' "Record your voice again" (the app supplies
 * `AppEnvironment.makeVoiceIntro`, as iOS's shell hands Settings its `voiceScreen`). Null hides
 * the row, as on iOS without a voice screen.
 */
val LocalVoiceIntroFactory = staticCompositionLocalOf<(() -> VoiceIntroStore)?> { null }

/**
 * Recording the voice again from Settings: the same three sentences, through the Omi when it is
 * connected, else the phone. Pushed inside Settings.
 */
@Composable
fun VoiceProfileScreen(voice: VoiceIntroStore, source: VoiceIntroStore.Source, language: String, onDismiss: () -> Unit) {
    VoiceFlow(voice, source, language, savesAnswers = false, onDone = onDismiss, onSkip = onDismiss, laterTitle = L("cancel"))
    DisposableEffect(voice) { onDispose { voice.stop() } }
}

@Composable
private fun VoiceFlow(
    voice: VoiceIntroStore,
    source: VoiceIntroStore.Source,
    language: String,
    savesAnswers: Boolean,
    onDone: () -> Unit,
    onSkip: () -> Unit,
    laterTitle: String,
) {
    val scope = rememberCoroutineScope()
    when (voice.phase) {
        VoiceIntroStore.Phase.Saved -> VoiceSaved(voice, savesAnswers, onDone)
        VoiceIntroStore.Phase.Saving -> OnboardingLayout(kicker = L("nativeKickerYourVoice"), title = L("nativeSavingVoice")) {
            Box(Modifier.fillMaxWidth().padding(top = DS.Spacing.section), contentAlignment = Alignment.Center) { OmiProgress(Modifier.size(36.dp)) }
        }
        VoiceIntroStore.Phase.Failed(VoiceIntroStore.Failure.Upload) -> OnboardingLayout(
            kicker = L("nativeKickerYourVoice"), title = L("nativeVoiceNotSaved"), subtitle = L("nativeVoiceNotSavedBody"),
            button = StepButton(L("retry"), action = { scope.launch { voice.retryUpload() } }),
            secondary = StepButton(laterTitle, action = onSkip),
        ) {}
        else -> Prompting(voice, source, language, onSkip)
    }
}

/** The gap sentences: name, work, free time, and the extra one (literal keys, so the catalog has them). */
private val templates = listOf("nativeVoiceGap_name", "nativeVoiceGap_work", "nativeVoiceGap_free")
private const val EXTRA = "nativeVoiceGap_more"
/**
 * What to talk about, in the app's language, where the sentences have no translation into the
 * language the user speaks.
 */
private val topics = listOf("nativeVoiceTopic_name", "nativeVoiceTopic_work", "nativeVoiceTopic_free")
private const val EXTRA_TOPIC = "nativeVoiceTopic_more"

/**
 * One sentence at a time, filling in as it is said; on by itself after a pause. When the sample
 * is still short, one more sentence with an example ("Today I ___.").
 */
@Composable
private fun Prompting(voice: VoiceIntroStore, source: VoiceIntroStore.Source, language: String, onSkip: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val total = templates.size
    /**
     * The sentences in the language the user speaks (an English speaker on a German phone reads
     * English sentences, the recognizer listens in English); null when they are not translated.
     */
    val spokenTemplates = remember(language) {
        val sentences = (templates + EXTRA).mapNotNull { localized(context, it, language) }
        if (sentences.size == total + 1) sentences else null
    }
    val isLast = voice.promptIndex >= total - 1
    val topicKey = if (spokenTemplates != null) null else if (voice.needsMore) EXTRA_TOPIC else topics[minOf(voice.promptIndex, total - 1)]
    val topic = topicKey?.let { L(it) }

    suspend fun advance() {
        haptics.tap()
        if (isLast || voice.needsMore) voice.saveVoice() else voice.nextPrompt()
    }

    OnboardingLayout(
        kicker = L("nativeKickerYourVoice"), title = L("nativeLetOmiLearnYourVoice"),
        subtitle = if (spokenTemplates == null) L("nativeVoiceTalkAbout") else L("nativeVoiceReadAloud"),
        // Sentences move on by themselves after a pause; the button is for when they do not.
        button = StepButton(
            if (isLast || voice.needsMore) L("nativeSaveMyVoice") else L("nextButton"),
            isEnabled = voice.canAdvance,
            action = { scope.launch { advance() } },
        ),
        secondary = StepButton(L("nativeSetUpVoiceLater"), action = {
            voice.stop()
            onSkip()
        }),
    ) {
        Column(
            Modifier.padding(horizontal = DS.Spacing.gutter).onboardingCard(padding = DS.Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg),
        ) {
            SentenceSteps(voice.promptIndex, total, voice.match?.progress ?: 0.0, voice.needsMore)
            Text(
                if (voice.needsMore) L("nativeVoiceOneMoreExample") else L("nativeVoiceSentenceOf", "${minOf(voice.promptIndex + 1, total)}", "$total"),
                style = TextStyles.footnote.semibold(), color = DS.Palette.inkSecondary,
            )
            AnimatedContent(
                targetState = if (voice.needsMore) -1 else voice.promptIndex,
                transitionSpec = { (slideInVertically(DS.Motion.standard()) { it / 2 } + fadeIn(DS.Motion.standard())).togetherWith(androidx.compose.animation.ExitTransition.None) },
                label = "voice-sentence",
            ) { _ ->
                Column(Modifier.fillMaxWidth().heightIn(min = 120.dp), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                    if (topic != null) Text(topic, style = DS.Typography.sectionTitle, color = DS.Palette.ink)
                    voice.match?.let { GapSentenceText(it) }
                }
            }
            ListeningLine(voice)
        }
    }
    LaunchedEffect(Unit) {
        // Arriving here directly (debug, or back from a later step) starts the session too.
        voice.start(source, language)
        if (spokenTemplates != null) {
            voice.beginTraining(spokenTemplates.take(total), extra = spokenTemplates.last())
        } else {
            voice.beginTraining(List(total) { "___" }, extra = "___")
        }
    }
    // A finished sentence is a clear step: a soft tap as the next one comes up.
    var firstIndex by remember { mutableStateOf(true) }
    LaunchedEffect(voice.promptIndex) { if (firstIndex) firstIndex = false else haptics.soft() }
    LaunchedEffect(voice.phase) { if (voice.phase == VoiceIntroStore.Phase.Saved) haptics.success() }
}

/**
 * "Omi knows your voice": a calm check and one line, then on by itself. In onboarding the answers
 * are kept as memories in the background, as Flutter keeps them by default; nothing to review.
 */
@Composable
private fun VoiceSaved(voice: VoiceIntroStore, savesAnswers: Boolean, onContinue: () -> Unit) {
    val scope = rememberCoroutineScope()
    var left by remember { mutableStateOf(false) }
    fun leave() {
        if (left) return
        left = true
        onContinue()
    }
    OnboardingLayout(
        kicker = L("nativeKickerYourVoice"), title = L("nativeVoiceSaved"), subtitle = L("nativeVoiceSavedBody"),
        button = StepButton(L("continueButton"), action = ::leave),
        centered = true,
    ) {
        Box(Modifier.fillMaxWidth().padding(top = DS.Spacing.section), contentAlignment = Alignment.Center) {
            SFImage("checkmark.circle", size = 72.sp, weight = FontWeight.ExtraLight, tint = DS.Palette.success)
        }
    }
    LaunchedEffect(Unit) {
        if (savesAnswers) scope.launch { voice.saveAnswers() }
        delay(2000)
        leave()
    }
}

/**
 * The live transcript: where the audio comes from, the input level, and every word as it arrives
 * (the newest at the bottom, older ones fading off the top).
 */
@Composable
internal fun VoiceLiveCard(voice: VoiceIntroStore, text: String, placeholder: String) {
    Column(
        Modifier.padding(horizontal = DS.Spacing.gutter).onboardingCard(padding = DS.Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg),
    ) {
        ListeningLine(voice)
        val style = TextStyles.title3.medium().copy(lineHeight = (TextStyles.title3.lineHeight.value + 3).sp)
        Box(Modifier.fillMaxWidth().heightIn(min = 130.dp)) {
            if (text.isEmpty()) Text(placeholder, style = style, color = DS.Palette.inkTertiary)
            else Text(text.takeLast(220), style = style, color = DS.Palette.ink)
        }
        if (voice.phase == VoiceIntroStore.Phase.Failed(VoiceIntroStore.Failure.Input)) {
            HStack(spacing = DS.Spacing.xs) {
                SFImage("exclamationmark.triangle.fill", size = 13.sp, tint = DS.Palette.warning)
                Text(L("nativeMicrophoneUnavailable"), style = TextStyles.footnote, color = DS.Palette.warning)
            }
        }
    }
}
