//
//  SpineRowLeadingGridTests.swift — one leading grid for every row.
//
//  Attachment on the spine is air and the rail, never a horizontal offset: a strip of frames under
//  its conversation has to start at the same left edge as a strip standing on its own, or the same
//  kind of row reads as two different grids a group apart — the drift a user reads as misaligned
//  padding. The invariant is asserted on the mounted view tree, because it is a fact about frames,
//  not about constants.
//

import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class SpineRowLeadingGridTests: XCTestCase {
  // MARK: - Fixtures

  private func moment(_ id: Int64) -> SpineMoment {
    SpineMoment(
      id: id,
      timestamp: Date(timeIntervalSince1970: 1_785_000_000),
      appName: "Cursor",
      windowTitle: "omni",
      imagePath: nil,
      videoChunkPath: nil,
      frameOffset: nil)
  }

  private func momentsRow(isAttached: Bool) -> SpineRow {
    SpineRow(
      id: isAttached ? "conv-shot:1" : "shot:1",
      anchor: Date(timeIntervalSince1970: 1_785_000_000),
      kind: .screen,
      isAttached: isAttached,
      content: .moments(shown: [moment(1)], total: 1),
      searchText: "cursor")
  }

  // MARK: - The grid

  func testAnAttachedMomentStripStartsOnTheSameLeftGridAsALooseOne() throws {
    let loose = try stripLeadingX(row: momentsRow(isAttached: false))
    let attached = try stripLeadingX(row: momentsRow(isAttached: true))

    XCTAssertGreaterThan(loose, 0, "the strip should sit past the gutter")
    XCTAssertEqual(
      attached, loose, accuracy: 0.5,
      "a strip attached to the conversation above it must share the leading grid of a loose strip; "
        + "attachment is air and the rail, not a horizontal offset")
  }

  // MARK: - Mounting

  /// Lays the row out at the panel's real width and returns the strip's leading x.
  ///
  /// The row mounts in an ordered (but parked, click-through) window: SwiftUI only builds its native
  /// hierarchy — the part whose frames this test reads — once the view has window backing.
  private func stripLeadingX(row: SpineRow) throws -> CGFloat {
    let view = SpineRowView(
      row: row,
      showsIndent: true,
      onOpenConversation: { _ in },
      onOpenMemory: { _ in },
      onToggleTask: { _ in },
      onToggleStar: { _ in },
      onOpenMoment: { _, _ in },
      onShowAllMoments: {},
      onOpenBrainMap: {})

    let host = NSHostingView(rootView: view.frame(width: 900))
    host.frame = NSRect(x: 0, y: 0, width: 900, height: 160)
    let window = NSWindow(
      contentRect: host.frame,
      styleMask: [.borderless],
      backing: .buffered,
      defer: false)
    window.contentView = host
    NonintrusiveTestWindow.orderIn(window)
    defer {
      window.orderOut(nil)
      window.contentView = nil
    }
    host.layoutSubtreeIfNeeded()

    let scrollViews = Self.descendants(of: host).compactMap { $0 as? NSScrollView }
    let strip = try XCTUnwrap(
      scrollViews.min(by: { $0.frame.minX < $1.frame.minX }),
      "the mounted moments row should contain a scroll-backed strip")
    // Frames are parent-relative; the grid lives in the host's coordinates.
    return host.convert(strip.frame, from: strip.superview).minX
  }

  private static func descendants(of view: NSView) -> [NSView] {
    var result: [NSView] = []
    var stack = view.subviews
    while let next = stack.popLast() {
      result.append(next)
      stack.append(contentsOf: next.subviews)
    }
    return result
  }
}
