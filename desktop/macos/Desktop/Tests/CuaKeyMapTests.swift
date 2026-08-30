import CoreGraphics
import XCTest

@testable import Omi_Computer

/// Chord parsing, against a keyboard the test owns rather than the one the
/// machine running it happens to have plugged in.
final class CuaKeyMapTests: XCTestCase {
  /// A pretend layout where `a` is key 0 and `A` needs shift, `z` is key 6, and
  /// `+` is key 24 shifted. Deliberately not a real US layout: the point is that
  /// nothing in the parser knows what a real one looks like.
  private let layout = CuaKeyMap.KeyboardLayout(strokes: [
    "a": .init(keyCode: 0, needsShift: false),
    "A": .init(keyCode: 0, needsShift: true),
    "z": .init(keyCode: 6, needsShift: false),
    "s": .init(keyCode: 1, needsShift: false),
    "+": .init(keyCode: 24, needsShift: true),
  ])

  func testAModifierChordResolvesToTheLayoutsKey() {
    let chord = CuaKeyMap.chord(from: "cmd+z", layout: layout)
    XCTAssertEqual(chord?.keyCode, 6)
    XCTAssertEqual(chord?.flags, .maskCommand)
  }

  func testEveryModifierSpellingIsAccepted() {
    XCTAssertEqual(
      CuaKeyMap.chord(from: "command+option+control+shift+s", layout: layout)?.flags,
      [.maskCommand, .maskAlternate, .maskControl, .maskShift])
    XCTAssertEqual(
      CuaKeyMap.chord(from: "meta+alt+ctrl+s", layout: layout)?.flags,
      [.maskCommand, .maskAlternate, .maskControl])
  }

  /// A character that only exists shifted brings its own shift, so `cmd+A` is
  /// the shortcut the user would press rather than the unshifted key.
  func testAShiftedCharacterCarriesItsShift() {
    let chord = CuaKeyMap.chord(from: "cmd+A", layout: layout)
    XCTAssertEqual(chord?.keyCode, 0)
    XCTAssertEqual(chord?.flags, [.maskCommand, .maskShift])
  }

  func testNamedKeysNeedNoLayout() {
    XCTAssertEqual(CuaKeyMap.chord(from: "escape", layout: layout)?.keyCode, 53)
    XCTAssertEqual(CuaKeyMap.chord(from: "return", layout: layout)?.keyCode, 36)
    XCTAssertEqual(CuaKeyMap.chord(from: "shift+tab", layout: layout)?.flags, .maskShift)
  }

  /// The separator can also be the key. `cmd++` is zoom in half the apps on the
  /// Mac, and splitting naively drops it.
  func testTheKeyCanItselfBeAPlus() {
    let chord = CuaKeyMap.chord(from: "cmd++", layout: layout)
    XCTAssertEqual(chord?.keyCode, 24)
    XCTAssertEqual(chord?.flags, [.maskCommand, .maskShift])
  }

  /// A misspelled modifier must not quietly become a bare keystroke: `cmd+q`
  /// read as `q` types a letter into whatever the user was writing.
  func testAnUnknownModifierIsRefused() {
    XCTAssertNil(CuaKeyMap.chord(from: "hyper+z", layout: layout))
  }

  func testAKeyTheLayoutCannotProduceIsRefused() {
    XCTAssertNil(CuaKeyMap.chord(from: "cmd+ß", layout: layout))
  }

  func testModifierOnlyParsingForAModifiedClick() {
    XCTAssertEqual(CuaKeyMap.flags(from: "cmd+shift"), [.maskCommand, .maskShift])
    XCTAssertNil(CuaKeyMap.flags(from: "cmd+bogus"))
  }
}
