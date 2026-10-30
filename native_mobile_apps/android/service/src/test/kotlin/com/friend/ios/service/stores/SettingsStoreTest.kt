package com.friend.ios.service.stores

import com.friend.ios.core.models.FairUseStatus
import com.friend.ios.core.models.Person
import com.friend.ios.core.models.PhoneNumber
import com.friend.ios.core.models.Subscription
import com.friend.ios.core.models.UsageStats
import com.friend.ios.core.models.UserProfile
import com.friend.ios.network.APIError
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.service.FakeAPI
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Port of `AccountAndSettingsTests.swift` (the SettingsStore half) and `SettingsHubTests.swift`. */
class SettingsStoreTest {
    private fun store(api: FakeAPI, prefs: Preferences = freshPreferences()) =
        SettingsStore(api.client, prefs, CoroutineScope(Dispatchers.Unconfined), File(System.getProperty("java.io.tmpdir")))

    /** The backend's name wins over the one saved on this phone; a rename shows at once. */
    @Test
    fun profileNameFromTheBackend() = runTest {
        val api = fakeAPI()
        val prefs = freshPreferences()
        prefs.set(Key.GivenName, "Alex")
        val settings = store(api, prefs)
        assertEquals("Alex", settings.displayName)
        with(api) { "userProfile" returns UserProfile("Ada Lovelace", "ada@example.com") }
        settings.loadProfile()
        assertEquals("Ada Lovelace", settings.displayName)
        settings.nameChanged("  Ada L  ")
        assertEquals("Ada L", settings.displayName)
        settings.nameChanged("   ")
        assertEquals("Ada L", settings.displayName)
    }

    /** The email saved at sign-in wins; the backend's fills in when there is none. */
    @Test
    fun emailFromPreferencesThenBackend() = runTest {
        val api = fakeAPI { "userProfile" returns UserProfile(null, "server@example.com") }
        val prefs = freshPreferences()
        val settings = store(api, prefs)
        settings.loadProfile()
        assertEquals("server@example.com", settings.email)
        prefs.set(Key.Email, "local@example.com")
        assertEquals("local@example.com", settings.email)
    }

    @Test
    fun failedProfileKeepsTheLastOne() = runTest {
        val api = fakeAPI { "userProfile" returns UserProfile("Ada", null) }
        val settings = store(api)
        settings.loadProfile()
        with(api) { "userProfile" throws APIError.Transport("offline") }
        settings.loadProfile()
        assertEquals("Ada", settings.displayName)
    }

    @Test
    fun storesRecordingsRollsBackWhenRefused() = runTest {
        val api = fakeAPI { "setStoresRecordings" throws APIError.Http(500, "") }
        val settings = store(api)
        settings.setStoresRecordings(true)
        assertFalse(settings.storesRecordings)
        assertNotNull(settings.lastError)
        with(api) { "setStoresRecordings" returns Unit }
        settings.setStoresRecordings(true)
        assertTrue(settings.storesRecordings)
        assertNull(settings.lastError)
    }

    @Test
    fun dailySummaryDefaultsAndRollback() = runTest {
        val api = fakeAPI {
            "dailySummary" returns (false to 7)
            "notificationFrequency" returns 3
            "setDailySummary" throws APIError.Transport("offline")
        }
        val settings = store(api)
        assertTrue(settings.dailySummaryEnabled)
        assertEquals(22, settings.dailySummaryHour)
        settings.loadNotifications()
        assertFalse(settings.dailySummaryEnabled)
        assertEquals(7, settings.dailySummaryHour)
        assertEquals(3, settings.notificationFrequency)
        settings.setDailySummary(true, 9)
        assertFalse(settings.dailySummaryEnabled)
        assertEquals(7, settings.dailySummaryHour)
    }

    @Test
    fun vocabularyAddsOnceAndRemoves() = runTest {
        val api = fakeAPI { "setVocabulary" returns Unit }
        val settings = store(api)
        settings.addWord("  Omi ")
        settings.addWord("Omi")
        settings.addWord(" ")
        settings.addWord("Lovelace")
        assertEquals(listOf("Omi", "Lovelace"), settings.vocabulary)
        assertEquals(2, api.called("setVocabulary").size)
        settings.removeWords(setOf(0))
        assertEquals(listOf("Lovelace"), settings.vocabulary)
        with(api) { "setVocabulary" throws APIError.Http(500, "") }
        settings.addWord("Nope")
        assertEquals(listOf("Lovelace"), settings.vocabulary)
    }

    @Test
    fun peopleSortedAndDeleteRollsBack() = runTest {
        val api = fakeAPI {
            "people" returns listOf(Person("2", "Zoe", 1), Person("1", "Ann", 2))
            "deletePerson" throws APIError.Http(500, "")
        }
        val settings = store(api)
        settings.loadPeople()
        assertEquals(listOf("Ann", "Zoe"), settings.people.map { it.name })
        settings.deletePerson("1")
        assertEquals(listOf("Ann", "Zoe"), settings.people.map { it.name })
    }

