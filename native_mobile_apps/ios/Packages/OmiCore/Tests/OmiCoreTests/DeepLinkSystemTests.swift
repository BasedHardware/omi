import Foundation
@testable import OmiCore
import Testing

/// Siri, Spotlight, quick actions and universal links all land on a `DeepLink`.
struct DeepLinkSystemTests {
    private func link(_ string: String) throws -> DeepLink? {
        try DeepLink(universalLink: #require(URL(string: string)))
    }

    @Test func sharePagesOpenInTheApp() throws {
        #expect(try link("https://h.omi.me/conversations/c1?s=ios&sid=ab12") == .conversation(id: "c1"))
        #expect(try link("https://h.omi.me/recaps/sum-1") == .recap("sum-1"))
        #expect(try link("https://H.OMI.ME/unlimited") == .account)
        #expect(try link("https://try.omi.me/conversations/c2") == .conversation(id: "c2"))
        #expect(try link("https://h.omi.me/memories/m1") == .memory(id: "m1"))
        #expect(try link("https://h.omi.me/apps/app-1?s=ios") == .app(id: "app-1"))
        #expect(try link("https://h.omi.me/tasks/tok-9") == .sharedTasks(token: "tok-9"))
        #expect(DeepLink.app(id: "a b").route == "/apps/a%20b")
        #expect(DeepLink(route: DeepLink.app(id: "a b").route) == .app(id: "a b"))
    }

    @Test func otherLinksOnlyOpenTheApp() throws {
        #expect(try link("https://h.omi.me/wrapped") == nil)
        #expect(try link("https://h.omi.me/tasks") == nil)
        #expect(try link("https://h.omi.me/apps") == nil)
        #expect(try link("https://h.omi.me/conversations") == nil)
        #expect(try link("https://h.omi.me/") == nil)
        #expect(try link("https://omi.me/conversations/c1") == nil)
        #expect(try link("omi://conversation/c1") == nil)
    }

    @Test func quickActionsRouteThroughDeepLinks() {
        #expect(QuickAction(shortcutType: "ask_omi")?.link == .chat)
        #expect(QuickAction(shortcutType: "add_task")?.link == .newTask)
        #expect(QuickAction(shortcutType: "start_recording")?.link == .record)
        #expect(QuickAction(shortcutType: "device_settings")?.link == .device)
        // Flutter's other device item and shortcuts the native app does not offer.
        #expect(QuickAction(shortcutType: "connect_device") == .myOmi)
        #expect(QuickAction(shortcutType: "voice_mode") == nil)
        #expect(QuickAction(shortcutType: "mute") == nil)
        #expect(Set(QuickAction.menuOrder) == Set(QuickAction.allCases))
    }

    @Test func siriAndSpotlightTargetsRoundTrip() {
        let links: [DeepLink] = [
            .memory(id: "m 1"), .folder(id: "f/1"), .newTask, .record, .account,
            .chatDraft("Was hab ich heute gemacht? & mehr"), .conversation(id: "c1"), .task(id: "t1"),
        ]
        for link in links {
            #expect(DeepLink(route: link.route) == link)
            #expect(DeepLink(url: link.url) == link)
        }
    }

    @Test func omiURLsForTheNewPlaces() throws {
        #expect(try DeepLink(url: #require(URL(string: "omi://memory/m1"))) == .memory(id: "m1"))
        #expect(try DeepLink(url: #require(URL(string: "omi://memory"))) == .memories)
        #expect(try DeepLink(url: #require(URL(string: "omi://folder/f1"))) == .folder(id: "f1"))
        #expect(try DeepLink(url: #require(URL(string: "omi://folder"))) == nil)
        #expect(try DeepLink(url: #require(URL(string: "omi://tasks/new"))) == .newTask)
        #expect(try DeepLink(url: #require(URL(string: "omi://chat?q=%20%20"))) == .chat)
        #expect(try DeepLink(url: #require(URL(string: "omi://settings/account"))) == .account)
        #expect(DeepLink.conversation(id: "c1").url.absoluteString == "omi://conversation/c1")
    }
}
