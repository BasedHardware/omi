import SwiftUI

/// Light-mode ("warm paper") onboarding chrome + scaffold for the redesigned flow.
///
/// Mirrors the mockup's `ob-*` screens: an `omi` wordmark, a 7-segment progress
/// rail, an optional Skip affordance, an optional BuddyRing, a serif eyebrow /
/// headline / body block, a content slot, and pill-soft `InkButton` CTAs.
///
/// Every redesigned step composes this — the *wiring* stays in the existing
/// coordinator / step closures; only the visuals + copy change.

// MARK: - Beat mapping (19 functional steps → 7 narrative beats)

enum RedesignOnboarding {
  /// Maps a functional step index onto one of the mockup's 7 progress beats.
  static func beat(forStep step: Int) -> Int {
    switch step {
    case 0, 1, 2: return 1  // Name / Language / HowDidYouHear → welcome
    case 3: return 2  // Trust → promise
    case 4, 5, 7, 8, 9: return 3  // permissions
    case 6, 14, 15: return 4  // FileScan / DataSources / Exports → import
    case 10, 11, 12, 13: return 5  // shortcuts + demos → "see it in action"
    case 16, 17: return 6  // Goal / BYOK
    default: return 7  // Tasks → you're set
    }
  }
}

// MARK: - Progress rail (7 segments)

struct RedesignProgRail: View {
  let beat: Int  // 1...7

  var body: some View {
    HStack(spacing: 6) {
      ForEach(1...7, id: \.self) { k in
        Capsule(style: .continuous)
          .fill(k == beat ? Ink.accent : (k < beat ? Ink.ink : Ink.hair2))
          .frame(width: k == beat ? 30 : 18, height: 4)
      }
    }
    .animation(.easeInOut(duration: 0.2), value: beat)
  }
}

// MARK: - Top chrome (wordmark · rail · skip)

struct RedesignOnboardingChrome: View {
  let beat: Int
  var showsSkip: Bool = false
  var onSkip: (() -> Void)? = nil
  var onForceComplete: (() -> Void)? = nil

  var body: some View {
    HStack(spacing: 0) {
      Text("omi")
        .inkWordmark(20)
        .contentShape(Rectangle())
        .onLongPressGesture(minimumDuration: 1) { onForceComplete?() }
        .accessibilityLabel("omi")

      Spacer(minLength: 12)
      RedesignProgRail(beat: beat)
      Spacer(minLength: 12)

      if showsSkip, let onSkip {
        Button(action: onSkip) {
          Text("Skip").font(InkFont.sans(13)).foregroundColor(Ink.faint)
        }
        .buttonStyle(.plain)
        .frame(minWidth: 34, alignment: .trailing)
      } else {
        Color.clear.frame(width: 34, height: 1)
      }
    }
    .padding(.horizontal, 30)
    .padding(.vertical, 22)
  }
}

// MARK: - Centered scaffold

struct RedesignOnboardingScaffold<Content: View>: View {
  let beat: Int
  var eyebrow: String = ""
  var title: String
  var subtitle: String = ""
  var titleSize: CGFloat = 30
  var showsBuddy: Bool = false
  var buddyColor: Color = Ink.ink
  var centeredText: Bool = true
  var showsSkip: Bool = false
  var onSkip: (() -> Void)? = nil
  var onForceComplete: (() -> Void)? = nil
  var maxWidth: CGFloat = 560
  @ViewBuilder var content: () -> Content

  var body: some View {
    VStack(spacing: 0) {
      RedesignOnboardingChrome(
        beat: beat, showsSkip: showsSkip, onSkip: onSkip, onForceComplete: onForceComplete)

      GeometryReader { geo in
        ScrollView(showsIndicators: false) {
          VStack(alignment: centeredText ? .center : .leading, spacing: 18) {
            if showsBuddy {
              BuddyRing(diameter: 56, dot: 7, color: buddyColor).padding(.bottom, 6)
            }
            if !eyebrow.isEmpty {
              Text(eyebrow).inkEyebrow()
            }
            Text(title)
              .inkDisplay(titleSize)
              .multilineTextAlignment(centeredText ? .center : .leading)
              .fixedSize(horizontal: false, vertical: true)
            if !subtitle.isEmpty {
              Text(subtitle)
                .inkBody()
                .multilineTextAlignment(centeredText ? .center : .leading)
                .frame(maxWidth: 440, alignment: centeredText ? .center : .leading)
                .fixedSize(horizontal: false, vertical: true)
            }
            content()
              .padding(.top, 6)
          }
          .frame(maxWidth: maxWidth, alignment: centeredText ? .center : .leading)
          .frame(
            minWidth: 0, maxWidth: .infinity, minHeight: geo.size.height,
            maxHeight: .infinity, alignment: .center
          )
          .padding(.horizontal, 44)
          .padding(.vertical, 24)
        }
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
  }
}

// MARK: - Shared light building blocks

/// A light warm-paper text field matching the mockup `.input`.
struct RedesignOnboardingField: View {
  var placeholder: String
  @Binding var text: String
  var secure: Bool = false
  var maxWidth: CGFloat? = 360

  var body: some View {
    Group {
      if secure {
        SecureField(placeholder, text: $text)
      } else {
        TextField(placeholder, text: $text)
      }
    }
    .textFieldStyle(.plain)
    .font(InkFont.sans(15))
    .foregroundColor(Ink.ink)
    .padding(.horizontal, 16)
    .padding(.vertical, 13)
    .frame(maxWidth: maxWidth)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(Ink.surface)
        .overlay(
          RoundedRectangle(cornerRadius: 12, style: .continuous)
            .strokeBorder(Ink.hair2, lineWidth: 1))
    )
  }
}

/// A selectable pill chip (mockup `.pill.goal-chip`).
struct RedesignOnboardingChip: View {
  let title: String
  let selected: Bool
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Text(title)
        .font(InkFont.sans(14, selected ? .semibold : .medium))
        .foregroundColor(selected ? Ink.accentStrong : Ink.body)
        .padding(.horizontal, 18)
        .frame(height: 40)
        .background(
          Capsule(style: .continuous)
            .fill(selected ? Ink.accentTint : Ink.surface)
            .overlay(
              Capsule(style: .continuous)
                .strokeBorder(selected ? Ink.accent : Ink.hair2, lineWidth: 1))
        )
    }
    .buttonStyle(.plain)
  }
}

