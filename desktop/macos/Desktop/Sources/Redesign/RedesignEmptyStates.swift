import SwiftUI

/// Reusable empty-state card — mockup `empty-states.html`.
///
/// The voice: never "No data." An empty screen is an invitation. Short,
/// first-person-from-omi. Any page can drop one of these in place of a list.
///
/// ```swift
/// InkEmptyState.noTasks            // preset
/// InkEmptyState(icon: "brain", title: "…", sub: "…")   // custom
/// ```
struct InkEmptyState: View {
  /// SF Symbol name for the recessed icon tile.
  let icon: String
  /// Serif headline.
  let title: String
  /// Muted supporting line.
  let sub: String

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Recessed icon tile.
      ZStack {
        RoundedRectangle(cornerRadius: 11, style: .continuous)
          .fill(Ink.surface2)
          .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
              .strokeBorder(Ink.hair, lineWidth: 1))
        Image(systemName: icon)
          .font(.system(size: 18, weight: .regular))
          .foregroundColor(Ink.muted)
      }
      .frame(width: 40, height: 40)

      Text(title)
        .font(InkFont.serif(21, .medium))
        .foregroundColor(Ink.ink)
        .tracking(-0.2)
        .fixedSize(horizontal: false, vertical: true)
        .padding(.top, 18)

      Text(sub)
        .font(InkFont.sans(13.5))
        .foregroundColor(Ink.muted)
        .lineSpacing(2)
        .fixedSize(horizontal: false, vertical: true)
        .padding(.top, 8)
    }
    .frame(maxWidth: .infinity, minHeight: 118, alignment: .topLeading)
    .padding(EdgeInsets(top: 36, leading: 30, bottom: 36, trailing: 30))
    .background(
      RoundedRectangle(cornerRadius: InkRadius.card, style: .continuous)
        .fill(Ink.surface)
        .overlay(
          RoundedRectangle(cornerRadius: InkRadius.card, style: .continuous)
            .strokeBorder(Ink.hair, lineWidth: 1))
    )
  }
}

// MARK: - Presets (copy lifted 1:1 from the mockup)

extension InkEmptyState {
  static let noTasks = InkEmptyState(
    icon: "checkmark",
    title: "No tasks yet",
    sub: "Nothing on your plate yet. I'll add things as they come up.")

  static let emptyBrain = InkEmptyState(
    icon: "brain",
    title: "Your brain, filling in",
    sub: "Your brain map fills in as you go. Give it a day.")

  static let quietInbox = InkEmptyState(
    icon: "tray",
    title: "Inbox is quiet",
    sub: "No drafts waiting. I'll ping you when something needs you.")

  static let askAnything = InkEmptyState(
    icon: "sparkles",
    title: "Ask me anything",
    sub: "Ask me anything — I remember what you saw and said.")
}

#if canImport(PreviewsMacros)
#Preview {
  ScrollView {
    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 20) {
      InkEmptyState.noTasks
      InkEmptyState.emptyBrain
      InkEmptyState.quietInbox
      InkEmptyState.askAnything
    }
    .padding(48)
    .frame(maxWidth: 820)
  }
  .frame(width: 900, height: 560)
  .background(Ink.canvas)
}
#endif
