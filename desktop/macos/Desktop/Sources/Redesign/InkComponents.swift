import SwiftUI

// MARK: - Buttons

enum InkButtonKind {
  case primary  // ink fill, canvas text — the main action
  case plain  // surface + hairline
  case ghost  // transparent
  case accent  // same as primary in a monochrome system
}

enum InkButtonSize {
  case sm, md, lg
  var height: CGFloat { self == .sm ? 30 : (self == .lg ? 46 : 38) }
  var hPad: CGFloat { self == .sm ? 14 : (self == .lg ? 24 : 18) }
  var font: CGFloat { self == .sm ? 13 : (self == .lg ? 15 : 14) }
}

/// A pill-soft button matching the mockup's `.btn` family.
struct InkButton: View {
  let title: String
  var systemImage: String? = nil
  var kind: InkButtonKind = .plain
  var size: InkButtonSize = .md
  var fullWidth: Bool = false
  let action: () -> Void

  @State private var hovering = false

  private var isFilled: Bool { kind == .primary || kind == .accent }

  private var bg: Color {
    switch kind {
    case .primary, .accent: return hovering ? Ink.accentStrong : Ink.ink
    case .plain: return hovering ? Ink.surface2 : Ink.surface
    case .ghost: return hovering ? Ink.surface2 : .clear
    }
  }
  private var fg: Color { isFilled ? Ink.accentInk : Ink.ink }
  private var border: Color { kind == .plain ? Ink.hair2 : .clear }

  var body: some View {
    Button(action: action) {
      HStack(spacing: 8) {
        if let systemImage { Image(systemName: systemImage).font(.system(size: size.font, weight: .semibold)) }
        Text(title)
      }
      .font(InkFont.sans(size.font, isFilled ? .semibold : .medium))
      .foregroundColor(fg)
      .frame(maxWidth: fullWidth ? .infinity : nil)
      .frame(height: size.height)
      .padding(.horizontal, size.hPad)
      .background(
        Capsule(style: .continuous).fill(bg)
          .overlay(Capsule(style: .continuous).strokeBorder(border, lineWidth: 1))
      )
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .onHover { hovering = $0 }
  }
}

// MARK: - Cards

/// Hairline card on a white surface — the default container.
struct InkCard<Content: View>: View {
  var padding: CGFloat = InkSpace.s5
  var recessed: Bool = false
  var radius: CGFloat = InkRadius.card
  @ViewBuilder var content: () -> Content

  var body: some View {
    content()
      .padding(padding)
      .background(
        RoundedRectangle(cornerRadius: radius, style: .continuous)
          .fill(recessed ? Ink.surface2 : Ink.surface)
          .overlay(
            RoundedRectangle(cornerRadius: radius, style: .continuous)
              .strokeBorder(Ink.hair, lineWidth: 1)
          )
      )
  }
}

/// The hero "do this next" card, with a scarce warm radial tint at the top-right.
struct NextCard<Content: View>: View {
  @ViewBuilder var content: () -> Content

  var body: some View {
    content()
      .padding(EdgeInsets(top: 28, leading: 30, bottom: 28, trailing: 30))
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        RoundedRectangle(cornerRadius: InkRadius.next, style: .continuous)
          .fill(Ink.surface)
          .overlay(
            RoundedRectangle(cornerRadius: InkRadius.next, style: .continuous)
              .fill(
                RadialGradient(
                  colors: [Ink.accentTint, .clear],
                  center: .topTrailing, startRadius: 2, endRadius: 360)
              )
          )
          .overlay(
            RoundedRectangle(cornerRadius: InkRadius.next, style: .continuous)
              .strokeBorder(Ink.hair, lineWidth: 1)
          )
      )
  }
}

// MARK: - Badges

enum InkBadgeKind { case draft, needs, hold, sent }

struct InkBadge: View {
  let text: String
  var kind: InkBadgeKind = .hold

  private var fg: Color {
    switch kind {
    case .draft: return Ink.accentStrong
    case .needs: return Ink.warnText
    case .hold: return Ink.body
    case .sent: return Ink.sentText
    }
  }
  private var bg: Color {
    switch kind {
    case .draft: return Ink.accentTint
    case .needs: return Ink.warn.opacity(0.14)
    case .hold: return Ink.surface2
    case .sent: return Ink.live.opacity(0.13)
    }
  }
  private var dot: Color {
    switch kind {
    case .draft: return Ink.accent
    case .needs: return Ink.warn
    case .hold: return Ink.faint
    case .sent: return Ink.live
    }
  }

