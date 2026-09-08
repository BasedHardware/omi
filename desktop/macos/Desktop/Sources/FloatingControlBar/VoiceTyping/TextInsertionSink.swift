import AppKit
import ApplicationServices
import CoreGraphics
import CryptoKit
import Foundation

/// An exact field, caret and document revision. Text is hashed, never logged or
/// persisted; the AX reference only lives for the current capture/undo window.
struct TextInsertionTarget: Equatable {
  let elementID: AnyHashable
  let processID: pid_t
  let bundleIdentifier: String
  let selection: NSRange
  let valueDigest: Data
  let needsSeparatingSpace: Bool

  func isSameField(as other: Self) -> Bool {
    elementID == other.elementID && processID == other.processID
      && bundleIdentifier == other.bundleIdentifier
  }
}

struct FocusedDictationText {
  let elementID: AnyHashable
  let processID: pid_t
  let bundleIdentifier: String
  let value: String
  let selection: NSRange
  let canReplaceSelection: Bool

  var target: TextInsertionTarget {
    let prefix = (value as NSString).substring(to: selection.location)
    return TextInsertionTarget(
      elementID: elementID, processID: processID, bundleIdentifier: bundleIdentifier,
      selection: selection, valueDigest: Self.digest(value),
      needsSeparatingSpace: selection.length == 0
        && prefix.last.map(PasteboardTextInsertionSink.needsSeparatingSpace(after:)) == true)
  }

  static func digest(_ value: String) -> Data { Data(SHA256.hash(data: Data(value.utf8))) }
}

/// A dispatched AX request can fail or time out after changing the editor.
/// Only a rejection before dispatch proves that nothing was written.
enum DictationTextReplacementResult: Equatable {
  case notAttempted
  case applied
  case uncertain
}

enum TextInsertionResult: Equatable {
  case inserted
  /// Legacy paste dispatch is accepted, but its asynchronous result cannot
  /// support a verified insertion receipt.
  case pastePosted
  case notInserted
  /// Text may already be partly or fully present. Do not copy for a retry.
  case uncertain
}

/// All AX mutations are addressed to a captured element, never a generic Undo
/// command. Injectable so the real validation boundary runs in hermetic tests.
@MainActor
protocol DictationTextAccess: AnyObject {
  func readFocusedText() -> FocusedDictationText?
  func replaceSelection(_ text: String, in target: TextInsertionTarget) -> DictationTextReplacementResult
  func select(_ range: NSRange, in target: TextInsertionTarget) -> Bool
}

@MainActor
protocol TextInsertionSink: AnyObject {
  func paste(_ text: String, into target: TextInsertionTarget) -> TextInsertionResult
  func copy(_ text: String)
  func focusTarget() -> TextInsertionTarget?
  /// Receipt availability only. The action must separately validate the editor.
  var canUndoInsertion: Bool { get }
  var insertionReceiptDidChange: (() -> Void)? { get set }
  func undoInsertion() -> Bool
  func discardInsertionReceipt()
}

extension TextInsertionSink {
  var canUndoInsertion: Bool { false }
  func undoInsertion() -> Bool { false }
  func discardInsertionReceipt() {}
}

/// Prefer an addressed AX insertion. Editors without writable selected text
/// keep their existing paste behavior, gated by the exact target at dispatch.
/// Only a synchronously verified AX insertion can offer Undo last dictation.
@MainActor
final class PasteboardTextInsertionSink: TextInsertionSink {
  private let access: DictationTextAccess
  private let now: () -> TimeInterval
  private let clipboardPaste: ((String, TextInsertionTarget) -> Bool)?
  private let clipboardCopy: ((String) -> Void)?
  private let sleepForReceiptExpiry: @MainActor (TimeInterval) async throws -> Void
  private var receiptExpiryTask: Task<Void, Never>?
  var insertionReceiptDidChange: (() -> Void)?
  private struct InsertionReceipt {
    let target: TextInsertionTarget
    let insertedRange: NSRange
    let originalDigest: Data
    let expiresAt: TimeInterval
  }
  private var insertionReceipt: InsertionReceipt?

