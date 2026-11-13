package com.friend.ios.service.stores

import com.friend.ios.core.models.AppDetail
import com.friend.ios.core.models.DeveloperKey
import com.friend.ios.core.models.DeveloperWebhook
import com.friend.ios.core.models.Integration
import com.friend.ios.core.models.OmiApp
import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.AppsMapper
import com.friend.ios.persistence.Preferences.NativeKey
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Port of the capabilities, app store and `DeveloperStoreTests.swift` cases. */
class AppsAndDeveloperTest {
    private fun app(id: String, enabled: Boolean = false) = OmiApp(id, id, "", null, null, null, null, 0, enabled)

    @Test
    fun capabilitiesReadEachConnection() = runTest {
        val api = fakeAPI {
            "connectedTaskApps" returns setOf("todoist")
            "integrationConnected" does { args -> args[0] == "gmail" }
        }
        val store = CapabilitiesStore(api.client)
        store.load()
        assertEquals(setOf("gmail", "todoist"), store.integrations.filter { it.isConnected }.map { it.id }.toSet())
        assertEquals(2, store.connectedCount)
        assertEquals(2, SettingsHub.connectedApps(store.connectedCount, health = false, reminders = false))
    }

    @Test
    fun connectSaysWhyItCannot() = runTest {
        val calendar = CapabilitiesStore.catalog.first()
        val api = fakeAPI { "integrationOAuthURL" throws APIError.Http(500, "Google Calendar not configured - GOOGLE_CLIENT_ID missing") }
        val store = CapabilitiesStore(api.client)
        assertNull(store.authorizationURL(calendar))
        assertEquals(CapabilitiesStore.ConnectFailure.NotConfigured, store.failures[calendar.id])
        assertNull(store.connecting)
        assertEquals(CapabilitiesStore.ConnectFailure.Offline, CapabilitiesStore.failure(APIError.Transport("x")))
        store.loginEnded(calendar, cancelled = true)
        assertEquals(CapabilitiesStore.ConnectFailure.Cancelled, store.failures[calendar.id])
    }

    @Test
    fun installIsOptimisticAndTakenBack() = runTest {
        val api = fakeAPI { "setApp" throws APIError.Transport("offline") }
        val store = CapabilitiesStore(api.client)
        store.setApp(app("a"), enabled = true)
        assertTrue(store.installedApps.isEmpty())
        with(api) { "setApp" returns Unit }
        store.setApp(app("a"), enabled = true)
        assertEquals(listOf("a"), store.installedApps.map { it.id })
        assertTrue(store.installedApps.single().isEnabled)
    }

    @Test
    fun appMapperReadsDetailSetupAndOwnership() {
        val o = Json.parseToJsonElement(
            """
            {"id": "a1", "name": "Notes", "uid": "me", "is_paid": true, "is_user_paid": false, "payment_link": "https://pay",
             "rating_avg": 4.5, "rating_count": 2, "capabilities": ["chat"], "chat_prompt": "  ",
             "external_integration": {"auth_steps": [{"name": "Sign in", "url": "https://x"}], "setup_instructions_file_path": "Do this", "app_home_url": "https://home"},
             "reviews": [{"uid": "u", "score": 4, "review": "good"}, {"uid": "v", "score": 1, "review": ""}],
             "user_review": {"uid": "me", "score": 5, "review": "mine"}}
            """.trimIndent(),
        ) as JsonObject
        val detail: AppDetail = AppsMapper.detail(o, "me")!!
        assertTrue(detail.isOwn)
        assertTrue(detail.needsPurchase)
        assertTrue(detail.app.worksWithChat)
        assertNull(detail.chatPrompt)
        assertEquals("Do this", detail.setupInstructionsText)
        assertNull(detail.setupInstructionsURL)
        assertEquals(1, detail.reviews.size)
        assertEquals("mine", detail.userReview?.text)
        assertEquals("https://h.omi.me/apps/a1", detail.shareURL)
    }