  var body: some View {
    HStack(spacing: 6) {
      Circle().fill(dot).frame(width: 6, height: 6)
      Text(text).font(InkFont.sans(11.5, .medium))
    }
    .foregroundColor(fg)
    .padding(.horizontal, 9)
    .frame(height: 22)
    .background(
      RoundedRectangle(cornerRadius: 7, style: .continuous)
        .fill(bg)
        .overlay(
          kind == .hold
            ? RoundedRectangle(cornerRadius: 7).strokeBorder(Ink.hair, lineWidth: 1) : nil)
    )
  }
}

/// A neutral pill / chip.
struct InkPill: View {
  let text: String
  var systemImage: String? = nil
  var body: some View {
    HStack(spacing: 6) {
      if let systemImage { Image(systemName: systemImage).font(.system(size: 11)) }
      Text(text).font(InkFont.sans(12, .medium))
    }
    .foregroundColor(Ink.body)
    .padding(.horizontal, 11)
    .frame(height: 26)
    .background(
      Capsule().fill(Ink.surface2).overlay(Capsule().strokeBorder(Ink.hair, lineWidth: 1)))
  }
}

/// Amber-free "Member #NNNN" outlined pill.
struct MemberBadge: View {
  let text: String
  var body: some View {
    HStack(spacing: 7) {
      Image(systemName: "star.fill").font(.system(size: 10))
      Text(text).font(InkFont.sans(12.5, .medium))
    }
    .foregroundColor(Ink.ink)
    .padding(.horizontal, 12)
    .frame(height: 30)
    .background(
      Capsule().fill(Ink.surface).overlay(Capsule().strokeBorder(Ink.hair2, lineWidth: 1)))
  }
}

// MARK: - Toggle

/// The mockup's pill switch — green when on.
struct InkToggle: View {
  @Binding var isOn: Bool
  var body: some View {
    ZStack(alignment: isOn ? .trailing : .leading) {
      Capsule().fill(isOn ? Ink.live : Ink.hair2).frame(width: 40, height: 24)
      Circle().fill(.white).frame(width: 18, height: 18).padding(3)
        .shadow(color: .black.opacity(0.25), radius: 1, y: 1)
    }
    .animation(.easeInOut(duration: 0.18), value: isOn)
    .onTapGesture { isOn.toggle() }
  }
}

// MARK: - Live dot & presence chips

/// A small pulsing status dot (green by default).
struct LiveDot: View {
  var color: Color = Ink.live
  var size: CGFloat = 7
  @State private var pulse = false
  var body: some View {
    Circle().fill(color).frame(width: size, height: size)
      .overlay(
        Circle().stroke(color.opacity(pulse ? 0 : 0.45), lineWidth: 2)
          .scaleEffect(pulse ? 2.4 : 1))
      .onAppear {
        withAnimation(.easeOut(duration: 2.6).repeatForever(autoreverses: false)) { pulse = true }
      }
  }
}

/// The titlebar "🖥 Capture · 🎤 Listening" presence chips.
struct PresenceChips: View {
  var capturing: Bool
  var listening: Bool
  var body: some View {
    HStack(spacing: 14) {
      chip(icon: "display", label: "Capture", live: capturing)
      chip(icon: "mic", label: "Listening", live: listening)
    }
  }
  private func chip(icon: String, label: String, live: Bool) -> some View {
    HStack(spacing: 5) {
      Image(systemName: icon).font(.system(size: 11)).foregroundColor(Ink.faint)
      if live { LiveDot(size: 6) } else {
        Circle().fill(Ink.faint.opacity(0.5)).frame(width: 6, height: 6)
      }
      Text(label).font(InkFont.sans(11.5, .medium)).foregroundColor(Ink.muted)
    }
  }
}

// MARK: - The omi buddy (8-dot rotating ring)

struct BuddyRing: View {
  var diameter: CGFloat = 60
  var dot: CGFloat = 8
  var color: Color = Ink.ink
  var spins: Bool = true

  @State private var angle: Double = 0

  var body: some View {
    ZStack {
      ForEach(0..<8, id: \.self) { i in
        Circle()
          .fill(color)
          .frame(width: dot, height: dot)
          .offset(y: -(diameter / 2 - dot / 2))
          .rotationEffect(.degrees(Double(i) * 45))
      }
    }
    .frame(width: diameter, height: diameter)
    .rotationEffect(.degrees(angle))
    .onAppear {
      guard spins else { return }
      withAnimation(.linear(duration: 22).repeatForever(autoreverses: false)) { angle = 360 }
    }
  }
}
