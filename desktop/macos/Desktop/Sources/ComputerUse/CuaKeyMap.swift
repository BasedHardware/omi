import Carbon.HIToolbox
import CoreGraphics
import Foundation

/// Key names as a model writes them, resolved against the keyboard the user
/// actually has.
///
/// Two lookups, for two different problems. Named keys (`return`, `escape`,
/// `left`) are physical positions and never move, so they are a table. Printable
/// characters are not: `cmd+z` is virtual key 6 on QWERTY and virtual key 26 on
/// AZERTY, and a hardcoded table silently sends the wrong shortcut to anyone not
/// on a US layout. Those are resolved by asking the current input source what
/// each key produces, which is the only answer that stays right when the user
/// switches layouts mid-session.
enum CuaKeyMap {
  struct Chord: Equatable {
    let keyCode: CGKeyCode
    let flags: CGEventFlags
  }

  /// Physical keys that have a name rather than a character.
  private static let namedKeys: [String: Int] = [
    "return": kVK_Return, "enter": kVK_Return, "tab": kVK_Tab, "space": kVK_Space,
    "delete": kVK_Delete, "backspace": kVK_Delete, "forwarddelete": kVK_ForwardDelete,
    "escape": kVK_Escape, "esc": kVK_Escape, "capslock": kVK_CapsLock,
    "left": kVK_LeftArrow, "right": kVK_RightArrow, "up": kVK_UpArrow, "down": kVK_DownArrow,
    "home": kVK_Home, "end": kVK_End, "pageup": kVK_PageUp, "pagedown": kVK_PageDown,
    "help": kVK_Help,
    "f1": kVK_F1, "f2": kVK_F2, "f3": kVK_F3, "f4": kVK_F4, "f5": kVK_F5, "f6": kVK_F6,
    "f7": kVK_F7, "f8": kVK_F8, "f9": kVK_F9, "f10": kVK_F10, "f11": kVK_F11, "f12": kVK_F12,
  ]

  private static let modifiers: [String: CGEventFlags] = [
    "cmd": .maskCommand, "command": .maskCommand, "meta": .maskCommand, "super": .maskCommand,
    "shift": .maskShift,
    "alt": .maskAlternate, "opt": .maskAlternate, "option": .maskAlternate,
    "ctrl": .maskControl, "control": .maskControl,
    "fn": .maskSecondaryFn, "function": .maskSecondaryFn,
  ]

  /// A chord written the way people write them: `cmd+shift+4`, `ctrl+c`, `escape`.
  ///
  /// The last segment is the key and everything before it is a modifier, so a
  /// literal `+` still works as `cmd++`. An unknown name is an error rather than
  /// a dropped modifier, because a silently weakened chord does something else
  /// entirely — `cmd+q` typed as `q` types a letter into whatever is focused.
  static func chord(from combination: String, layout: KeyboardLayout = .current()) -> Chord? {
    let segments =
      combination
      .split(separator: "+", omittingEmptySubsequences: false)
      .map { $0.trimmingCharacters(in: .whitespaces) }
    guard let last = segments.last else { return nil }
    // A trailing empty segment means the key itself is "+" (as in "cmd++").
    let keyName = last.isEmpty ? "+" : last
    let modifierNames = last.isEmpty ? segments.dropLast(2) : segments.dropLast()

    var flags: CGEventFlags = []
    for name in modifierNames {
      guard let flag = modifiers[name.lowercased()] else { return nil }
      flags.insert(flag)
    }

    if let named = namedKeys[keyName.lowercased()] {
      return Chord(keyCode: CGKeyCode(named), flags: flags)
    }
    guard keyName.count == 1, let character = keyName.first,
      let stroke = layout.stroke(for: character)
    else { return nil }
    if stroke.needsShift { flags.insert(.maskShift) }
    return Chord(keyCode: stroke.keyCode, flags: flags)
  }

