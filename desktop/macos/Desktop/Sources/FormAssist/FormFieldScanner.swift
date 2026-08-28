import AppKit
import ApplicationServices
import Foundation

/// A UI element as form assist sees it: everything the AX tree said about it, minus the
/// live handle. Detection and labelling run on this, so they are testable without a
/// real window on screen.
struct FormElement: Sendable, Equatable {
  let role: String
  let title: String
  let value: String
  let placeholder: String
  let description: String
  let help: String
  let frame: CGRect

  init(
    role: String,
    title: String = "",
    value: String = "",
    placeholder: String = "",
    description: String = "",
    help: String = "",
    frame: CGRect = .zero
  ) {
    self.role = role
    self.title = title
    self.value = value
    self.placeholder = placeholder
    self.description = description
    self.help = help
    self.frame = frame
  }

  init(node: AXFormNode) {
    self.init(
      role: node.role,
      title: node.title,
      value: node.value,
      placeholder: node.placeholder,
      description: node.description,
      help: node.help,
      frame: node.frame
    )
  }

  var searchableText: String {
    [role, title, value, placeholder, description, help]
      .filter { !$0.isEmpty }
      .joined(separator: " ")
      .lowercased()
  }
}

/// One input the user still has to fill in.
struct FormField: Sendable, Equatable {
  let label: String
  let isEmpty: Bool
  let isSecure: Bool
}

/// Cheap identity of the window in front of the user, readable without walking the
/// accessibility tree. Used to decide whether a walk is worth doing at all, and whether
/// the card on screen still belongs to what the user is looking at.
///
/// Identity is the window, not its title. Titles move under you — a page sets its title
/// after it renders its fields, a tab picks up an unread count, a document gains a dirty
/// marker — and treating that as a new window made the card disappear and rebuild itself
/// seconds after the user first saw it.
struct FormWindowKey: Sendable, Equatable {
  let appName: String
  let windowTitle: String
  let windowID: CGWindowID?

  static func == (lhs: Self, rhs: Self) -> Bool {
    guard lhs.appName == rhs.appName else { return false }
    if let left = lhs.windowID, let right = rhs.windowID { return left == right }
    return lhs.windowTitle == rhs.windowTitle
  }
}

/// What the frontmost window looks like right now, in the only terms form assist needs.
struct FormSnapshot: Sendable, Equatable {
  let appName: String
  let windowTitle: String
  let fields: [FormField]
  let hasSubmitButton: Bool
  let windowFrame: CGRect?
  let windowID: CGWindowID?

  var emptyFields: [FormField] { fields.filter { $0.isEmpty && !$0.isSecure } }

  /// Identity of "this form". Re-deriving the same fingerprint means the user is looking
  /// at a form Omi has already answered, so it re-shows that card instead of paying for
  /// another model call.
  ///
  /// Deliberately excludes the window title. A page's title arrives after its fields do,
  /// so including it made the same form fingerprint differently either side of load, and
  /// the card was rebuilt from under the user a second after it appeared. Two forms with
  /// the same fields in the same app get the same answers anyway — the values come from
  /// the user's memories, never from the page.
  var fingerprint: String {
    ([appName] + fields.map(\.label).sorted()).joined(separator: "\u{1F}")
  }
}

/// Decides whether a window is a form worth offering help on, from the shape of its
/// inputs alone. Pure, so the whole cost contract is testable without a real window.
enum FormAssistGate {
  enum Decision: String, Equatable {
    case eligible
    case notAForm
    /// A password box means sign-in or sign-up. Omi has nothing useful to paste there,
    /// and a copy card over a credential field is the last place to guess.
    case credentialForm
    case nothingLeftToFill
  }

  /// Secure fields never count toward eligibility and are never offered, but their
  /// presence alone no longer refuses the form: a job application that ends in "create a
  /// password" is still an application. What refuses a form is having nothing else worth
  /// filling — which is exactly the shape of a sign-in or sign-up box.
  static func decide(fields: [FormField], hasSubmitButton: Bool) -> Decision {
    let secure = fields.filter(\.isSecure).count
    let fillable = fields.filter { $0.isEmpty && !$0.isSecure }.count
    guard fields.count >= 2 else { return .notAForm }
    // Half the fields being passwords means the page is *about* credentials — a login
    // box, a sign-up box, or both side by side, which is what a real login page looks
    // like: two username boxes and two password boxes, enough non-secure fields to pass
    // a plain count.
    guard secure * 2 < fields.count else { return .credentialForm }
    if fillable >= 3 || (fillable >= 2 && hasSubmitButton) { return .eligible }
    if secure > 0 { return .credentialForm }
    return fields.allSatisfy { !$0.isEmpty } ? .nothingLeftToFill : .notAForm
  }
}

/// Reads the frontmost window's accessibility tree and describes any form in it.
enum FormFieldScanner {
  private static let maxDepth = 14
  private static let maxNodes = 900

  /// Labels on a button that mean "this completes something the user was filling in".
  private static let submitTerms = [
    "submit", "apply", "send", "save", "continue", "next", "finish", "register",
    "create account", "sign up", "review", "checkout",
  ]

