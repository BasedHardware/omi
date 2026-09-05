import AppKit
import ApplicationServices
import CoreGraphics
import Foundation

/// Where dictated text lands. The protocol exists so the session's delivery
/// rules are testable without touching the clipboard or whatever app the
/// developer happens to have focused.
@MainActor
protocol TextInsertionSink: AnyObject {
  /// Puts `text` at the caret of the focused app in one step. Returns false
  /// when nothing could be posted, so the caller can fall back to `copy`.
  func paste(_ text: String) -> Bool
  /// Leaves `text` on the clipboard for the user to paste themselves.
  func copy(_ text: String)
  /// Whether the dictation is continuing a line — the caret sits right after
  /// a word or the punctuation that closed one — so it needs a separating
  /// space first. False when there is no caret context to read.
  func caretNeedsSeparatingSpace() -> Bool
  /// Identifies where a paste would land right now — the frontmost
  /// application and its key window. Nil when it cannot be read.
  func focusTarget() -> String?
}

extension TextInsertionSink {
  func caretNeedsSeparatingSpace() -> Bool { false }
  func focusTarget() -> String? { nil }
}

/// Delivers text the way a paste does: onto the general pasteboard, then one
/// ⌘V into whichever application owns keyboard focus, then the previous
/// clipboard contents back.
///
/// Pasting rather than typing keystrokes is what makes a whole paragraph land
/// at once, in every app: keystroke injection is slow for long text and drops
/// characters in Electron and Terminal first-responders, and a paste is the
/// one insertion every text field already handles. The floating bar is a
/// non-activating panel, so during push-to-talk focus is still the user's own
/// app — the caret they were last in.
@MainActor
final class PasteboardTextInsertionSink: TextInsertionSink {

  /// How long the focused app gets to read the pasteboard before the previous
  /// contents are put back. Apps read it synchronously on ⌘V; the delay only
  /// covers event delivery, and is generous for a slow first responder.
  private static let restoreDelay: TimeInterval = 0.6
  private static let vKeyCode: CGKeyCode = 9
  /// Clipboard managers honour this type by not recording the item, so a
  /// dictation does not pollute the user's clipboard history.
  private static let transientType = NSPasteboard.PasteboardType("org.nspasteboard.TransientType")

  /// A private-state source does not inherit live hardware modifiers. A locked
  /// turn is finished by a chord press, so the user may still be physically
  /// holding Option when the paste is posted; sourced from `.hidSystemState`
  /// that ⌘V would arrive as ⌥⌘V.
  private let source = CGEventSource(stateID: .privateState)

  /// The real user clipboard to put back, and the scheduled restore that does
  /// it, while a dictation sits on the pasteboard. Held so a second dictation
  /// within the restore window carries the *original* clipboard forward instead
  /// of saving the first dictation as if it were the user's.
  private var pendingRestore: (items: [[NSPasteboard.PasteboardType: Data]], task: Task<Void, Never>)?
  /// The pasteboard `changeCount` right after this sink wrote a dictation. If it
  /// still holds at restore time, nothing else wrote since (a ⌘V only reads), so
  /// the restore is safe; a higher count means the user copied something and
  /// that must win.
  private var writtenChangeCount = 0

  func paste(_ text: String) -> Bool {
    guard !text.isEmpty else { return false }
    let pasteboard = NSPasteboard.general
    // A dictation this sink is still holding is not the user's clipboard —
    // carry the original behind it forward rather than saving the dictation.
    let previous: [[NSPasteboard.PasteboardType: Data]]
    if let pending = pendingRestore, pasteboard.changeCount == writtenChangeCount {
      pending.task.cancel()
      previous = pending.items
    } else {
      pendingRestore?.task.cancel()
      previous = Self.snapshot(pasteboard)
    }
    pendingRestore = nil

    pasteboard.clearContents()
    let item = NSPasteboardItem()
    item.setString(text, forType: .string)
    item.setString("", forType: Self.transientType)
    guard pasteboard.writeObjects([item]) else {
      Self.restore(previous, to: pasteboard)
      return false
    }
    guard postCommandV() else {
      Self.restore(previous, to: pasteboard)
      return false
    }
    writtenChangeCount = pasteboard.changeCount
    let expectedCount = writtenChangeCount
    let task = Task { @MainActor [weak self] in
      let delay = UInt64(Self.restoreDelay * 1_000_000_000)
      try? await Task.sleep(nanoseconds: delay)
      guard !Task.isCancelled, let self else { return }
      self.pendingRestore = nil
      // A ⌘V reads without bumping changeCount; a higher count means the user
      // copied their own content, which must win.
      guard pasteboard.changeCount == expectedCount else { return }
      Self.restore(previous, to: pasteboard)
    }
    pendingRestore = (previous, task)
    return true
  }

  func copy(_ text: String) {
    guard !text.isEmpty else { return }
    let pasteboard = NSPasteboard.general
    pasteboard.clearContents()
    pasteboard.setString(text, forType: .string)
  }

