#if DEBUG
    import OmiExtras
    import SwiftUI
    import UIKit

    /// Renders the Live Activity's views (Extensions/LiveActivityUI) to PNGs for layout checks,
    /// without ActivityKit: `-omiRenderLiveActivity YES` writes them to
    /// Library/Caches/LiveActivityRenders at the screen's scale, in English and German.
    @MainActor
    enum LiveActivityRenderer {
        private typealias State = OmiActivityAttributes.ContentState
        private typealias Chrome = LiveActivityMockChrome

        static func renderAll() {
            let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            let folder = caches.appendingPathComponent("LiveActivityRenders", isDirectory: true)
            try? FileManager.default.removeItem(at: folder)
            try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            for language in ["en", "de"] {
                for (name, view) in views() {
                    // A still render cannot play the wave's flipbook (it turns on the system's
                    // clock), so its frames overlap; the bars' sizes and spacing are what to check.
                    let content = view.environment(\.locale, Locale(identifier: language))
                    let renderer = ImageRenderer(content: content)
                    renderer.scale = UIScreen.main.scale
                    guard let data = renderer.uiImage?.pngData() else { continue }
                    try? data.write(to: folder.appendingPathComponent("ours-\(language)-\(name).png"))
                }
            }
            print("LiveActivityRenderer: wrote \(folder.path)")
        }

        private static func views() -> [(String, AnyView)] {
            let now = Date.now
            let start = now.addingTimeInterval(-136)
            func capture(_ status: State.CaptureStatus, source: State.Source = .omi, elapsed: Int? = nil) -> State {
                State.capture(id: "rec", startedAt: start, source: source, status: status, elapsed: elapsed,
                              canPause: source != .watch, now: now)
            }
            let listening = CaptureSnapshot(state: capture(.listening), isStale: false)
            let paused = CaptureSnapshot(state: capture(.paused, source: .iPhone, elapsed: 136), isStale: false)
            let later = CaptureSnapshot(state: capture(.recording, source: .iPhone), isStale: false)
            let watch = CaptureSnapshot(state: capture(.listening, source: .watch), isStale: false)
            let stale = CaptureSnapshot(state: capture(.listening), isStale: true)
            let hours = CaptureSnapshot(state: State.capture(id: "rec", startedAt: now.addingTimeInterval(-4000), source: .omi,
                                                             status: .listening, canPause: true, now: now), isStale: false)
            let working = AgentSnapshot(state: State(id: "run", phase: .working, startedAt: now.addingTimeInterval(-42),
                                                     title: "Find a dentist near the office", step: "Searching the web", otherRuns: 1))
            let finished = AgentSnapshot(state: State(id: "run", phase: .finished, startedAt: now.addingTimeInterval(-300), elapsed: 300,
                                                      title: "Find a dentist near the office"))
            let failed = AgentSnapshot(state: State(id: "run", phase: .failed, startedAt: now.addingTimeInterval(-90), elapsed: 90,
                                                    title: "Book a table for four on Friday"))
            var views: [(String, AnyView)] = []
            for (name, snapshot) in [("listening", listening), ("paused", paused), ("later", later), ("watch", watch),
                                     ("stale", stale), ("hours", hours)]
            {
                views.append(("lock-\(name)", AnyView(Chrome.lockScreen(card: CaptureLockScreenView(snapshot: snapshot),
                                                                        tint: CapturePalette.card))))
                views.append(("island-\(name)", AnyView(captureIsland(snapshot))))
            }
            views.append(("compact-listening", AnyView(Chrome.compact(
                leading: CapturePendant(active: true, size: 20),
                trailing: CaptureCompactClock(value: listening.clock)
            ))))
            views.append(("minimal-listening", AnyView(Chrome.minimal(CapturePendant(active: true, size: 20)))))
            for (name, snapshot) in [("working", working), ("finished", finished), ("failed", failed)] {
                views.append(("agent-lock-\(name)", AnyView(Chrome.lockScreen(card: AgentLockScreenView(snapshot: snapshot),
                                                                              tint: CapturePalette.card))))
                views.append(("agent-island-\(name)", AnyView(Chrome.expanded(
                    leading: AgentIslandLeading(snapshot: snapshot),
                    trailing: IslandClock(value: snapshot.clock, ended: false),
                    bottom: AgentIslandBottom(snapshot: snapshot)
                ))))
                views.append(("agent-compact-\(name)", AnyView(Chrome.compact(
                    leading: AgentArt(snapshot: snapshot, size: 20),
                    trailing: CaptureCompactClock(value: snapshot.clock)
                ))))
            }
            views.append(("agent-minimal-working", AnyView(Chrome.minimal(AgentArt(snapshot: working, size: 20)))))
            return views
        }

        private static func captureIsland(_ snapshot: CaptureSnapshot) -> some View {
            Chrome.expanded(
                leading: CaptureIslandLeading(snapshot: snapshot),
                trailing: IslandClock(value: snapshot.clock, ended: snapshot.ended),
                bottom: CaptureIslandBottom(snapshot: snapshot)
            )
        }
    }
#endif
