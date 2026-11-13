package com.friend.ios.service.stores

import com.friend.ios.device.OmiGATT
import com.friend.ios.core.models.SpokenLanguage
import com.friend.ios.network.APIError
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.persistence.Preferences.NativeKey
import com.friend.ios.service.FakeAPI
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import com.friend.ios.service.stores.OnboardingStore.Step
import com.friend.ios.service.voice.GapSentence
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Port of `OnboardingStoreTests.swift` (and the button lessons of `ButtonTutorialStoreTests.swift`). */
class OnboardingStoreTest {
    private val scope = CoroutineScope(Dispatchers.Unconfined)

    private fun store(
        api: FakeAPI = fakeAPI(),
        prefs: Preferences = freshPreferences(),
        watch: Boolean = false,
        names: MutableList<String> = mutableListOf(),
    ) = OnboardingStore(
        api.client, prefs, scope, watchPaired = { watch }, updateDisplayName = { names += it }, phoneLanguage = { "de" },
    )

    @Test
    fun pathWithoutOmiLeavesTheOmiStepsOut() {
        val onboarding = store()
        onboarding.hasOmi = false
        assertEquals(
            listOf(Step.Name, Step.Language, Step.FoundOmi, Step.HasOmi, Step.Hello, Step.Voice, Step.Permissions, Step.Setup, Step.Ready),
            onboarding.path,
        )
    }

    @Test
    fun pathWithOmiHasEveryOmiStepButTheWatch() {
        val onboarding = store()
        onboarding.hasOmi = true
        assertTrue(onboarding.path.containsAll(listOf(Step.Pair, Step.Lights, Step.AskOmi, Step.VoiceReply, Step.DoublePress)))
        assertFalse(Step.Watch in onboarding.path)
        assertTrue(Step.Watch in store(watch = true).path)
    }

    @Test
    fun nextAndBackFollowThePath() {
        val onboarding = store()
        onboarding.step = Step.HasOmi
        onboarding.chooseOmi(false)
        assertEquals(Step.Hello, onboarding.step)
        onboarding.back()
        assertEquals(Step.HasOmi, onboarding.step)
        onboarding.chooseOmi(true)
        assertEquals(Step.Pair, onboarding.step)
        onboarding.continueWithoutOmi()
        assertEquals(Step.Hello, onboarding.step)
        assertEquals(false, onboarding.hasOmi)
        onboarding.step = Step.Name
        onboarding.back()
        assertEquals(Step.Name, onboarding.step)
        onboarding.step = Step.Ready
        onboarding.next()
        assertEquals(Step.Ready, onboarding.step)
    }

    @Test
    fun progressCountsTheStepOnThePath() {
        val onboarding = store()
        onboarding.hasOmi = false
        assertEquals(1.0 / 9, onboarding.progress, 1e-9)
        onboarding.step = Step.Ready
        assertEquals(1.0, onboarding.progress, 1e-9)
    }

    @Test
    fun stepNamesMatchTheIOSLaunchArgument() {
        assertEquals(Step.AskOmi, Step.from("askOmi"))
        assertEquals(Step.VoiceReply, Step.from("voiceReply"))
        assertEquals("foundOmi", Step.FoundOmi.rawName)
        assertNull(Step.from("nope"))
    }

    @Test
    fun languagesArePickedInOrderAndTakenOut() {
        val onboarding = store()
        assertEquals("de", onboarding.language) // nothing picked: the phone's language
        onboarding.toggleLanguage("en")
        onboarding.toggleLanguage("de")
        assertEquals(1, onboarding.rank("en"))
        assertEquals(2, onboarding.rank("de"))
        assertEquals("en", onboarding.language)
        onboarding.toggleLanguage("en")
        assertNull(onboarding.rank("en"))
        assertEquals(1, onboarding.rank("de"))
    }

    @Test
    fun languageRowsShowCommonFirstAndKeepASearchedPick() = runTest {
        val api = fakeAPI {
            "availableLanguages" returns listOf(
                SpokenLanguage("English", "en"), SpokenLanguage("German", "de"), SpokenLanguage("Spanish", "es"),
                SpokenLanguage("Japanese", "ja"), SpokenLanguage("French", "fr"),
            )
        }
        val onboarding = store(api)
        // Before the catalog: the common codes, the phone's own first, six in all.
        assertEquals(listOf("de", "en", "es", "fr", "pt", "it"), onboarding.languageRows().map { it.code })
        onboarding.loadLanguages()
        assertEquals(listOf("de", "en", "es", "fr"), onboarding.languageRows().map { it.code })
        assertEquals(listOf("ja"), onboarding.languageRows("japan").map { it.code })
        assertEquals(listOf("ja"), onboarding.languageRows("JA").map { it.code })
        onboarding.toggleLanguage("ja")
        assertEquals("ja", onboarding.languageRows().first().code)
    }

