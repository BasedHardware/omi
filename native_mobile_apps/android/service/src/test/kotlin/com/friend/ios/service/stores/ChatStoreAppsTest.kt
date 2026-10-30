package com.friend.ios.service.stores

import com.friend.ios.core.models.OmiApp
import com.friend.ios.network.endpoints.AppsAPI
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.NativeKey
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.lang.reflect.Proxy

/**
 * Chat apps and personas: the chat talks to Omi or to one enabled app that can chat. Port of
 * `ChatAppsTests` (`AppCatalogAndChatAppsTests.swift`).
 */
class ChatStoreAppsTest {
    private fun app(id: String, capabilities: Set<String>) = OmiApp(
        id = id, name = id.replaceFirstChar { it.uppercase() }, description = "", author = null, imageURL = null, category = null,
        rating = null, installs = 0, isEnabled = true, capabilities = capabilities,
    )

    /** The installed apps (`installedOnly`: the backend leaves out the ones turned off). */
    private var installed = listOf(app("coach", setOf("chat")), app("sync", setOf("memories")), app("twin", setOf("persona")))
    private val searches = mutableListOf<List<Any?>>()

    /** Only `searchApps` is answered; the chat never asks for anything else. */
    private val apps = Proxy.newProxyInstance(AppsAPI::class.java.classLoader, arrayOf(AppsAPI::class.java)) { _, method, args ->
        check(method.name == "searchApps") { "not stubbed: ${method.name}" }
        searches += args.orEmpty().dropLast(1)
        installed
    } as AppsAPI

    @Test
    fun listsOnlyInstalledAppsThatChat() = runTest {
        val chat = ChatStore(FakeChatAPI(), Preferences(FakePrefs()), this, apps)
        chat.loadChatApps()
        assertEquals(listOf("coach", "twin"), chat.chatApps.map { it.id })
        assertEquals(listOf<Any?>("", true, 0), searches.single())
    }

    @Test
    fun theChosenAppIsRestoredAfterARelaunch() = runTest {
        val prefs = Preferences(FakePrefs())
        val first = ChatStore(FakeChatAPI(), prefs, this, apps)
        first.loadChatApps()
        first.talk(first.chatApps[1])
        val api = FakeChatAPI()
        val relaunched = ChatStore(api, prefs, this, apps)
        relaunched.loadHistory()
        assertEquals("twin", relaunched.chatApp?.id)
        assertEquals("app-session", api.historySessions.last())
    }

    @Test
    fun aDisabledAppFallsBackToOmi() = runTest {
        val prefs = Preferences(FakePrefs())
        val chat = ChatStore(FakeChatAPI(), prefs, this, apps)
        chat.loadChatApps()
        chat.talk(chat.chatApps[0])
        assertEquals("coach", chat.chatApp?.id)
        installed = installed.filter { it.id != "coach" }
        chat.loadChatApps()
        assertNull(chat.chatApp)
        assertNull(prefs.string(NativeKey.SelectedChatAppID))
    }

    @Test
    fun withoutAnAppListTheChatStaysWithOmi() = runTest {
        val chat = ChatStore(FakeChatAPI(), Preferences(FakePrefs()), this)
        chat.loadChatApps()
        assertTrue(chat.chatApps.isEmpty())
        assertNull(chat.chatApp)
    }
}
