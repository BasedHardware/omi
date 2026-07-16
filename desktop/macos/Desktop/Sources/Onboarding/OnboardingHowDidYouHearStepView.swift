import OmiTheme
import SwiftUI

struct OnboardingHowDidYouHearStepView: View {
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  @AppStorage("onboardingHowDidYouHearSource") private var selectedSource: String = ""
  /// True when the step appeared with an answer already saved (a revisit).
  /// Only the first-ever selection auto-advances; revisits use Continue so
  /// changing your saved answer doesn't yank you forward.
  @State private var hadSelectionOnAppear = false
  @State private var advanceTask: Task<Void, Never>?

  enum SourceGlyph: Equatable {
    case emoji(String)
    case youtube
    case productHunt
  }

  static let sources: [(name: String, glyph: SourceGlyph)] = [
    ("Social media", .emoji("📱")),
    ("YouTube", .youtube),
    ("Friend", .emoji("👋")),
    ("Search engine", .emoji("🔍")),
    ("AI chat", .emoji("✨")),
    ("Podcast", .emoji("🎙️")),
    ("Colleague", .emoji("🧑‍💻")),
    ("Article", .emoji("📝")),
    ("Product Hunt", .productHunt),
    ("Newsletter", .emoji("📬")),
    ("Event", .emoji("🎟️")),
    ("Other", .emoji("💬")),
  ]

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Quick question",
      title: "How did you hear\nabout Omi?",
      description: "",
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        FlowLayout(spacing: OmiSpacing.sm) {
          ForEach(Self.sources, id: \.name) { source in
            OnboardingSelectableChip(
              title: source.name,
              leading: AnyView(glyphView(source.glyph)),
              isSelected: selectedSource == source.name
            ) {
              selectedSource = source.name
              AnalyticsManager.shared.onboardingHowDidYouHear(source: source.name)
              // First-ever answer auto-advances; on a revisit the user changes
              // the saved selection and moves on with the Continue button.
              if !hadSelectionOnAppear {
                advanceTask?.cancel()
                advanceTask = Task {
                  try? await Task.sleep(nanoseconds: 250_000_000)
                  guard !Task.isCancelled else { return }
                  onContinue()
                }
              }
            }
          }
        }

        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          if hadSelectionOnAppear {
            Button("Continue", action: onContinue)
              .buttonStyle(OmiButtonStyle(.primary))
              .keyboardShortcut(.defaultAction)
          }
        }
        .padding(.top, OmiSpacing.sm)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .onAppear {
        hadSelectionOnAppear = !selectedSource.isEmpty
      }
      .onDisappear {
        advanceTask?.cancel()
      }
    }
  }

  @ViewBuilder
  private func glyphView(_ glyph: SourceGlyph) -> some View {
    switch glyph {
    case .emoji(let emoji):
      Text(emoji)
        .font(.system(size: 13))
    case .youtube:
      ZStack {
        RoundedRectangle(cornerRadius: 3.5, style: .continuous)
          .fill(Color(red: 1, green: 0, blue: 0))
          .frame(width: 16, height: 12)
        Image(systemName: "play.fill")
          .font(.system(size: 6))
          .foregroundColor(.white)
      }
    case .productHunt:
      ZStack {
        Circle()
          .fill(Color(red: 0xDA / 255, green: 0x55 / 255, blue: 0x2F / 255))
          .frame(width: 14, height: 14)
        Text("P")
          .font(.system(size: 9, weight: .bold, design: .rounded))
          .foregroundColor(.white)
      }
    }
  }
}

// Uses FlowLayout from AppsPage.swift
