import AppKit
import XCTest
@testable import Omi_Computer

/// Tests for `TasksStore` auto-refresh observer wiring (#6500).
///
/// After replacing the 30-second `Timer.publish` with `didBecomeActive` +
/// `.refreshAllData` subscribers, the store must still refresh when those
/// notifications fire. These tests post each notification and assert the
/// baseline-diffed `refreshInvocations` counter advances by one, proving the
/// observer reaches `refreshTasksIfNeeded()` — the early-exit guards inside
/// that method run after the counter bumps, so tests don't need local auth
/// or any prior `loadTasks()` call.
@MainActor
final class TasksStoreObserverTests: XCTestCase {

    func testDidBecomeActiveNotificationTriggersRefresh() async {
        let store = TasksStore.shared
        let baseline = store.refreshInvocations

        NotificationCenter.default.post(
            name: NSApplication.didBecomeActiveNotification, object: nil
        )
        // Sink runs on the main queue; yield so the task enqueues and fires.
        await Task.yield()
        try? await Task.sleep(nanoseconds: 50_000_000)

        XCTAssertEqual(
            store.refreshInvocations, baseline + 1,
            "didBecomeActive must route to refreshTasksIfNeeded() via the activation observer"
        )
    }

    func testRefreshAllDataNotificationTriggersRefresh() async {
        let store = TasksStore.shared
        let baseline = store.refreshInvocations

        NotificationCenter.default.post(name: .refreshAllData, object: nil)
        await Task.yield()
        try? await Task.sleep(nanoseconds: 50_000_000)

        XCTAssertEqual(
            store.refreshInvocations, baseline + 1,
            ".refreshAllData (Cmd+R) must route to refreshTasksIfNeeded() via the refresh observer"
        )
    }

    func testBothNotificationsTriggerIndependentRefreshes() async {
        let store = TasksStore.shared
        let baseline = store.refreshInvocations

        NotificationCenter.default.post(
            name: NSApplication.didBecomeActiveNotification, object: nil
        )
        NotificationCenter.default.post(name: .refreshAllData, object: nil)
        await Task.yield()
        try? await Task.sleep(nanoseconds: 100_000_000)

        XCTAssertEqual(
            store.refreshInvocations, baseline + 2,
            "Both observers must fire independently — posting both notifications yields two refresh calls"
        )
    }
}
