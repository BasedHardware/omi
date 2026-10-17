package com.friend.ios.system

import com.friend.ios.core.DeepLink
import com.friend.ios.core.QuickAction
import com.friend.ios.shell.Route
import com.friend.ios.shell.Tab
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** The router's inbox and the destinations that need nothing loaded (`DeepLinkRouterTests.swift`). */
class DeepLinkRouterTest {
    @Test fun aLinkWaitsUntilTheShellTakesIt() {
        val router = DeepLinkRouter()
        router.open(null as DeepLink?)
        assertNull(router.pending)
        router.open("omi://conversation/abc")
        assertEquals(DeepLink.Conversation("abc"), router.pending)
        // A newer link replaces one not opened yet.
        router.open("https://h.omi.me/apps/x")
        assertEquals(DeepLink.App("x"), router.take())
        assertNull(router.take())
        // Not a link (the auth callback, an unknown page): nothing waits.
        router.open("omi://auth/callback?code=1")
        router.open("https://h.omi.me/wrapped")
        assertNull(router.pending)
    }

    @Test fun immediateDestinations() {
        val cases = mapOf(
            DeepLink.Conversation("c") to DeepLinkRouter.Destination.Push(Route.Conversation("c")),
            DeepLink.Tasks to DeepLinkRouter.Destination.Push(Route.AllTasks),
            DeepLink.Memories to DeepLinkRouter.Destination.SelectTab(Tab.Memory),
            DeepLink.Memory("m") to DeepLinkRouter.Destination.SelectTab(Tab.Memory),
            DeepLink.Home to DeepLinkRouter.Destination.SelectTab(Tab.Home),
            DeepLink.Chat to DeepLinkRouter.Destination.Chat,
            DeepLink.Device to DeepLinkRouter.Destination.Device,
            DeepLink.ChatDraft("hi") to DeepLinkRouter.Destination.ChatDraft("hi"),
            DeepLink.NewTask to DeepLinkRouter.Destination.NewTask,
            DeepLink.Record to DeepLinkRouter.Destination.Record,
            DeepLink.Account to DeepLinkRouter.Destination.Account,
            DeepLink.App("a") to DeepLinkRouter.Destination.App("a"),
        )
        cases.forEach { (link, destination) -> assertEquals(link.toString(), destination, DeepLinkRouter.immediateDestination(link)) }
        // These load first (the task, the recap, the shared list, the folder filter).
        listOf(DeepLink.Task("t"), DeepLink.Recap("2026-10-07"), DeepLink.SharedTasks("s"), DeepLink.Folder("f"))
            .forEach { assertNull(it.toString(), DeepLinkRouter.immediateDestination(it)) }
    }

    @Test fun launcherShortcutsOpenTheirPlace() {
        assertEquals(DeepLinkRouter.Destination.Chat, DeepLinkRouter.immediateDestination(DeepLink.fromUrl(QuickAction.AskOmi.link.url)!!))
        assertEquals(DeepLinkRouter.Destination.NewTask, DeepLinkRouter.immediateDestination(DeepLink.fromUrl(QuickAction.AddTask.link.url)!!))
        assertEquals(DeepLinkRouter.Destination.Record, DeepLinkRouter.immediateDestination(DeepLink.fromUrl(QuickAction.StartRecording.link.url)!!))
        assertEquals(DeepLinkRouter.Destination.Device, DeepLinkRouter.immediateDestination(DeepLink.fromUrl(QuickAction.MyOmi.link.url)!!))
    }
}