  /// The frontmost application and its key window. The window is what
  /// catches focus moving *within* the app while the recognizer runs — a new
  /// document, a sheet, a chat switched to another thread — which a pid alone
  /// cannot see. Read from the window list, which needs no permission: the
  /// frontmost app's topmost normal-layer window is its key window.
  func focusTarget() -> String? {
    guard let app = NSWorkspace.shared.frontmostApplication else { return nil }
    let window = Self.keyWindowNumber(ownedBy: app.processIdentifier).map(String.init) ?? "?"
    return "\(app.processIdentifier):\(app.bundleIdentifier ?? ""):\(window)"
  }

  private static func keyWindowNumber(ownedBy pid: pid_t) -> Int? {
    let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
    guard let windows = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[CFString: Any]] else {
      return nil
    }
    // Front to back; the first normal-layer window the app owns is its key window.
    for window in windows {
      guard let owner = window[kCGWindowOwnerPID] as? pid_t, owner == pid,
        let layer = window[kCGWindowLayer] as? Int, layer == 0,
        let number = window[kCGWindowNumber] as? Int
      else { continue }
      return number
    }
    return nil
  }

  /// Whether dictation landing after `character` needs a space before it: yes
  /// after a word or the punctuation that closes one ("sentence." + "Next"),
  /// no after whitespace or anything that opens what follows — a bracket, a
  /// quote, a slash, a hyphen, "@". A rule on all non-whitespace put a stray
  /// space after "(" and after an opening quote.
  nonisolated static func needsSeparatingSpace(after character: Character) -> Bool {
    if character.isWhitespace || character.isNewline { return false }
    if character.isLetter || character.isNumber { return true }
    return !Self.openers.contains(character)
  }
  private nonisolated static let openers: Set<Character> = [
    "(", "[", "{", "<", "\"", "'", "“", "‘", "«", "/", "\\", "-", "–", "—", "_", "@", "#", "$", "€", "£", "~", "`",
  ]

  /// Reads one character behind the caret through Accessibility. A second
  /// dictation into the same line landed flush against the first ("voiceI
  /// think") because nothing knew what the caret was sitting after. Only the
  /// one character is fetched (`AXStringForRange`), never the document.
  func caretNeedsSeparatingSpace() -> Bool {
    var focusedRef: CFTypeRef?
    guard
      AXUIElementCopyAttributeValue(
        AXUIElementCreateSystemWide(), kAXFocusedUIElementAttribute as CFString, &focusedRef) == .success,
      let focusedRef, CFGetTypeID(focusedRef) == AXUIElementGetTypeID()
    else { return false }
    let element = unsafeDowncast(focusedRef, to: AXUIElement.self)
    var rangeRef: CFTypeRef?
    guard
      AXUIElementCopyAttributeValue(element, kAXSelectedTextRangeAttribute as CFString, &rangeRef) == .success,
      let rangeRef, CFGetTypeID(rangeRef) == AXValueGetTypeID()
    else { return false }
    let rangeValue = unsafeDowncast(rangeRef, to: AXValue.self)
    var selection = CFRange()
    guard AXValueGetValue(rangeValue, .cfRange, &selection), selection.location > 0 else { return false }
    var previous = CFRange(location: selection.location - 1, length: 1)
    guard let parameter = AXValueCreate(.cfRange, &previous) else { return false }
    var textRef: CFTypeRef?
    guard
      AXUIElementCopyParameterizedAttributeValue(
        element, kAXStringForRangeParameterizedAttribute as CFString, parameter, &textRef) == .success,
      let text = textRef as? String, let character = text.last
    else { return false }
    return Self.needsSeparatingSpace(after: character)
  }

  private func postCommandV() -> Bool {
    guard let down = CGEvent(keyboardEventSource: source, virtualKey: Self.vKeyCode, keyDown: true),
      let up = CGEvent(keyboardEventSource: source, virtualKey: Self.vKeyCode, keyDown: false)
    else { return false }
    down.flags = .maskCommand
    up.flags = .maskCommand
    down.post(tap: .cghidEventTap)
    up.post(tap: .cghidEventTap)
    return true
  }

  /// Every item's every representation, so a copied image or rich text is put
  /// back exactly as it was. An item already on a pasteboard cannot be written
  /// to it again, so the data is copied out rather than the items kept.
  private static func snapshot(_ pasteboard: NSPasteboard) -> [[NSPasteboard.PasteboardType: Data]] {
    (pasteboard.pasteboardItems ?? []).map { item in
      var representations: [NSPasteboard.PasteboardType: Data] = [:]
      for type in item.types {
        if let data = item.data(forType: type) { representations[type] = data }
      }
      return representations
    }
  }

  private static func restore(_ items: [[NSPasteboard.PasteboardType: Data]], to pasteboard: NSPasteboard) {
    pasteboard.clearContents()
    let restored = items.compactMap { representations -> NSPasteboardItem? in
      guard !representations.isEmpty else { return nil }
      let item = NSPasteboardItem()
      for (type, data) in representations { item.setData(data, forType: type) }
      return item
    }
    if !restored.isEmpty { pasteboard.writeObjects(restored) }
  }
}
