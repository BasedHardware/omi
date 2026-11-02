import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class MeetingMemoryBriefRenderingTests: XCTestCase {
  func testCitedCardRendersAtDesktopWidth() throws {
    let brief = MeetingMemoryBrief(
      eventID: "fixture-event",
      title: "Product sync",
      startsAt: Date(timeIntervalSince1970: 1_800_000_000),
      sourceConversationID: "fixture-conversation",
      sourceConversationTitle: "Previous product sync",
      facts: [
        MeetingMemoryBriefFact(
          kind: .decision, text: "Ship the opt-in pilot to dogfood first.",
          sourceConversationID: "fixture-conversation", sourceSegmentIDs: ["segment-1"]),
        MeetingMemoryBriefFact(
          kind: .followUp, text: "Share the launch checklist before Friday.",
          sourceConversationID: "fixture-conversation", sourceSegmentIDs: ["segment-2"]),
        MeetingMemoryBriefFact(
          kind: .openQuestion, text: "Who will collect review feedback?",
          sourceConversationID: "fixture-conversation", sourceSegmentIDs: ["segment-3"]),
      ])

    let size = NSSize(width: 680, height: 320)
    let host = NSHostingView(
      rootView: ZStack {
        Color.white
        MeetingMemoryBriefCard(brief: brief, onOpenSource: { _ in }, onDismiss: {})
          .padding(20)
      }
      .frame(width: size.width, height: size.height))
    host.appearance = InkGlass.appearance
    host.frame = NSRect(origin: .zero, size: size)

    let bitmap = try XCTUnwrap(host.bitmapImageRepForCachingDisplay(in: host.bounds))
    host.cacheDisplay(in: host.bounds, to: bitmap)
    XCTAssertGreaterThanOrEqual(bitmap.pixelsWide, 680)
    XCTAssertGreaterThanOrEqual(bitmap.pixelsHigh, 320)

    let background = try XCTUnwrap(bitmap.colorAt(x: 0, y: 0)?.usingColorSpace(.deviceRGB))
    XCTAssertGreaterThan(background.redComponent, 0.9)
    XCTAssertGreaterThan(background.greenComponent, 0.9)
    XCTAssertGreaterThan(background.blueComponent, 0.9)
    let inkPixels = inkPixelCount(in: bitmap)
    let inset = 40 * bitmap.pixelsWide / 680
    let regionPixels = (bitmap.pixelsWide - 2 * inset) * (bitmap.pixelsHigh - 2 * inset)
    // Text covers a small, roughly scale-invariant fraction of the card; 0.05% is far below
    // the ~0.2% measured at 2x and clears the same text rendered at 1x.
    XCTAssertGreaterThan(
      inkPixels * 2000, regionPixels,
      "The brief card should contain visible text, not an empty backdrop (ink \(inkPixels) of \(regionPixels) px)")

    if let path = ProcessInfo.processInfo.environment["OMI_MEETING_BRIEF_SNAPSHOT_PATH"] {
      let png = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
      try png.write(to: URL(fileURLWithPath: path), options: .atomic)
    }
  }

  /// Counts every dark device pixel inside the card's inset region. Sampling each pixel
  /// rather than a fixed grid makes the count independent of how thin glyph strokes
  /// align with the sample points, and of the backing scale factor.
  private func inkPixelCount(in bitmap: NSBitmapImageRep) -> Int {
    let inset = 40 * bitmap.pixelsWide / 680
    var inkPixels = 0
    for x in inset..<(bitmap.pixelsWide - inset) {
      for y in inset..<(bitmap.pixelsHigh - inset) {
        if let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB),
          (color.redComponent + color.greenComponent + color.blueComponent) / 3 < 0.3
        {
          inkPixels += 1
        }
      }
    }
    return inkPixels
  }
}
