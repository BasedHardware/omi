import AppKit
import SwiftUI
import XCTest

@testable import OmiTheme
@testable import Omi_Computer

@MainActor
final class AppsHeaderRowLayoutTests: XCTestCase {
  func testSearchFieldIsCappedOnAWideWindow() {
    let recorder = AppsHeaderLayoutRecorder()
    layOut(width: 1000, recorder: recorder)

    guard let search = recorder.frame(of: .search) else {
      return XCTFail("the search field never laid out")
    }
    XCTAssertEqual(search.width, AppsHeaderMetrics.searchFieldMaxWidth, accuracy: 0.5)
  }

  func testLabelledFiltersRemainLegibleAtOrdinaryAndCompactWidths() {
    let intrinsicFilterWidth = NSHostingView(
      rootView: AppsHeaderFilterFixture().fixedSize()
    ).fittingSize.width

    for width in [720.0, 380.0] {
      let recorder = AppsHeaderLayoutRecorder()
      layOut(width: width, recorder: recorder)
      guard let filters = recorder.frame(of: .filters) else {
        return XCTFail("the filters never laid out at \(width)pt")
      }
      XCTAssertGreaterThanOrEqual(filters.width, intrinsicFilterWidth - 0.5)
    }
  }

  func testCreateControlMovesBelowFiltersWhenTheCompactRowWouldOverflow() {
    let recorder = AppsHeaderLayoutRecorder()
    let width: CGFloat = 380
    layOut(
      width: width,
      recorder: recorder,
      filters: Color.clear.frame(width: 280, height: AppsHeaderMetrics.controlHeight)
    )

    guard let filters = recorder.frame(of: .filters),
      let create = recorder.frame(of: .create)
    else {
      return XCTFail("the compact header controls never laid out")
    }

    XCTAssertLessThanOrEqual(filters.maxX, width + 0.5)
    XCTAssertLessThanOrEqual(create.maxX, width + 0.5)
    XCTAssertGreaterThanOrEqual(
      create.minY,
      filters.maxY - 0.5,
      "Create App should move below filters instead of extending the compact row"
    )
  }

  func testAppsToolbarControlsShareTheSearchFieldHeight() {
    let recorder = AppsHeaderLayoutRecorder()
    let host = NSHostingView(
      rootView: HStack(spacing: OmiSpacing.md) {
        AppsHeaderLayoutProbe(recorder: recorder, slot: .search) {
          Color.clear
            .frame(width: 240, height: AppsHeaderMetrics.controlHeight)
        }
        AppsHeaderLayoutProbe(recorder: recorder, slot: .installed) {
          FilterToggle(icon: "arrow.down.circle", label: "Installed", isActive: false) {}
        }
        AppsHeaderLayoutProbe(recorder: recorder, slot: .category) {
          SearchableDropdown(
            title: "Category",
            label: "Category",
            options: [SearchableDropdownOption(id: "", title: "All Categories")],
            selectedId: "",
            minWidth: 180,
            controlHeight: AppsHeaderMetrics.controlHeight,
            usesHeaderChrome: true
          ) { _ in }
        }
        AppsHeaderLayoutProbe(recorder: recorder, slot: .create) {
          SmallHeaderButton(icon: "app.badge.fill", label: "Create App", color: Ink.secondary) {}
        }
      }
      .fixedSize()
    )
    host.frame = NSRect(x: 0, y: 0, width: 900, height: 80)
    host.layoutSubtreeIfNeeded()

    for slot in [AppsHeaderLayoutSlot.search, .installed, .category, .create] {
      guard let frame = recorder.frame(of: slot) else {
        return XCTFail("\(slot) never laid out")
      }
      XCTAssertEqual(
        frame.height,
        AppsHeaderMetrics.controlHeight,
        accuracy: 0.5,
        "\(slot) should occupy the shared Apps toolbar height"
      )
    }
  }

  private func layOut(width: CGFloat, recorder: AppsHeaderLayoutRecorder) {
    layOut(width: width, recorder: recorder, filters: AppsHeaderFilterFixture())
  }

  private func layOut<Filters: View>(
    width: CGFloat,
    recorder: AppsHeaderLayoutRecorder,
    filters: Filters
  ) {
    let host = NSHostingView(
      rootView: AppsHeaderRow(
        search: {
          AppsHeaderLayoutProbe(recorder: recorder, slot: .search) {
            Color.clear.frame(maxWidth: .infinity).frame(height: AppsHeaderMetrics.controlHeight)
          }
        },
        filters: {
          AppsHeaderLayoutProbe(recorder: recorder, slot: .filters) {
            filters
          }
        },
        create: {
          AppsHeaderLayoutProbe(recorder: recorder, slot: .create) {
            Color.clear.frame(width: 100, height: AppsHeaderMetrics.controlHeight)
          }
        },
        dismiss: { EmptyView() }
      )
      .frame(width: width)
    )
    host.frame = NSRect(x: 0, y: 0, width: width, height: 200)
    host.layoutSubtreeIfNeeded()
  }
}

private struct AppsHeaderFilterFixture: View {
  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      Text("Installed")
        .padding(.horizontal, OmiSpacing.md)
      Text("All Categories")
        .padding(.horizontal, OmiSpacing.md)
    }
    .frame(height: AppsHeaderMetrics.controlHeight)
  }
}

private enum AppsHeaderLayoutSlot {
  case search
  case filters
  case installed
  case category
  case create
}

private final class AppsHeaderLayoutRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private var frames: [AppsHeaderLayoutSlot: CGRect] = [:]

  func record(_ slot: AppsHeaderLayoutSlot, _ frame: CGRect) {
    lock.lock()
    frames[slot] = frame
    lock.unlock()
  }

  func frame(of slot: AppsHeaderLayoutSlot) -> CGRect? {
    lock.lock()
    defer { lock.unlock() }
    return frames[slot]
  }
}

private struct AppsHeaderLayoutProbe: Layout {
  let recorder: AppsHeaderLayoutRecorder
  let slot: AppsHeaderLayoutSlot

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
    subviews.reduce(into: .zero) { size, subview in
      let child = subview.sizeThatFits(proposal)
      size.width = max(size.width, child.width)
      size.height = max(size.height, child.height)
    }
  }

  func placeSubviews(
    in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()
  ) {
    recorder.record(slot, bounds)
    for subview in subviews {
      subview.place(
        at: CGPoint(x: bounds.minX, y: bounds.minY),
        anchor: .topLeading,
        proposal: ProposedViewSize(width: bounds.width, height: bounds.height)
      )
    }
  }
}
