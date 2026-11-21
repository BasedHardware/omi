import Foundation
@testable import OmiExtras
import Testing

struct SharedStoreTests {
    private func store() -> SharedStore {
        let name = "omi.extras.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defaults.removePersistentDomain(forName: name)
        return SharedStore(defaults: defaults)
    }

    @Test func writesReportOnlyRealChanges() {
        let store = store()
        let device = DeviceSnapshot(name: "Omi", connected: true, battery: 82)
        #expect(store.write(device, for: .device))
        #expect(!store.write(device, for: .device))
        #expect(store.read(DeviceSnapshot.self, for: .device) == device)
        #expect(store.write(DeviceSnapshot(name: "Omi", connected: true, battery: 81), for: .device))
    }

    @Test func batteryIsClampedToAPercentage() {
        #expect(DeviceSnapshot(name: "Omi", connected: true, battery: 140).battery == 100)
        #expect(DeviceSnapshot(name: "Omi", connected: true, battery: -3).battery == 0)
        #expect(DeviceSnapshot(name: "Omi", connected: false, battery: nil).battery == nil)
    }

    @Test func aClearedDocumentIsStillKnown() {
        let store = store()
        #expect(!store.isKnown(.latest))
        #expect(store.write(LatestSnapshot?.none, for: .latest))
        #expect(store.isKnown(.latest))
        #expect(store.read(LatestSnapshot.self, for: .latest) == nil)
        #expect(!store.write(LatestSnapshot?.none, for: .latest))
    }

    @Test func datesSurviveTheRoundTrip() {
        let store = store()
        let at = Date(timeIntervalSince1970: 1_790_000_000)
        let latest = LatestSnapshot(id: "c1", title: "Pricing call", at: at, taskCount: 2, duration: 840)
        store.write(latest, for: .latest)
        #expect(store.read(LatestSnapshot.self, for: .latest) == latest)
    }

    @Test func signingOutClearsEveryWidget() {
        let store = store()
        store.write(DeviceSnapshot(name: "Omi", connected: true, battery: 50), for: .device)
        store.write(UpNextSnapshot(tasks: [], open: 0), for: .upNext)
        #expect(Set(store.clear()) == [.battery, .upNext])
        #expect(!store.isKnown(.device))
        #expect(store.clear().isEmpty)
    }
}

struct UpNextPickerTests {
    private let now = Date(timeIntervalSince1970: 1_790_000_000)

    @Test func datedTasksComeFirstSoonestOnTop() {
        let snapshot = UpNextPicker.snapshot([
            .init(id: "undated", title: "Read the report", due: nil, isOpen: true),
            .init(id: "later", title: "Send the draft", due: now.addingTimeInterval(7200), isOpen: true),
            .init(id: "overdue", title: "Call Chitapa", due: now.addingTimeInterval(-3600), isOpen: true),
            .init(id: "done", title: "Book flights", due: now, isOpen: false),
            .init(id: "next", title: "Pay rent", due: now.addingTimeInterval(60), isOpen: true),
        ])
        #expect(snapshot.tasks.map(\.id) == ["overdue", "next", "later"])
        #expect(snapshot.open == 4)
    }

    @Test func blankTitlesAreSkippedAndTrimmed() {
        let snapshot = UpNextPicker.snapshot([
            .init(id: "a", title: "  ", due: nil, isOpen: true),
            .init(id: "b", title: " Water plants \n", due: nil, isOpen: true),
        ])
        #expect(snapshot.tasks == [.init(id: "b", title: "Water plants", due: nil)])
        #expect(snapshot.open == 1)
    }
}

struct ActivityTests {
    private let start = Date(timeIntervalSince1970: 1_790_000_000)

    private typealias State = OmiActivityAttributes.ContentState

    private func live(_ status: State.CaptureStatus = .listening, source: State.Source = .omi) -> State {
        State.capture(id: "rec", startedAt: start, source: source, status: status, canPause: true, now: start)
    }

