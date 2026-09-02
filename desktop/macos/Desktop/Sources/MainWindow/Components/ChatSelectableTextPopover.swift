import AppKit
import OmiTheme
import SwiftUI

/// **The separate, non-live reading surface for one chat message.**
///
/// The transcript itself can never host native text selection: PR #10834 put
/// `.textSelection(.enabled)` back on settled rows and reopened
/// FC-selection-overlay-layout-loop in Omi Beta 0.12.146 — `SelectionOverlay`
/// pinned the main thread through `setFont`/intrinsic-size/AttributeGraph while
/// memory grew without bound. `.github/scripts/check_chat_selection_boundary.py`
/// keeps that door shut.
///
/// So the reader gets the other half of the remedy instead. "Select Text" opens
/// this popover, which is one `NSTextView` over one message, outside the
/// transcript's layout, mounted only when asked for and torn down on close. It
/// cannot participate in transcript loading, scrolling or resize, which is what
/// made selection unsafe in the first place. Nothing here uses SwiftUI's
/// `textSelection` — AppKit's own selection is what an `NSTextView` already is.
struct ChatSelectableTextPopover: View {
  let text: String
  let onClose: () -> Void

  /// Wide enough for a normal answer line without rewrapping it into a column,
  /// capped so a long reply scrolls inside the popover rather than growing one
  /// taller than the window.
  private static let width: CGFloat = 420
  private static let maxTextHeight: CGFloat = 360

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(spacing: OmiSpacing.sm) {
        Text("Select text")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundColor(Ink.primary)
        Spacer(minLength: 0)
        Text("⌘A · ⌘C")
          .scaledFont(size: OmiType.micro)
          .foregroundColor(Ink.secondary)
      }

      OmiSelectableTextView(text: text, maxHeight: Self.maxTextHeight)
        .frame(width: Self.width)
        .frame(maxHeight: Self.maxTextHeight)
    }
    .padding(OmiSpacing.md)
    // Escape. `.popover` is transient, but a click never has to happen for the
    // reader to be done reading.
    .onExitCommand(perform: onClose)
    .accessibilityLabel("Selectable message text")
  }
}

/// Read-only, selectable AppKit text. Deliberately **not** a SwiftUI `Text`:
/// one `NSTextView` owns its own selection, so there is no per-`Text`
/// `SelectionOverlay` to install and nothing for a parent rebuild to thrash.
struct OmiSelectableTextView: NSViewRepresentable {
  let text: String
  let maxHeight: CGFloat

  func makeNSView(context: Context) -> NSScrollView { Self.makeScrollView(text: text) }

  func updateNSView(_ scrollView: NSScrollView, context: Context) {
    Self.apply(text: text, to: scrollView)
  }

  /// The AppKit configuration, reachable without an `NSViewRepresentableContext`
  /// so a test can assert what this surface actually is.
  static func makeScrollView(text: String) -> NSScrollView {
    let scrollView = NSTextView.scrollableTextView()
    scrollView.drawsBackground = false
    scrollView.hasVerticalScroller = true
    scrollView.autohidesScrollers = true
    scrollView.borderType = .noBorder

    guard let textView = scrollView.documentView as? NSTextView else { return scrollView }
    textView.isEditable = false
    textView.isSelectable = true
    textView.isRichText = false
    textView.drawsBackground = false
    textView.textContainerInset = NSSize(width: 0, height: 0)
    textView.font = .systemFont(ofSize: 13)
    textView.textColor = .labelColor
    textView.isAutomaticQuoteSubstitutionEnabled = false
    textView.isAutomaticSpellingCorrectionEnabled = false
    textView.string = text

    // The reader asked for this surface in order to select; give them the
    // caret without a first click.
    DispatchQueue.main.async {
      textView.window?.makeFirstResponder(textView)
    }
    return scrollView
  }

  /// A rebuild replaces a string on the one text view; it never installs a
  /// second selection overlay.
  static func apply(text: String, to scrollView: NSScrollView) {
    guard let textView = scrollView.documentView as? NSTextView else { return }
    if textView.string != text { textView.string = text }
  }

  /// Hug short messages; scroll long ones instead of growing past the cap.
  func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSScrollView, context: Context) -> CGSize? {
    guard let textView = nsView.documentView as? NSTextView,
      let container = textView.textContainer,
      let layoutManager = textView.layoutManager
    else { return nil }

    let width = proposal.width ?? container.size.width
    container.containerSize = NSSize(width: width, height: .greatestFiniteMagnitude)
    layoutManager.ensureLayout(for: container)
    let used = layoutManager.usedRect(for: container).height
    return CGSize(width: width, height: min(max(used, 20), maxHeight))
  }
}