/// An inline error line in warn ink.
struct RedesignOnboardingError: View {
  let message: String
  var body: some View {
    Text(message)
      .font(InkFont.sans(12, .medium))
      .foregroundColor(Ink.warnText)
      .multilineTextAlignment(.center)
      .fixedSize(horizontal: false, vertical: true)
  }
}

// MARK: - Second-brain node graph (mockup `.brainwrap` / `.brainstage`)

struct RedesignBrainNode: Identifiable {
  let id = UUID()
  let text: String
  let x: CGFloat  // 0...1
  let y: CGFloat  // 0...1
  var core: Bool = false
}

/// A lightweight second-brain node graph on warm paper, matching the mockup's
/// dim/core node pills connected by hairlines to the `omi` core.
struct RedesignBrainGraph: View {
  let nodes: [RedesignBrainNode]
  /// Index pairs to draw a hairline between (into `nodes`).
  var links: [(Int, Int)] = []
  var background: Color = Ink.soft

  var body: some View {
    GeometryReader { geo in
      let w = geo.size.width
      let h = geo.size.height
      ZStack {
        // Hairlines
        Path { path in
          for (a, b) in links {
            guard nodes.indices.contains(a), nodes.indices.contains(b) else { continue }
            path.move(to: CGPoint(x: nodes[a].x * w, y: nodes[a].y * h))
            path.addLine(to: CGPoint(x: nodes[b].x * w, y: nodes[b].y * h))
          }
        }
        .stroke(Ink.hair2, lineWidth: 1)

        // Nodes
        ForEach(nodes) { node in
          nodePill(node)
            .position(x: node.x * w, y: node.y * h)
        }
      }
    }
    .background(background)
  }

  @ViewBuilder
  private func nodePill(_ node: RedesignBrainNode) -> some View {
    Text(node.text)
      .font(InkFont.sans(node.core ? 15 : 12.5, node.core ? .semibold : .medium))
      .foregroundColor(node.core ? Ink.accentInk : Ink.muted)
      .padding(.horizontal, node.core ? 18 : 12)
      .padding(.vertical, node.core ? 10 : 7)
      .background(
        Capsule(style: .continuous)
          .fill(node.core ? Ink.accent : Ink.surface)
          .overlay(
            node.core
              ? nil
              : Capsule(style: .continuous).strokeBorder(Ink.hair, lineWidth: 1))
          .shadow(color: Ink.shadow, radius: node.core ? 8 : 3, y: 2)
      )
      .fixedSize()
  }

}

// MARK: - Benefit-led permission card (mockup `.perm`)

struct RedesignPermissionCard: View {
  let icon: String
  let name: String
  let payoff: String
  let granted: Bool
  var isBusy: Bool = false
  var grantTitle: String = "Grant"
  var onGrant: () -> Void

  var body: some View {
    HStack(spacing: 16) {
      ZStack {
        RoundedRectangle(cornerRadius: 11, style: .continuous)
          .fill(granted ? Ink.live.opacity(0.14) : Ink.surface2)
          .frame(width: 44, height: 44)
        Image(systemName: granted ? "checkmark" : icon)
          .font(.system(size: 18, weight: .semibold))
          .foregroundColor(granted ? Ink.live : Ink.ink)
      }

      VStack(alignment: .leading, spacing: 3) {
        Text(name).inkH3()
        Text(payoff).font(InkFont.sans(13)).foregroundColor(Ink.muted)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer(minLength: 12)

      if granted {
        InkBadge(text: "Granted", kind: .sent)
      } else {
        InkButton(title: isBusy ? "Waiting…" : grantTitle, kind: .primary, size: .sm) {
          onGrant()
        }
      }
    }
    .padding(.horizontal, 20)
    .padding(.vertical, 18)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Ink.surface)
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .strokeBorder(Ink.hair, lineWidth: 1))
    )
  }
}