    private func run(step: String, phase: State.Phase = .working) -> State {
        State(id: "run", phase: phase, startedAt: start, taskID: "run", title: "Find a dentist", step: step)
    }

    @Test func onlyNewStepsWaitForTheThrottle() {
        #expect(run(step: "Searching the web").isRoutineChange(from: run(step: "Reading results")))
        #expect(!run(step: "Done", phase: .finished).isRoutineChange(from: run(step: "Reading results")))
        #expect(!run(step: "Same").isRoutineChange(from: run(step: "Same")))
        #expect(!live(.paused).isRoutineChange(from: live()))
        #expect(!live(source: .iPhone).isRoutineChange(from: live()))
    }

    @Test func stoppedRecordingsFreezeTheirClock() {
        #expect(live().elapsed == nil)
        let paused = State.capture(id: "rec", startedAt: start, source: .omi, status: .paused, elapsed: 75, canPause: true)
        #expect(paused.elapsed == 75)
        let ended = live().ended(at: start.addingTimeInterval(136))
        #expect(ended.status == .ended && ended.elapsed == 136 && !ended.canPause)
        #expect(paused.ended(at: start.addingTimeInterval(500)).elapsed == 75)
        #expect(run(step: "x").ended(at: start.addingTimeInterval(9)).phase == .working)
    }

    @Test func onlyRunningCapturesGoStale() {
        #expect(live().staleDate(now: start) == start.addingTimeInterval(State.staleAfter))
        #expect(live(.recording).staleDate(now: start) != nil)
        #expect(live(.paused).staleDate(now: start) == nil)
        #expect(live(.ended).staleDate(now: start) == nil)
        #expect(run(step: "x").staleDate(now: start) == nil)
        #expect(State.heartbeat < State.staleAfter)
    }

    @Test func pausedTimeIsLeftOffTheClock() {
        var clock = CapturePauseClock()
        #expect(clock.observe(since: start, paused: false, now: start.addingTimeInterval(10)) == (start, nil))
        let stopped = clock.observe(since: start, paused: true, now: start.addingTimeInterval(60))
        #expect(stopped.startedAt == start && stopped.elapsed == 60)
        // Still stopped later: the frozen value holds.
        #expect(clock.observe(since: start, paused: true, now: start.addingTimeInterval(90)).elapsed == 60)
        let resumed = clock.observe(since: start, paused: false, now: start.addingTimeInterval(100))
        #expect(resumed.startedAt == start.addingTimeInterval(40) && resumed.elapsed == nil)
        // A new recording starts over.
        let next = start.addingTimeInterval(1000)
        #expect(clock.observe(since: next, paused: false, now: next) == (next, nil))
    }

    @Test func throttleSpacesRoutineUpdates() {
        var throttle = ActivityUpdateThrottle(interval: 4, floor: 1)
        #expect(throttle.decide(urgent: false, at: start) == .send)
        throttle.didSend(at: start)
        #expect(throttle.decide(urgent: false, at: start.addingTimeInterval(1.5)) == .wait(2.5))
        #expect(throttle.decide(urgent: false, at: start.addingTimeInterval(4)) == .send)
    }

    @Test func urgentUpdatesOnlyMergeBursts() {
        var throttle = ActivityUpdateThrottle(interval: 4, floor: 1)
        throttle.didSend(at: start)
        #expect(throttle.decide(urgent: true, at: start.addingTimeInterval(0.25)) == .wait(0.75))
        #expect(throttle.decide(urgent: true, at: start.addingTimeInterval(1)) == .send)
        throttle.reset()
        #expect(throttle.decide(urgent: false, at: start) == .send)
    }

    @Test func contentStateStaysSmall() throws {
        let state = State(id: String(repeating: "i", count: 40), phase: .working, startedAt: start, taskID: "t",
                          title: String(repeating: "t", count: 120), step: String(repeating: "s", count: 80), otherRuns: 3)
        // ActivityKit rejects content over 4 KB.
        #expect(try JSONEncoder().encode(state).count < 1024)
        #expect(try JSONDecoder().decode(State.self, from: JSONEncoder().encode(live(.paused))) == live(.paused))
    }
}

