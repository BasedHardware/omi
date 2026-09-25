import AppKit
import XCTest

@testable import Omi_Computer

final class EscapeKeyDispatchTests: XCTestCase {
  @MainActor
  func testTasksEscapeCancelsInlineCreationBeforeHomeNavigation() {
    let window = NSWindow(contentRect: .zero, styleMask: [], backing: .buffered, defer: true)
    let viewModel = TasksViewModel()
    viewModel.isInlineCreating = true
    viewModel.inlineCreateAfterTaskId = "task"
    var navigatedHome = false
    let navigation = WindowEscapeKeyMonitor.shared.register(window: window, priority: .navigation) {
      navigatedHome = true
      return true
    }
    let content = WindowEscapeKeyMonitor.shared.register(window: window, priority: .content) {
      viewModel.handleEscape()
    }
    defer {
      WindowEscapeKeyMonitor.shared.unregister(content)
      WindowEscapeKeyMonitor.shared.unregister(navigation)
    }

    XCTAssertTrue(WindowEscapeKeyMonitor.shared.dispatchEscape(in: window))
    XCTAssertFalse(viewModel.isInlineCreating)
    XCTAssertNil(viewModel.inlineCreateAfterTaskId)
    XCTAssertFalse(navigatedHome)
  }

  @MainActor
  func testTasksEscapeDeselectsBeforeHomeNavigation() {
    let window = NSWindow(contentRect: .zero, styleMask: [], backing: .buffered, defer: true)
    let viewModel = TasksViewModel()
    viewModel.keyboardSelectedTaskId = "task"
    var navigatedHome = false
    let navigation = WindowEscapeKeyMonitor.shared.register(window: window, priority: .navigation) {
      navigatedHome = true
      return true
    }
    let content = WindowEscapeKeyMonitor.shared.register(window: window, priority: .content) {
      viewModel.handleEscape()
    }
    defer {
      WindowEscapeKeyMonitor.shared.unregister(content)
      WindowEscapeKeyMonitor.shared.unregister(navigation)
    }

    XCTAssertTrue(WindowEscapeKeyMonitor.shared.dispatchEscape(in: window))
    XCTAssertNil(viewModel.keyboardSelectedTaskId)
    XCTAssertFalse(navigatedHome)
  }

  @MainActor
  func testLiveNotesEscapeCancelsEditBeforeHomeNavigation() {
    let window = NSWindow(contentRect: .zero, styleMask: [], backing: .buffered, defer: true)
    var editingNoteId: Int64? = 1
    var navigatedHome = false
    let navigation = WindowEscapeKeyMonitor.shared.register(window: window, priority: .navigation) {
      navigatedHome = true
      return true
    }
    let editing = WindowEscapeKeyMonitor.shared.register(window: window, priority: .editing) {
      guard LiveNotesEscapeHandling.shouldCancelEdit(editingNoteId: editingNoteId) else { return false }
      editingNoteId = nil
      return true
    }
    defer {
      WindowEscapeKeyMonitor.shared.unregister(editing)
      WindowEscapeKeyMonitor.shared.unregister(navigation)
    }

    XCTAssertTrue(WindowEscapeKeyMonitor.shared.dispatchEscape(in: window))
    XCTAssertNil(editingNoteId)
    XCTAssertFalse(navigatedHome)
  }

  @MainActor
  func testLiveNotesEditPrecedesRewindContentRegardlessOfRegistrationOrder() {
    let window = NSWindow(contentRect: .zero, styleMask: [], backing: .buffered, defer: true)
    var editingNoteId: Int64? = 1
    var rewindHandled = false
    let editing = WindowEscapeKeyMonitor.shared.register(window: window, priority: .editing) {
      guard LiveNotesEscapeHandling.shouldCancelEdit(editingNoteId: editingNoteId) else { return false }
      editingNoteId = nil
      return true
    }
    let rewind = WindowEscapeKeyMonitor.shared.register(window: window, priority: .content) {
      rewindHandled = true
      return true
    }
    defer {
      WindowEscapeKeyMonitor.shared.unregister(rewind)
      WindowEscapeKeyMonitor.shared.unregister(editing)
    }

    XCTAssertTrue(WindowEscapeKeyMonitor.shared.dispatchEscape(in: window))
    XCTAssertNil(editingNoteId)
    XCTAssertFalse(rewindHandled)
  }

  @MainActor
  func testAtlasSelectionTakesEscapeBeforeLeavingThePage() {
    let window = NSWindow(contentRect: .zero, styleMask: [], backing: .buffered, defer: true)
    var selected = true
    var leftMap = false
    let navigation = WindowEscapeKeyMonitor.shared.register(window: window, priority: .navigation) {
      leftMap = true
      return true
    }
    let content = WindowEscapeKeyMonitor.shared.register(window: window, priority: .content) {
      switch MemoryAtlasDismissal.next(
        isSearching: false, hasSelection: selected, hasTrail: false, isInsideNeighbourhood: false)
      {
      case .selection:
        selected = false
        return true
      case .passThrough:
        leftMap = true
        return true
      default:
        return true
      }
    }
    defer {
      WindowEscapeKeyMonitor.shared.unregister(content)
      WindowEscapeKeyMonitor.shared.unregister(navigation)
    }

    XCTAssertTrue(WindowEscapeKeyMonitor.shared.dispatchEscape(in: window))
    XCTAssertFalse(selected)
    XCTAssertFalse(leftMap)
  }
}