    /** A paid feature: the backend's own words ("detail") explain why phone calls are locked. */
    @Test
    fun phoneNumbersLockedOnTheFreePlan() = runTest {
        val api = fakeAPI { "phoneNumbers" throws APIError.Http(402, """{"detail":"Phone calls require a paid subscription"}""") }
        val settings = store(api)
        settings.loadPhoneNumbers()
        assertEquals("Phone calls require a paid subscription", settings.phoneUnavailableReason)
        with(api) { "phoneNumbers" returns listOf(PhoneNumber("n1", "+1555", true)) }
        settings.loadPhoneNumbers()
        assertNull(settings.phoneUnavailableReason)
        assertEquals(1, settings.phoneNumbers.size)
    }

    @Test
    fun subscriptionFailureReadsAsUnknown() = runTest {
        val api = fakeAPI { "subscription" throws APIError.Transport("offline") }
        val settings = store(api)
        settings.loadSubscription()
        assertNull(settings.subscription)
        val free = Subscription("basic", "active", false, emptyList(), 0, 0, null, true, emptyList())
        with(api) { "subscription" returns free }
        settings.loadSubscription()
        assertEquals("basic", settings.subscription?.plan)
    }

    /** `flutter.appearanceMode`: dark by default, kept under Flutter's key. */
    @Test
    fun appearanceModeUsesFlutterKey() {
        val prefs = freshPreferences()
        val settings = store(fakeAPI(), prefs)
        assertEquals("dark", settings.appearanceMode)
        settings.appearanceMode = "light"
        assertEquals("light", prefs.string(Key.AppearanceMode))
        assertEquals("light", store(fakeAPI(), prefs).appearanceMode)
    }

    @Test
    fun voiceResponseModeDefaultsToHeadphones() {
        val prefs = freshPreferences()
        val settings = store(fakeAPI(), prefs)
        assertEquals(1, settings.voiceResponseMode)
        settings.voiceResponseMode = 2
        assertEquals(2, prefs.integer(Key.VoiceResponseMode, 1))
    }

    @Test
    fun spokenLanguageRollsBack() = runTest {
        val prefs = freshPreferences()
        prefs.set(Key.UserPrimaryLanguage, "en")
        val api = fakeAPI { "setPrimaryLanguage" throws APIError.Http(500, "") }
        val settings = store(api, prefs)
        settings.setSpokenLanguage("de")
        assertEquals("en", settings.spokenLanguage)
    }

    @Test
    fun usageStoreTracksFailedPeriods() = runTest {
        val totals = UsageStats.Totals(60, 100, 2, 3)
        val api = fakeAPI { "usage" throws APIError.Transport("offline") }
        val usage = UsageStore(api.client, "Europe/Berlin")
        usage.load()
        assertTrue(UsageStats.Period.Monthly in usage.failedPeriods)
        with(api) { "usage" returns UsageStats(totals, emptyList()) }
        usage.load()
        assertEquals(totals, usage.current?.totals)
        assertTrue(usage.failedPeriods.isEmpty())
        assertEquals(listOf(UsageStats.Period.Monthly, "Europe/Berlin"), api.called("usage").last())
        with(api) { "fairUseStatus" returns FairUseStatus("none", null, FairUseStatus.Window.of(1.0, 2.0), FairUseStatus.Window.of(0.0, 8.0), FairUseStatus.Window.of(0.0, 10.0), "") }
        usage.loadFairUse()
        assertEquals(50.0, usage.fairUse!!.today.percent, 0.001)
    }

    /** Keeping audio on the phone uses Flutter's `unlimitedLocalStorageEnabled`. */
    @Test
    fun profileStoreAudioOnPhoneAndCancel() = runTest {
        val prefs = freshPreferences()
        val api = fakeAPI { "cancelSubscription" returns Unit }
        val profile = store(api, prefs).makeProfileStore()
        assertFalse(profile.storesAudioOnPhone)
        profile.storesAudioOnPhone = true
        assertTrue(prefs.bool(Key.UnlimitedLocalStorageEnabled))
        assertTrue(profile.cancelSubscription("too_expensive", "  details  "))
        assertEquals(listOf("too_expensive", "details"), api.called("cancelSubscription").single())
        with(api) { "cancelSubscription" throws APIError.Http(500, "") }
        assertFalse(profile.cancelSubscription(null, null))
        assertNotNull(profile.lastError)
    }

    @Test
    fun referralMissingIsAFailure() = runTest {
        val api = fakeAPI { "referralURL" returns null }
        val profile = store(api).makeProfileStore()
        profile.loadReferral()
        assertTrue(profile.referralFailed)
    }
}