  /// Just the modifiers, for a tool that holds them while doing something else
  /// (a command-click). An unknown name is nil rather than an empty set, so a
  /// typo does not quietly become a plain click.
  static func flags(from modifierList: String) -> CGEventFlags? {
    var flags: CGEventFlags = []
    for name in modifierList.split(separator: "+") {
      guard let flag = modifiers[name.trimmingCharacters(in: .whitespaces).lowercased()] else {
        return nil
      }
      flags.insert(flag)
    }
    return flags
  }

  /// What the keyboard currently attached to this Mac produces for each key.
  struct KeyboardLayout {
    struct Stroke: Equatable {
      let keyCode: CGKeyCode
      let needsShift: Bool
    }

    private let strokes: [Character: Stroke]

    init(strokes: [Character: Stroke]) {
      self.strokes = strokes
    }

    func stroke(for character: Character) -> Stroke? {
      strokes[character]
    }

    /// Built from the active input source, and rebuilt when the user switches to
    /// another one. Keyed by the source id because the layout data itself is an
    /// opaque blob with nothing cheaper to compare.
    static func current() -> KeyboardLayout {
      let sourceID = currentInputSourceID()
      if let cached = cache.value(for: sourceID) { return cached }
      let built = KeyboardLayout(strokes: readCurrentStrokes())
      cache.store(built, for: sourceID)
      return built
    }
  }

  private static let cache = LayoutCache()

  private final class LayoutCache: @unchecked Sendable {
    private let lock = NSLock()
    private var sourceID: String?
    private var layout: KeyboardLayout?

    func value(for sourceID: String?) -> KeyboardLayout? {
      lock.lock()
      defer { lock.unlock() }
      guard self.sourceID == sourceID else { return nil }
      return layout
    }

    func store(_ layout: KeyboardLayout, for sourceID: String?) {
      lock.lock()
      self.sourceID = sourceID
      self.layout = layout
      lock.unlock()
    }
  }

  private static func currentInputSourceID() -> String? {
    guard let source = TISCopyCurrentKeyboardLayoutInputSource()?.takeRetainedValue(),
      let raw = TISGetInputSourceProperty(source, kTISPropertyInputSourceID)
    else { return nil }
    return Unmanaged<CFString>.fromOpaque(raw).takeUnretainedValue() as String
  }

  /// Every character the current layout can produce unshifted or shifted, and
  /// the key that produces it. First key wins, so the main row beats the numeric
  /// keypad for digits.
  private static func readCurrentStrokes() -> [Character: KeyboardLayout.Stroke] {
    guard let source = TISCopyCurrentKeyboardLayoutInputSource()?.takeRetainedValue(),
      let raw = TISGetInputSourceProperty(source, kTISPropertyUnicodeKeyLayoutData)
    else { return [:] }
    let data = Unmanaged<CFData>.fromOpaque(raw).takeUnretainedValue() as Data

    var strokes: [Character: KeyboardLayout.Stroke] = [:]
    data.withUnsafeBytes { buffer in
      guard let layout = buffer.baseAddress?.assumingMemoryBound(to: UCKeyboardLayout.self) else {
        return
      }
      for keyCode in 0..<128 {
        for shifted in [false, true] {
          var deadKeyState: UInt32 = 0
          var characters = [UniChar](repeating: 0, count: 4)
          var length = 0
          let modifierKeyState: UInt32 = shifted ? UInt32(shiftKey >> 8) : 0
          let status = UCKeyTranslate(
            layout,
            UInt16(keyCode),
            UInt16(kUCKeyActionDown),
            modifierKeyState,
            UInt32(LMGetKbdType()),
            OptionBits(kUCKeyTranslateNoDeadKeysBit),
            &deadKeyState,
            characters.count,
            &length,
            &characters
          )
          guard status == noErr, length == 1,
            let scalar = Unicode.Scalar(characters[0]), !scalar.properties.isWhitespace
          else { continue }
          let character = Character(scalar)
          if strokes[character] == nil {
            strokes[character] = .init(keyCode: CGKeyCode(keyCode), needsShift: shifted)
          }
        }
      }
    }
    return strokes
  }
}
