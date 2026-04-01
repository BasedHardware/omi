import SwiftUI

struct OnboardingHowDidYouHearStepView: View {
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  @State private var selectedSource: String?
  @State private var shuffledSources: [String] = []

  private static let sources = [
    "Social media",
    "YouTube",
    "Newsletter",
    "AI chat",
    "Search engine",
    "Event",
    "Friend",
    "Colleague",
    "Podcast",
    "Article",
    "Product Hunt",
    "Other",
  ]

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Quick question",
      title: "How did you hear\nabout Omi?",
      description: nil,
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: 12) {
        FlowLayout(spacing: 10) {
          ForEach(shuffledSources, id: \.self) { source in
            OnboardingSelectableChip(
              title: source,
              isSelected: selectedSource == source
            ) {
              selectedSource = source
              AnalyticsManager.shared.onboardingHowDidYouHear(source: source)
              DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                onContinue()
              }
            }
          }
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .onAppear {
        if shuffledSources.isEmpty {
          shuffledSources = Self.sources.shuffled()
        }
      }
    }
  }
}

/// Simple flow layout that wraps chips to the next line when they exceed width.
struct FlowLayout: Layout {
  var spacing: CGFloat = 10

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
    let result = arrange(proposal: proposal, subviews: subviews)
    return result.size
  }

  func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
    let result = arrange(proposal: proposal, subviews: subviews)
    for (index, position) in result.positions.enumerated() {
      subviews[index].place(
        at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y),
        proposal: .unspecified
      )
    }
  }

  private func arrange(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
    let maxWidth = proposal.width ?? .infinity
    var positions: [CGPoint] = []
    var x: CGFloat = 0
    var y: CGFloat = 0
    var rowHeight: CGFloat = 0
    var totalHeight: CGFloat = 0

    for subview in subviews {
      let size = subview.sizeThatFits(.unspecified)
      if x + size.width > maxWidth && x > 0 {
        x = 0
        y += rowHeight + spacing
        rowHeight = 0
      }
      positions.append(CGPoint(x: x, y: y))
      rowHeight = max(rowHeight, size.height)
      x += size.width + spacing
      totalHeight = y + rowHeight
    }

    return (CGSize(width: maxWidth, height: totalHeight), positions)
  }
}