    @Test
    fun saveNameSplitsGivenAndFamily() = runTest {
        val prefs = freshPreferences()
        val names = mutableListOf<String>()
        val onboarding = store(prefs = prefs, names = names)
        onboarding.givenName = "  Ada Lovelace King "
        onboarding.saveName()
        assertEquals("Ada", prefs.string(Key.GivenName))
        assertEquals("Lovelace King", prefs.string(Key.FamilyName))
        assertEquals(listOf("Ada Lovelace King"), names)
        assertEquals(Step.Language, onboarding.step)
    }

    @Test
    fun saveNameIgnoresAnEmptyName() = runTest {
        val onboarding = store()
        onboarding.givenName = "   "
        onboarding.saveName()
        assertEquals(Step.Name, onboarding.step)
    }

    @Test
    fun saveLanguageSendsTheMainOneAndKeepsTheList() = runTest {
        val prefs = freshPreferences()
        val api = fakeAPI { "setPrimaryLanguage" returns Unit }
        val onboarding = store(api, prefs)
        onboarding.step = Step.Language
        onboarding.saveLanguage() // nothing picked: nothing sent
        assertTrue(api.called("setPrimaryLanguage").isEmpty())
        onboarding.toggleLanguage("es")
        onboarding.toggleLanguage("en")
        onboarding.saveLanguage()
        assertEquals(listOf(listOf<Any?>("es")), api.called("setPrimaryLanguage"))
        assertEquals("es", prefs.string(Key.UserPrimaryLanguage))
        assertEquals(listOf("es", "en"), prefs.strings(NativeKey.SpokenLanguages))
        assertTrue(prefs.bool(Key.HasSetPrimaryLanguage))
        assertEquals(Step.FoundOmi, onboarding.step)
    }

    @Test
    fun saveLanguageFailureStaysWithAMessage() = runTest {
        val api = fakeAPI { "setPrimaryLanguage" throws APIError.Http(500, "") }
        val onboarding = store(api)
        onboarding.step = Step.Language
        onboarding.toggleLanguage("en")
        onboarding.saveLanguage()
        assertEquals(Step.Language, onboarding.step)
        assertTrue(onboarding.errorMessage != null)
    }

    @Test
    fun saveSourceSendsItAndSkipSendsNothing() = runTest {
        val prefs = freshPreferences()
        val api = fakeAPI { "updateOnboarding" returns Unit }
        val onboarding = store(api, prefs)
        onboarding.step = Step.FoundOmi
        onboarding.saveSource("Reddit")
        assertEquals("Reddit", prefs.string(Key.FoundOmiSource))
        assertEquals(listOf(listOf<Any?>(null, "Reddit")), api.called("updateOnboarding"))
        assertEquals(Step.HasOmi, onboarding.step)
        onboarding.step = Step.FoundOmi
        onboarding.saveSource(null)
        assertEquals(1, api.called("updateOnboarding").size)
        assertEquals(Step.HasOmi, onboarding.step)
    }

    @Test
    fun voiceReplyStartsOffOnTheFirstRunAndShowsTheSavedChoiceOnAReplay() {
        val prefs = freshPreferences()
        val first = store(prefs = prefs)
        first.showVoiceReply()
        assertEquals(VoicePlaybackStore.ReplyMode.Off, first.voiceReplyMode)
        assertEquals(0, prefs.integer(Key.VoiceResponseMode, 1))
        first.chooseVoiceReply(VoicePlaybackStore.ReplyMode.Always)
        assertEquals(2, prefs.integer(Key.VoiceResponseMode, 1))

        val replayPrefs = freshPreferences()
        replayPrefs.set(Key.OnboardingCompleted, true)
        replayPrefs.set(Key.VoiceResponseMode, 2)
        val replay = store(prefs = replayPrefs)
        replay.showVoiceReply()
        assertEquals(VoicePlaybackStore.ReplyMode.Always, replay.voiceReplyMode)
    }