  private static let secureTerms = ["password", "passcode", "pin", "cvv", "security code"]

  /// Browser chrome and search boxes. They are text fields the user never wants filled
  /// from memory, and counting them inflates the field tally that decides eligibility —
  /// Safari's address bar alone contributed two "smart search field" entries.
  private static let ignoredLabelTerms = ["search", "address and search", "url"]

  /// Who is in front, without touching the accessibility tree.
  @MainActor
  static func frontWindowKey() -> FormWindowKey? {
    guard let app = NSWorkspace.shared.frontmostApplication,
      app.processIdentifier != ProcessInfo.processInfo.processIdentifier
    else { return nil }
    let info = ScreenCaptureService.getActiveWindowInfo()
    return FormWindowKey(
      appName: app.localizedName ?? "",
      windowTitle: info.windowTitle ?? "",
      windowID: info.windowID
    )
  }

  @MainActor
  static func scanFrontmostWindow() -> FormSnapshot? {
    guard AXIsProcessTrusted() else { return nil }
    guard let app = NSWorkspace.shared.frontmostApplication,
      app.processIdentifier != ProcessInfo.processInfo.processIdentifier
    else { return nil }

    let appElement = AXUIElementCreateApplication(app.processIdentifier)
    guard let window = AXFormTree.elementAttribute(appElement, "AXFocusedWindow")
    else { return nil }

    let elements =
      AXFormTree
      .collectNodes(from: window, maxDepth: maxDepth, maxNodes: maxNodes)
      .map(FormElement.init(node:))
    let windows = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]]
    let info = ScreenCaptureService.getActiveWindowInfo()
    let axTitle = AXFormTree.stringAttribute(window, "AXTitle")

    return FormSnapshot(
      appName: app.localizedName ?? "",
      windowTitle: axTitle.isEmpty ? (info.windowTitle ?? "") : axTitle,
      fields: fields(in: elements),
      hasSubmitButton: hasSubmitButton(in: elements),
      windowFrame: windows.flatMap {
        CloudConnectorFormAutomation.appKitWindowFrame(pid: app.processIdentifier, windows: $0)
      },
      windowID: info.windowID
    )
  }

  static func fields(in elements: [FormElement]) -> [FormField] {
    let captions = elements.filter { $0.role.lowercased().contains("statictext") && !$0.value.isEmpty }
    return elements.compactMap { element in
      guard isInput(element) else { return nil }
      let label = self.label(for: element, captions: captions)
      guard !label.isEmpty, !isIgnored(label) else { return nil }
      return FormField(
        label: label,
        isEmpty: element.value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
        isSecure: isSecure(element, label: label)
      )
    }
  }

  static func hasSubmitButton(in elements: [FormElement]) -> Bool {
    elements.contains { element in
      guard element.role.lowercased().contains("button") else { return false }
      let text = element.searchableText
      return submitTerms.contains { text.contains($0) }
    }
  }

  private static func isIgnored(_ label: String) -> Bool {
    let lowered = label.lowercased()
    return ignoredLabelTerms.contains { lowered.contains($0) }
  }

  private static func isInput(_ element: FormElement) -> Bool {
    let role = element.role.lowercased()
    return role.contains("textfield") || role.contains("textarea") || role.contains("combobox")
  }

  private static func isSecure(_ element: FormElement, label: String) -> Bool {
    if element.role.lowercased().contains("secure") { return true }
    let lowered = label.lowercased()
    return secureTerms.contains { lowered.contains($0) }
  }

  /// What a person would call this field. The element's own metadata first, then the
  /// nearest visible caption above or to the left of it — which is where the web puts
  /// labels that never reach `AXTitle`.
  static func label(for element: FormElement, captions: [FormElement]) -> String {
    for candidate in [element.title, element.placeholder, element.description, element.help] {
      let trimmed = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
      if !trimmed.isEmpty { return trimmed }
    }
    return nearestCaption(for: element, captions: captions) ?? ""
  }

  private static func nearestCaption(for element: FormElement, captions: [FormElement]) -> String? {
    // AX frames are top-left origin, so "above" means a smaller maxY.
    let field = element.frame
    guard field.width > 0, field.height > 0 else { return nil }

    let scored = captions.compactMap { caption -> (String, CGFloat)? in
      let text = caption.value.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !text.isEmpty, text.count <= 60 else { return nil }
      let above =
        caption.frame.maxY <= field.minY + 4 && field.minY - caption.frame.maxY <= 44
        && abs(caption.frame.minX - field.minX) <= field.width
      let leftOf =
        caption.frame.maxX <= field.minX + 4 && field.minX - caption.frame.maxX <= 60
        && abs(caption.frame.midY - field.midY) <= field.height
      guard above || leftOf else { return nil }
      return (text, hypot(caption.frame.midX - field.midX, caption.frame.midY - field.midY))
    }
    return scored.min(by: { $0.1 < $1.1 })?.0
  }
}