  init(
    access: DictationTextAccess = AccessibilityDictationTextAccess(),
    now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
    clipboardPaste: ((String, TextInsertionTarget) -> Bool)? = nil,
    clipboardCopy: ((String) -> Void)? = nil,
    sleepForReceiptExpiry: @escaping @MainActor (TimeInterval) async throws -> Void = { remaining in
      try await Task.sleep(for: .seconds(remaining))
    }
  ) {
    self.access = access
    self.now = now
    self.clipboardPaste = clipboardPaste
    self.clipboardCopy = clipboardCopy
    self.sleepForReceiptExpiry = sleepForReceiptExpiry
  }

  deinit { receiptExpiryTask?.cancel() }

  func focusTarget() -> TextInsertionTarget? { access.readFocusedText()?.target }

  func paste(_ text: String, into target: TextInsertionTarget) -> TextInsertionResult {
    discardInsertionReceipt()
    guard !text.isEmpty, let before = access.readFocusedText(), before.target == target else { return .notInserted }
    if before.canReplaceSelection {
      // A reported write failure may be partial. Never retry with Cmd-V or
      // restore the whole document after attempting an addressed mutation.
      let replacement = access.replaceSelection(text, in: target)
      guard replacement != .notAttempted else { return .notInserted }
      let expected = (before.value as NSString).replacingCharacters(in: before.selection, with: text)
      guard let after = access.readFocusedText(), after.target.isSameField(as: target),
        after.value == expected,
        after.selection == NSRange(location: before.selection.location + (text as NSString).length, length: 0)
      else { return .uncertain }
      if before.selection.length == 0 {
        installInsertionReceipt(
          InsertionReceipt(
            target: after.target,
            insertedRange: NSRange(location: before.selection.location, length: (text as NSString).length),
            originalDigest: target.valueDigest, expiresAt: now() + 30))
      }
      return .inserted
    }
    guard access.readFocusedText()?.target == target else { return .notInserted }
    let pasted = clipboardPaste?(text, target) ?? pasteViaClipboard(text, into: target)
    if pasted {
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "voice_typing", from: "ax_selected_text", to: "clipboard_paste",
        reason: "policy", outcome: .degraded)
    }
    return pasted ? .pastePosted : .notInserted
  }

  /// Opening an Omi menu can temporarily hide the focused text element. A
  /// presentation read must not consume the receipt or decide where to edit.
  var canUndoInsertion: Bool {
    guard let receipt = insertionReceipt else { return false }
    return now() < receipt.expiresAt
  }

  func undoInsertion() -> Bool {
    guard canUndoInsertion, let receipt = insertionReceipt else { return false }
    // One shot, including failure: a later retry must never affect a new edit.
    discardInsertionReceipt()
    guard let focused = access.readFocusedText(), focused.canReplaceSelection,
      focused.target == receipt.target,
      access.select(receipt.insertedRange, in: receipt.target),
      let selected = access.readFocusedText(), selected.target.isSameField(as: receipt.target),
      selected.target.valueDigest == receipt.target.valueDigest,
      selected.selection == receipt.insertedRange,
      access.replaceSelection("", in: selected.target) != .notAttempted
    else { return false }
    guard let after = access.readFocusedText(), after.target.isSameField(as: receipt.target),
      after.target.valueDigest == receipt.originalDigest,
      after.selection == NSRange(location: receipt.insertedRange.location, length: 0)
    else { return false }
    return true
  }

  func discardInsertionReceipt() {
    receiptExpiryTask?.cancel()
    receiptExpiryTask = nil
    guard insertionReceipt != nil else { return }
    insertionReceiptDidChange?()
    insertionReceipt = nil
  }

  private func installInsertionReceipt(_ receipt: InsertionReceipt) {
    discardInsertionReceipt()
    insertionReceiptDidChange?()
    insertionReceipt = receipt
    let sleepForReceiptExpiry = self.sleepForReceiptExpiry
    let expiresAt = receipt.expiresAt
    receiptExpiryTask = Task { @MainActor [weak self] in
      while !Task.isCancelled {
        guard let remaining = self.map({ expiresAt - $0.now() }) else { return }
        // The monotonic timestamp remains the authority. An early wake sleeps
        // the remaining interval; cancellation fences a superseded receipt.
        guard remaining > 0 else {
          self?.discardInsertionReceipt()
          return
        }
        do { try await sleepForReceiptExpiry(remaining) } catch { return }
      }
    }
  }

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

  private func pasteViaClipboard(_ text: String, into target: TextInsertionTarget) -> Bool {
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
    guard access.readFocusedText()?.target == target, postCommandV(to: target.processID) else {
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
    if let clipboardCopy {
      clipboardCopy(text)
      return
    }
    let pasteboard = NSPasteboard.general
    pasteboard.clearContents()
    pasteboard.setString(text, forType: .string)
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

  private func postCommandV(to processID: pid_t) -> Bool {
    guard let down = CGEvent(keyboardEventSource: source, virtualKey: Self.vKeyCode, keyDown: true),
      let up = CGEvent(keyboardEventSource: source, virtualKey: Self.vKeyCode, keyDown: false)
    else { return false }
    down.flags = .maskCommand
    up.flags = .maskCommand
    down.postToPid(processID)
    up.postToPid(processID)
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

/// AX text support varies by editor. A missing value/range, secure field, or
/// invalid range means no reliable destination, so dictation falls back to copy.
@MainActor
final class AccessibilityDictationTextAccess: DictationTextAccess {
  func readFocusedText() -> FocusedDictationText? {
    let systemWide = AXUIElementCreateSystemWide()
    AXUIElementSetMessagingTimeout(systemWide, 0.2)
    guard AXIsProcessTrusted(), let app = NSWorkspace.shared.frontmostApplication,
      let focused = attribute(kAXFocusedUIElementAttribute, of: systemWide),
      CFGetTypeID(focused) == AXUIElementGetTypeID()
    else { return nil }
    let element = unsafeDowncast(focused, to: AXUIElement.self)
    AXUIElementSetMessagingTimeout(element, 0.2)
    var pid: pid_t = 0
    guard AXUIElementGetPid(element, &pid) == .success, pid == app.processIdentifier,
      let role = attribute(kAXRoleAttribute, of: element) as? String,
      [kAXTextFieldRole, kAXTextAreaRole, kAXComboBoxRole].contains(role),
      (attribute(kAXSubroleAttribute, of: element) as? String) != kAXSecureTextFieldSubrole,
      let value = attribute(kAXValueAttribute, of: element) as? String,
      value.utf16.count <= 200_000,
      let rangeRef = attribute(kAXSelectedTextRangeAttribute, of: element),
      CFGetTypeID(rangeRef) == AXValueGetTypeID()
    else { return nil }
    var range = CFRange()
    guard AXValueGetValue(unsafeDowncast(rangeRef, to: AXValue.self), .cfRange, &range),
      range.location >= 0, range.length >= 0, range.location <= value.utf16.count,
      range.length <= value.utf16.count - range.location
    else { return nil }
    var writable = DarwinBoolean(false)
    let canReplace =
      AXUIElementIsAttributeSettable(element, kAXSelectedTextAttribute as CFString, &writable) == .success
      && writable.boolValue
    return FocusedDictationText(
      elementID: AnyHashable(element), processID: pid, bundleIdentifier: app.bundleIdentifier ?? "",
      value: value, selection: NSRange(location: range.location, length: range.length),
      canReplaceSelection: canReplace)
  }

  func replaceSelection(_ text: String, in target: TextInsertionTarget) -> DictationTextReplacementResult {
    guard readFocusedText()?.target == target else { return .notAttempted }
    let object = target.elementID.base as AnyObject
    guard CFGetTypeID(object) == AXUIElementGetTypeID() else { return .notAttempted }
    let element = unsafeDowncast(object, to: AXUIElement.self)
    let result = AXUIElementSetAttributeValue(element, kAXSelectedTextAttribute as CFString, text as CFString)
    // Even a timeout may have applied. An unchanged immediate reread is not
    // proof of no write, because the editor may still be processing the request.
    return result == .success ? .applied : .uncertain
  }

  func select(_ range: NSRange, in target: TextInsertionTarget) -> Bool {
    guard readFocusedText()?.target == target else { return false }
    var selection = CFRange(location: range.location, length: range.length)
    guard let value = AXValueCreate(.cfRange, &selection) else { return false }
    let object = target.elementID.base as AnyObject
    guard CFGetTypeID(object) == AXUIElementGetTypeID() else { return false }
    let element = unsafeDowncast(object, to: AXUIElement.self)
    return AXUIElementSetAttributeValue(element, kAXSelectedTextRangeAttribute as CFString, value) == .success
  }

  private func attribute(_ name: String, of element: AXUIElement) -> CFTypeRef? {
    var value: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success else { return nil }
    return value
  }
}
