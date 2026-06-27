import AppKit
import XCTest
@testable import Omi_Computer

/// Tests for `MemoriesViewModel` auto-refresh observer wiring (#6500).
///
/// After replacing the 30-second `Timer.publish` with `didBecomeActive` +
/// `.refreshAllData` subscribers, the view model must still refresh when
/// those notifications fire. Because `MemoriesViewModel` is not a singleton,
/// each test constructs a fresh instance (triggering `init()` which registers
/// the two subscribers into its private `cancellables`) and asserts that
/// posting each notification advances `refreshInvocations` by one.
@MainActor
final class MemoriesViewModelObserverTests: XCTestCase {

    func testDidBecomeActiveNotificationTriggersRefresh() async {
        let viewModel = MemoriesViewModel()
        XCTAssertEqual(viewModel.refreshInvocations, 0, "Fresh instance must start at zero")

        NotificationCenter.default.post(
            name: NSApplication.didBecomeActiveNotification, object: nil
        )
        await Task.yield()
        try? await Task.sleep(nanoseconds: 50_000_000)

        XCTAssertEqual(
            viewModel.refreshInvocations, 1,
            "didBecomeActive must route to refreshMemoriesIfNeeded() via the activation subscriber"
        )
    }

    func testRefreshAllDataNotificationTriggersRefresh() async {
        let viewModel = MemoriesViewModel()

        NotificationCenter.default.post(name: .refreshAllData, object: nil)
        await Task.yield()
        try? await Task.sleep(nanoseconds: 50_000_000)

        XCTAssertEqual(
            viewModel.refreshInvocations, 1,
            ".refreshAllData (Cmd+R) must route to refreshMemoriesIfNeeded() via the refresh subscriber"
        )
    }

    func testDeallocatedViewModelDoesNotLeakObservers() async {
        // Ensures the `[weak self]` capture in the Combine sinks lets the
        // view model deallocate cleanly — no crash when the notifications
        // fire after the instance is gone.
        do {
            let viewModel = MemoriesViewModel()
            XCTAssertEqual(viewModel.refreshInvocations, 0)
        }
        // viewModel is out of scope and should be deallocated.
        NotificationCenter.default.post(
            name: NSApplication.didBecomeActiveNotification, object: nil
        )
        NotificationCenter.default.post(name: .refreshAllData, object: nil)
        await Task.yield()
        try? await Task.sleep(nanoseconds: 50_000_000)
        // If the weak capture misbehaved we'd crash above; reaching here is the assertion.
    }
}
