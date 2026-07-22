import SwiftUI

/// Collects the on-screen frames of the sidebar nav items (keyed by
/// `SidebarNavItem.rawValue`) so the post-onboarding coach-marks can point at the
/// real buttons. Each sidebar item sets this via `.anchorPreference`.
struct SidebarCoachAnchorKey: PreferenceKey {
  static let defaultValue: [Int: Anchor<CGRect>] = [:]
  static func reduce(value: inout [Int: Anchor<CGRect>], nextValue: () -> [Int: Anchor<CGRect>]) {
    value.merge(nextValue()) { $1 }
  }
}

/// One coach-mark: which sidebar item to spotlight + the copy shown beside it.
struct OnboardingCoachStep {
  let itemRawValue: Int
  let title: String
  let body: String
}

/// Full-window coach-mark overlay: dims everything, spotlights the current
/// sidebar item, and shows a tooltip card beside it with Next / Skip. Tapping
/// anywhere advances. Pure SwiftUI, positioned from the item's live frame.
struct OnboardingWalkthroughOverlay: View {
  let steps: [OnboardingCoachStep]
  let index: Int
  let anchors: [Int: Anchor<CGRect>]
  let onNext: () -> Void
  let onSkip: () -> Void

  private var step: OnboardingCoachStep { steps[min(max(index, 0), steps.count - 1)] }

  var body: some View {
    GeometryReader { proxy in
      let rect: CGRect? = anchors[step.itemRawValue].map { proxy[$0] }
      ZStack(alignment: .topLeading) {
        // Dim the whole window except a rounded cut-out over the item.
        Path { path in
          path.addRect(CGRect(origin: .zero, size: proxy.size))
          if let r = rect {
            path.addRoundedRect(in: r.insetBy(dx: -6, dy: -6), cornerSize: CGSize(width: 12, height: 12))
          }
        }
        .fill(Color.black.opacity(0.62), style: FillStyle(eoFill: true))
        .contentShape(Rectangle())
        .onTapGesture { onNext() }

        if let r = rect {
          RoundedRectangle(cornerRadius: 12, style: .continuous)
            .stroke(Color.white.opacity(0.9), lineWidth: 2)
            .frame(width: r.width + 12, height: r.height + 12)
            .position(x: r.midX, y: r.midY)
            .allowsHitTesting(false)

          tooltip(near: r, in: proxy.size)
        }
      }
      .ignoresSafeArea()
    }
    .transition(.opacity)
  }

  private func tooltip(near rect: CGRect, in size: CGSize) -> some View {
    let cardWidth: CGFloat = 268
    // Sidebar is on the left, so place the card to the item's right, clamped.
    let x = min(rect.maxX + 24 + cardWidth / 2, size.width - cardWidth / 2 - 20)
    let y = min(max(rect.midY, 96), size.height - 130)
    let isLast = index + 1 >= steps.count
    return VStack(alignment: .leading, spacing: 8) {
      Text(step.title).font(.system(size: 15, weight: .semibold)).foregroundColor(.white)
      Text(step.body).font(.system(size: 13)).foregroundColor(.white.opacity(0.72))
        .fixedSize(horizontal: false, vertical: true)
      HStack(spacing: 12) {
        Text("\(index + 1) / \(steps.count)").font(.system(size: 11, weight: .medium))
          .foregroundColor(.white.opacity(0.4))
        Spacer()
        Button(action: onSkip) {
          Text("Skip").font(.system(size: 12)).foregroundColor(.white.opacity(0.55))
        }
        .buttonStyle(.plain)
        Button(action: onNext) {
          Text(isLast ? "Got it" : "Next")
            .font(.system(size: 13, weight: .semibold)).foregroundColor(.black)
            .padding(.horizontal, 16).padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Color.white))
        }
        .buttonStyle(.plain)
      }
      .padding(.top, 2)
    }
    .padding(14)
    .frame(width: cardWidth, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Color(red: 0.12, green: 0.12, blue: 0.13))
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .stroke(Color.white.opacity(0.12), lineWidth: 1))
    )
    .shadow(color: .black.opacity(0.45), radius: 22, y: 8)
    .position(x: x, y: y)
  }
}