    @Test
    fun catalogSignsSetupLinksAndReportsRefusals() = runTest {
        val capabilities = CapabilitiesStore(fakeAPI { "searchApps" returns emptyList<OmiApp>() }.client)
        val api = fakeAPI { "setApp" throws APIError.Http(400, """{"detail": "Finish setup first"}""") }
        val catalog = AppCatalogStore(api.client, capabilities, { "u1" })
        assertEquals("https://x.io/a?b=1&uid=u1", catalog.signedSetupURL("https://x.io/a?uid=old&b=1"))
        assertEquals("Finish setup first", catalog.setEnabled(app("a"), true))
        with(api) { "setApp" throws APIError.Transport("x") }
        assertEquals(AppCatalogStore.COULD_NOT_CHANGE, catalog.setEnabled(app("a"), true))
    }

    @Test
    fun developerLoadsWebhooksAndSplitsTheAudioInterval() = runTest {
        val api = fakeAPI {
            "webhookStatus" returns DeveloperWebhook.entries.associateWith { it == DeveloperWebhook.AudioBytes }
            "webhookURL" does { args -> if (args[0] == DeveloperWebhook.AudioBytes) "https://a.io/h,12" else "" }
            "developerKeys" returns emptyList<DeveloperKey>()
        }
        val store = DeveloperStore(api.client, freshPreferences(), "https://api.omi.me/")
        assertEquals("https://api.omi.me/v1/mcp", store.mcpServerURL)
        store.load()
        val audio = store.webhooks[DeveloperWebhook.AudioBytes]!!
        assertEquals("https://a.io/h", audio.url)
        assertEquals(12, audio.seconds)
        assertTrue(audio.isEnabled)
        assertFalse(store.hasUnsavedWebhooks)
        store.edit(DeveloperWebhook.DaySummary, url = "ftp://nope")
        assertTrue(store.hasUnsavedWebhooks)
        assertFalse(store.saveWebhooks())
        assertEquals(DeveloperStore.Failure.InvalidURL(DeveloperWebhook.DaySummary), store.failure)
        store.discardWebhookEdits()
        assertFalse(store.hasUnsavedWebhooks)
    }

    @Test
    fun developerSavesAndCreatesKeys() = runTest {
        val api = fakeAPI {
            "setWebhookURL" returns Unit
            "createDeveloperKey" does { args -> DeveloperKey("k1", args[1] as String, "omi_mcp_1", null, null, emptyList(), "secret") }
            "revokeDeveloperKey" throws APIError.Transport("x")
        }
        val prefs = freshPreferences()
        val store = DeveloperStore(api.client, prefs, "https://api.omi.me")
        store.edit(DeveloperWebhook.AudioBytes, url = "https://a.io/h", seconds = 0)
        assertTrue(store.saveWebhooks())
        assertEquals("https://a.io/h,1", api.called("setWebhookURL").single()[1])
        assertTrue(store.webhooks[DeveloperWebhook.AudioBytes]!!.isEnabled)
        assertFalse(store.createKey(DeveloperKey.Kind.Mcp, "  "))
        assertTrue(store.createKey(DeveloperKey.Kind.Mcp, "Claude"))
        assertEquals("secret", store.createdKey?.secret)
        assertNull(store.mcpKeys.single().secret)
        assertTrue(store.mcpConfig("secret").contains("\"Authorization\": \"Bearer secret\""))
        store.revoke(DeveloperKey.Kind.Mcp, "k1")
        assertEquals(1, store.mcpKeys.size)
        assertEquals(DeveloperStore.Failure.CouldNotSave, store.failure)
        store.isDeveloperMode = true
        assertTrue(prefs.bool(NativeKey.DeveloperMode, false))
    }

    @Test
    fun webhookAddressesAndAudioFormat() {
        assertTrue(DeveloperStore.isValidWebhook(""))
        assertTrue(DeveloperStore.isValidWebhook("https://hooks.example.com/x"))
        assertTrue(DeveloperStore.isValidWebhook("http://localhost:3000"))
        assertFalse(DeveloperStore.isValidWebhook("https://intranet/x"))
        assertFalse(DeveloperStore.isValidWebhook("https://a b.com"))
        assertEquals("" to 5, DeveloperWebhook.splitAudio(""))
        assertEquals("", DeveloperWebhook.joinAudio("", 3))
        assertEquals(8, DeveloperStore.fullAccessScopes.size)
        assertEquals(Integration.Kind.TaskApp, CapabilitiesStore.catalog.last().kind)
    }
}
