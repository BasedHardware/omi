//
//  OmiToast.swift — the main window's transient feedback, in one place.
//
//  Before this there were two undo toasts that looked like two products (a dark filled capsule in
//  Tasks, a glass bar with an X in Memories — and that X *committed* the delete, the opposite of what
//  an X means everywhere else) and copy actions that confirmed nothing at all when triggered from a
//  menu.
//
//  - `UndoToast` — "Memory deleted · Undo". No close button: the toast times out on its own and the
//    delete commits then. There is no gesture here whose meaning is "destroy it sooner".
//  - `OmiToastCenter.confirm(_:)` — a one-line confirmation ("Transcript copied") for actions that
//    have no button of their own to turn into a checkmark, such as a context-menu item. Mounted once
//    at the shell root by `.omiToastHost()`.
//
//  See `docs/ux-contract.md` (INV-UI-2).
//

import OmiTheme
import SwiftUI

/// The undo toast every deferred delete shows.
struct UndoToast: View {
  /// What happened, as a past-tense sentence: "Memory deleted", "Task deleted".
  let message: String
  /// The item, so the reader knows which one — "Call the dentist".
  var detail: String?
  /// How many deletes the Undo would walk back, when the owner keeps a stack.
  var count: Int = 1
  let onUndo: () -> Void

  var body: some View {
    HStack(spacing: OmiSpacing.md) {
      Image(systemName: "trash")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)

      VStack(alignment: .leading, spacing: 0) {
        Text(count > 1 ? "\(message) (\(count))" : message)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
          .lineLimit(1)
        if let detail, !detail.isEmpty {
          Text(detail)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .lineLimit(1)
            .truncationMode(.tail)
        }
      }

      Spacer(minLength: OmiSpacing.md)

      Button("Undo", action: onUndo)
        .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        .help("Undo")
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md)
    .frame(maxWidth: 420)
    .glassFloatingBar()
    .accessibilityElement(children: .contain)
    .accessibilityLabel(detail.map { "\(message): \($0)" } ?? message)
  }
}

// MARK: - Confirmations

@MainActor
final class OmiToastCenter: ObservableObject {
  static let shared = OmiToastCenter()

  struct Toast: Equatable, Identifiable {
    let id = UUID()
    let message: String
    var systemImage: String = "checkmark"
  }

  @Published private(set) var current: Toast?
  private var dismissTask: Task<Void, Never>?

  /// Shows a one-line confirmation for `OmiFeedbackTiming.confirmation`.
  func confirm(_ message: String) {
    show(Toast(message: message))
  }

  /// A one-line notice that is not a success ("Merge failed"), shown for the informational time.
  func notice(_ message: String, systemImage: String = "info.circle") {
    show(Toast(message: message, systemImage: systemImage), duration: OmiFeedbackTiming.informational)
  }

  private func show(_ toast: Toast, duration: TimeInterval = OmiFeedbackTiming.confirmation) {
    current = toast
    dismissTask?.cancel()
    dismissTask = Task { @MainActor [weak self] in
      try? await Task.sleep(nanoseconds: UInt64(duration * 1_000_000_000))
      guard !Task.isCancelled, self?.current?.id == toast.id else { return }
      self?.current = nil
    }
  }

  /// Copies `text` and confirms with `message`. Returns whether anything was copied; an empty
  /// string copies nothing and shows "Nothing to copy" instead of a false "Copied".
  @discardableResult
  func copy(_ text: String, confirming message: String = "Copied") -> Bool {
    if OmiClipboard.copy(text) {
      confirm(message)
      return true
    }
    notice("Nothing to copy")
    return false
  }
}

private struct OmiToastHost: ViewModifier {
  @ObservedObject private var center = OmiToastCenter.shared

  func body(content: Content) -> some View {
    content.overlay(alignment: .bottom) {
      if let toast = center.current {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: toast.systemImage)
            .scaledFont(size: OmiType.caption, weight: .semibold)
          Text(toast.message)
            .scaledFont(size: OmiType.caption, weight: .medium)
        }
        .foregroundColor(Ink.primary)
        .padding(.horizontal, OmiSpacing.lg)
        .padding(.vertical, OmiSpacing.sm)
        .glassFloatingBar()
        .padding(.bottom, OmiSpacing.xxl)
        .transition(.opacity)
        .id(toast.id)
        .allowsHitTesting(false)
        .accessibilityAddTraits(.updatesFrequently)
      }
    }
    .omiAnimation(.easeOut(duration: 0.15), value: center.current)
  }
}

extension View {
  /// Mount once, at the shell root, so every page's confirmations land in the same place.
  func omiToastHost() -> some View {
    modifier(OmiToastHost())
  }
}