    // ButtonTutorialStore

    /** The real DeviceStore over the device tests' fake driver (never started: no Bluetooth). */
    private fun device() = DeviceStore({ FakeDriver() }, freshPreferences(), CoroutineScope(Dispatchers.Unconfined))

    private class FakeAsk : AskOmi {
        val actions = mutableListOf<ButtonAction>()
        override val phase: AskOmi.Phase = AskOmi.Phase.Idle
        override val lastExchange: AskOmi.Exchange? = null
        override val question = ""
        override val problem: AskOmi.Problem? = null
        override var isPractice = false
        override fun handle(action: ButtonAction) {
            actions += action
        }
    }

    @Test
    fun askLessonRoutesPressesToAskOmiAsPractice() {
        val device = device()
        val ask = FakeAsk()
        val tutorial = ButtonTutorialStore(device, ask)
        tutorial.begin(ButtonTutorialStore.Lesson.Ask)
        assertTrue(ask.isPractice)
        assertTrue(device.buttonInterceptor!!(OmiGATT.ButtonEvent.SingleTap))
        assertTrue(device.buttonInterceptor!!(OmiGATT.ButtonEvent.LongPress))
        assertTrue(device.buttonInterceptor!!(OmiGATT.ButtonEvent.Release))
        assertTrue(device.buttonInterceptor!!(OmiGATT.ButtonEvent.DoubleTap))
        assertEquals(listOf(ButtonAction.AskToggle, ButtonAction.AskHoldStart, ButtonAction.AskHoldEnd), ask.actions)
        // Leaving a lesson that is no longer the current one does not end the new one.
        tutorial.begin(ButtonTutorialStore.Lesson.DoublePress)
        tutorial.end(ButtonTutorialStore.Lesson.Ask)
        assertEquals(ButtonTutorialStore.Lesson.DoublePress, tutorial.lesson)
        tutorial.end()
        assertNull(tutorial.lesson)
        assertNull(device.buttonInterceptor)
        assertFalse(ask.isPractice)
        assertFalse(tutorial.handle(OmiGATT.ButtonEvent.SingleTap))
    }

    @Test
    fun doublePressLessonCountsAndPickingStartsOver() {
        val device = device()
        val tutorial = ButtonTutorialStore(device, FakeAsk())
        tutorial.begin(ButtonTutorialStore.Lesson.DoublePress)
        tutorial.handle(OmiGATT.ButtonEvent.SingleTap)
        assertTrue(tutorial.singlePressHint)
        tutorial.handle(OmiGATT.ButtonEvent.DoubleTap)
        tutorial.handle(OmiGATT.ButtonEvent.DoubleTap)
        assertFalse(tutorial.singlePressHint)
        assertEquals(2, tutorial.doublePresses)
        tutorial.choose(DoubleTapAction.Star)
        assertEquals(DoubleTapAction.Star, device.doubleTapAction)
        assertEquals(DoubleTapAction.Star, tutorial.doublePressAction)
        assertEquals(0, tutorial.doublePresses)
    }

    // GapSentence

    @Test
    fun gapSentenceFillsBlanksAndChecksWords() {
        val sentence = GapSentence("My name is ___ and I work as ___.")
        val match = sentence.match("my name is Ada and I work as an engineer")
        assertEquals(listOf("Ada", "an engineer"), match.blanks)
        assertTrue(match.isComplete)
        assertEquals(1.0, match.progress, 1e-9)
        val partial = sentence.match("my name is")
        assertFalse(partial.isComplete)
        assertEquals(listOf("", ""), partial.blanks)
    }

    @Test
    fun freeSentenceNeedsAFewWords() {
        assertFalse(GapSentence.free.match("hello there").isComplete)
        assertTrue(GapSentence.free.match("today I went running").isComplete)
        assertEquals(listOf<GapSentence.Part>(GapSentence.Part.Blank), GapSentence.free.parts)
    }

    @Test
    fun tokensFoldContractionsAndAccents() {
        assertEquals(listOf("i", "am"), GapSentence.tokens("I’m"))
        assertEquals(listOf("strasse"), GapSentence.tokens("Straße"))
        assertEquals(listOf("cafe"), GapSentence.tokens("café,"))
        assertTrue(GapSentence.similar("arbeite", "arbeiten"))
        assertFalse(GapSentence.similar("is", "it"))
    }
}
