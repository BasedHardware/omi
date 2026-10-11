import ApplicationServices
import XCTest

@testable import Omi_Computer

final class AXAttributeCastingTests: XCTestCase {
  /// `AXUIElementCopyAttributeValue` is IPC against a foreign process: `.success` answers the
  /// attribute, it does not promise the value's type. The casts this seam replaces trapped the
  /// process when a buggy app answered `AXFocusedWindow`/`AXPosition` with the wrong CF type.
  func testWrongTypedValueResolvesNilInsteadOfTrapping() {
    let notAnElement: CFTypeRef = "not a window" as CFString
    XCTAssertNil(AXAttributeCasting.element(notAnElement))
    XCTAssertNil(AXAttributeCasting.value(notAnElement))
    XCTAssertEqual(AXAttributeCasting.elements(notAnElement), [])
  }

  func testCorrectlyTypedValuesRoundTrip() throws {
    let systemWide = AXUIElementCreateSystemWide()
    XCTAssertTrue(AXAttributeCasting.element(systemWide) === systemWide)

    var point = CGPoint(x: 7, y: 9)
    let axPoint = try XCTUnwrap(AXValueCreate(.cgPoint, &point))
    XCTAssertNotNil(AXAttributeCasting.value(axPoint))

    let elements: CFTypeRef = [systemWide, systemWide] as CFArray
    XCTAssertEqual(AXAttributeCasting.elements(elements).count, 2)
  }

  /// A mixed array keeps the real elements instead of trapping on the bad one.
  func testMixedElementArrayDropsOnlyTheBadEntries() {
    let systemWide = AXUIElementCreateSystemWide()
    let mixed: CFTypeRef = [systemWide, "junk" as CFString, systemWide] as CFArray
    let resolved = AXAttributeCasting.elements(mixed)
    XCTAssertEqual(resolved.count, 2)
    XCTAssertTrue(resolved.allSatisfy { $0 === systemWide })
  }

  func testNilResolvesEmpty() {
    XCTAssertNil(AXAttributeCasting.element(nil))
    XCTAssertNil(AXAttributeCasting.value(nil))
    XCTAssertEqual(AXAttributeCasting.elements(nil), [])
  }
}
