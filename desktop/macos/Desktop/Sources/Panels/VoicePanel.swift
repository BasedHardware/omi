import AppKit
import Foundation

/// One entry on a voice-requested panel: a value with a name, or a passage without one.
struct VoicePanelItem: Sendable, Equatable {
  let label: String
  let text: String
}

/// The voice tools' view of the shared panel.
///
/// `PanelSession` owns the card on screen and how long it lives; this is the part that
/// belongs to the voice surface — turning loosely-typed items into rows, and deciding
/// that a panel of the user's own details is about the user rather than about the tab
/// they happen to be looking at.
@MainActor
enum VoicePanel {
  /// Enough rows to answer with, few enough to read. Past this the model is writing a
  /// document, not putting something on screen to copy.
  static let maxItems = 12
  static let maxTextLength = 4_000
  /// Beyond one line at the card's width, a value reads as a passage and is wrapped.
  private static let wrapThreshold = 56

  /// A panel of plain values, from `show_panel`. About the user, not the screen: it
  /// survives tab changes and leaves with the app.
  @discardableResult
  static func present(title: String, items: [VoicePanelItem]) -> Int? {
    let fields = copyFields(from: items)
    guard !fields.isEmpty else { return nil }
    PanelSession.present(
      title: title, subtitle: subtitle(for: fields), fields: fields, grain: .app,
      origin: .requested)
    return fields.count
  }

  @discardableResult
  static func reopen() -> Int? { PanelSession.reopen() }

  @discardableResult
  static func dismiss() -> Bool { PanelSession.dismiss() }

  static func copyFields(from items: [VoicePanelItem]) -> [CloudConnectorCopyField] {
    items
      .map {
        (
          label: $0.label.trimmingCharacters(in: .whitespacesAndNewlines),
          text: String($0.text.prefix(maxTextLength)).trimmingCharacters(in: .whitespacesAndNewlines)
        )
      }
      .filter { !$0.text.isEmpty }
      .prefix(maxItems)
      .enumerated()
      .map { index, item in
        CloudConnectorCopyField(
          // Labels repeat and may be empty; the position is the only unique id.
          id: "voice-\(index)",
          label: item.label,
          value: item.text,
          // Nothing here came from the user's credential store — masking a value the
          // model was asked to show would hide the answer behind its own label.
          masksValue: false,
          wraps: item.label.isEmpty || item.text.count > wrapThreshold
        )
      }
  }

  private static func subtitle(for fields: [CloudConnectorCopyField]) -> String {
    fields.count == 1 ? "Copy it with the button." : "Copy each with its button."
  }
}
