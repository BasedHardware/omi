//
//  ActivitySpine.swift — the one Activity store, owned by the process rather than by a window.
//
//  **The store used to be `@StateObject` inside `ActivitySurface`, and that is a shorter-lived thing
//  than it looks.** `SearchBarWindow.dismiss()` sets `current = nil` before it closes, so `present()`
//  never takes its own reuse branch: every summoning of the panel builds a fresh window, a fresh
//  `SearchBarView` and therefore a fresh store. And the panel's lower half is a `switch` on which
//  body is showing, so typing a query unmounts the activity branch outright and clearing the field
//  mounts a new one. Three ordinary actions — launch, re-open, search-then-clear — each threw away a
//  fully hydrated corpus and re-paged the entire account from offset zero.
//
//  Measured on this machine that is thousands of rows and a walk of dozens of requests, every time,
//  for data that had not changed. It is also the reason the panel looked slow in a way no cache
//  could have fixed: a cache shortens the first paint, and this was re-doing the *whole* fill.
//
//  Main has never had this problem and not by cleverness — `AppState` and `ConversationRepository`
//  simply belong to the application, so opening its window costs nothing and `SpineStream.task` can
//  guard with `if appState.conversations.isEmpty`. This file is that ownership, in this app.
//
//  ## What lives here and what does not
//
//  Only the store. Everything about *drawing* it — the chips, the query, the detail push, the
//  reading position — stays with the view, because that is what is genuinely worth as long as the
//  panel is on screen and no longer. The corpus is not: it is the same corpus whoever is looking.
//
//  ## Signing out
//
//  A process-lived store outlives a sign-out, which a window-lived one never did, so it has to be
//  told. Everything one account handed over is dropped and the cache on disk with it — the next
//  account's first paint must not be somebody else's conversations. This is `ConversationRepository`'s
//  `.runtimeOwnerDidChange` reset, on the one signal this app has.
//

import AppKit
import Combine
import ContextCore
import Foundation

/// The application's single Activity store.
@MainActor
final class ActivitySpine {
    static let shared = ActivitySpine()

    /// The store every Activity surface draws. One per process — see the note above.
    let store: ActivityStore

    private var cancellables: Set<AnyCancellable> = []

    private init(
        store: ActivityStore? = nil,
        signIns: AnyPublisher<Bool, Never>? = nil,
        activations: AnyPublisher<Void, Never>? = nil
    ) {
        self.store =
            store
            ?? ActivityStore(
                store: { Engine.shared.contextStore },
                // Wrapped, for the reason `SearchBarView` documents where this used to be built:
                // three of the five chips have no local source at all, and the memory column is read
                // this Mac's database first so a `/v3/memories` outage does not draw as an empty
                // account. Built once here rather than per panel, which is also what gives the
                // reader's paging cursor a life longer than one window.
                account: ActivityLocalMemories(OmiActivityFeed()),
                cache: ActivityAccountCache(
                    store: { await MainActor.run { Engine.shared.contextStore } }))

        // Signing out is the one thing a store this long-lived cannot simply ignore. `filter` on the
        // false edge because signing *in* is already handled inside the store, where it re-reads an
        // account it had reported as absent; this is the other direction, where the right answer is
        // to forget rather than to fetch.
        (signIns ?? OmiAuth.shared.$isSignedIn.eraseToAnyPublisher())
            .removeDuplicates()
            .filter { !$0 }
            .sink { [weak self] _ in self?.store.forgetTheAccount() }
            .store(in: &cancellables)

        // **Coming back to the app is the other half of "keep what you have, fetch what changed".**
        // Main answers `didBecomeActiveNotification` with a server-only refresh over a list it never
        // clears (`DesktopHomeView`, throttled by `PollingConfig.activationCooldown`), and this is
        // that, on this app's one long-lived surface. `revalidate` carries the same cooldown, so the
        // two signals it now has — this, and the panel being summoned — cannot become two requests.
        (activations
            ?? NotificationCenter.default
            .publisher(for: NSApplication.didBecomeActiveNotification)
            .map { _ in () }
            .eraseToAnyPublisher())
            .sink { [weak self] in self?.store.revalidate() }
            .store(in: &cancellables)
    }

    /// A host with an injected store, for tests that need the sign-out wiring without the app.
    static func forTesting(
        store: ActivityStore,
        signIns: AnyPublisher<Bool, Never>,
        activations: AnyPublisher<Void, Never> = Empty().eraseToAnyPublisher()
    ) -> ActivitySpine {
        ActivitySpine(store: store, signIns: signIns, activations: activations)
    }
}