struct NotificationImageTests {
    @Test func readsFirebaseImageOption() {
        let payload: [AnyHashable: Any] = [
            "aps": ["alert": ["title": "Omi", "body": "Your recap"], "mutable-content": 1],
            "fcm_options": ["image": "https://cdn.omi.me/recap.png"],
            "gcm.message_id": "1",
        ]
        #expect(NotificationImage.url(in: payload) == URL(string: "https://cdn.omi.me/recap.png"))
    }

    @Test func fallsBackToPlainKeys() {
        #expect(NotificationImage.url(in: ["image_url": " https://a.b/c.jpg "]) == URL(string: "https://a.b/c.jpg"))
        #expect(NotificationImage.url(in: ["image": "https://a.b/i.gif"]) == URL(string: "https://a.b/i.gif"))
    }

    @Test func rejectsInsecureOrMissingImages() {
        #expect(NotificationImage.url(in: ["image": "http://a.b/c.jpg"]) == nil)
        #expect(NotificationImage.url(in: ["image": "not a url"]) == nil)
        #expect(NotificationImage.url(in: ["fcm_options": ["image": ""]]) == nil)
        #expect(NotificationImage.url(in: ["navigate_to": "/chat/omi"]) == nil)
    }

    @Test func picksTheAttachmentExtension() throws {
        let url = try #require(URL(string: "https://a.b/picture"))
        #expect(NotificationImage.fileExtension(mimeType: "image/png", url: url) == "png")
        #expect(NotificationImage.fileExtension(mimeType: "image/jpeg; charset=binary", url: url) == "jpg")
        #expect(NotificationImage.fileExtension(mimeType: "text/html", url: url) == nil)
        let gif = try #require(URL(string: "https://a.b/x.GIF?size=2"))
        #expect(NotificationImage.fileExtension(mimeType: nil, url: gif) == "gif")
    }
}

struct WidgetReloadTests {
    private func device(_ battery: Int?, connected: Bool = true, name: String = "Omi") -> DeviceSnapshot {
        DeviceSnapshot(name: name, connected: connected, battery: battery)
    }

    @Test func connectionAndIdentityAlwaysReload() {
        #expect(device(80).needsReload(from: nil))
        #expect(device(80, connected: false).needsReload(from: device(80)))
        #expect(device(80, name: "Omi 2").needsReload(from: device(80)))
        #expect(device(80).needsReload(from: device(nil)))
    }

    @Test func smallBatteryStepsWaitForTheWidgetsOwnRefresh() {
        #expect(!device(78).needsReload(from: device(80)))
        #expect(device(75).needsReload(from: device(80)))
        #expect(device(20).needsReload(from: device(22)))
        #expect(!device(80).needsReload(from: device(80)))
    }

    @Test func clockRangeEndsAtTheNextFullHour() {
        typealias State = OmiActivityAttributes.ContentState
        let start = Date(timeIntervalSince1970: 1_790_000_000)
        #expect(State.clockEnd(since: start, now: start) == start.addingTimeInterval(3600))
        #expect(State.clockEnd(since: start, now: start.addingTimeInterval(3599)) == start.addingTimeInterval(3600))
        #expect(State.clockEnd(since: start, now: start.addingTimeInterval(3600)) == start.addingTimeInterval(7200))
        let before = State.capture(id: "rec", startedAt: start, source: .omi, status: .listening, canPause: true, now: start)
        let rolled = State.capture(id: "rec", startedAt: start, source: .omi, status: .listening, canPause: true,
                                   now: start.addingTimeInterval(4000))
        #expect(rolled.clockEnd == start.addingTimeInterval(7200))
        #expect(!rolled.isRoutineChange(from: before))
    }
}
