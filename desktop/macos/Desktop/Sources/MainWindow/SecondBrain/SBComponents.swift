import AppKit
import OmiTheme
import SwiftUI

// MARK: - Logo

/// The 8-dot Omi mark, tinted to the current ink. Spins ONLY while Omi is
/// actively working (listening / thinking) — never decoratively.
struct SBLogo: View {
  @Environment(\.sbTheme) private var sb
  var size: CGFloat = 16
  var spinning: Bool = false
  /// Override the tint (defaults to solid ink). The notch passes white.
  var tint: Color? = nil
  /// Static opacity (design dims the idle notch logo).
  var opacity: Double = 1

  @State private var angle: Double = 0

  private static let image: NSImage? = {
    guard let url = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
      let data = try? Data(contentsOf: url)
    else { return nil }
    let img = NSImage(data: data)
    img?.isTemplate = true
    return img
  }()

  var body: some View {
    Group {
      if let nsImage = Self.image {
        Image(nsImage: nsImage)
          .resizable()
          .renderingMode(.template)
          .scaledToFit()
      } else {
        // Fallback: a simple ring of dots so the mark is never missing.
        Circle().strokeBorder(lineWidth: size * 0.12)
      }
    }
    .foregroundStyle(tint ?? sb.ink)
    .frame(width: size, height: size)
    .opacity(opacity)
    .rotationEffect(.degrees(angle))
    .onAppear { syncSpin() }
    .onChange(of: spinning) { _, _ in syncSpin() }
    .accessibilityHidden(true)
  }

  private func syncSpin() {
    if spinning {
      angle = 0
      withAnimation(SBMotion.logoSpin) { angle = 360 }
    } else {
      withAnimation(.easeOut(duration: 0.2)) { angle = 0 }
    }
  }
}

// MARK: - Section label (Geist Mono, letter-spaced, muted)

struct SBSectionLabel: View {
  @Environment(\.sbTheme) private var sb
  let text: String
  var trailing: String? = nil
  var onTrailingTap: (() -> Void)? = nil

  var body: some View {
    HStack(alignment: .firstTextBaseline, spacing: 8) {
      Text(text.uppercased())
        .geistMono(size: 12, weight: .medium, tracking: 12 * 0.08)
        .foregroundStyle(sb.ink(.w35))
      if let trailing {
        Text(trailing)
          .geistMono(size: 12, tracking: 0)
          .foregroundStyle(sb.ink(.w25))
          .onTapGesture { onTrailingTap?() }
          .contentShape(Rectangle())
      }
      Spacer(minLength: 0)
    }
  }
}

// MARK: - Buttons

/// The one accent in the whole design: an inverted-ink filled button.
struct SBInkButton: View {
  @Environment(\.sbTheme) private var sb
  let title: String
  var size: CGFloat = 14
  var horizontalPadding: CGFloat = 18
  var verticalPadding: CGFloat = 9
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Text(title)
        .geist(size: size, weight: .semibold)
        .foregroundStyle(sb.inkInverted)
        .padding(.horizontal, horizontalPadding)
        .padding(.vertical, verticalPadding)
        .background(
          RoundedRectangle(cornerRadius: 9, style: .continuous).fill(sb.ink)
        )
    }
    .buttonStyle(.plain)
  }
}

struct SBOutlineButton: View {
  @Environment(\.sbTheme) private var sb
  let title: String
  var size: CGFloat = 14
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Text(title)
        .geist(size: size, weight: .medium)
        .foregroundStyle(sb.ink(.w85))
        .padding(.horizontal, 16)
        .padding(.vertical, 9)
        .background(
          RoundedRectangle(cornerRadius: 9, style: .continuous)
            .stroke(sb.ink(.w18), lineWidth: 1)
        )
    }
    .buttonStyle(.plain)
  }
}

// MARK: - Glass panel modifier

private struct SBGlassPanelModifier: ViewModifier {
  @Environment(\.sbTheme) private var sb
  var radius: CGFloat = 14
  var strokeToken: SBInk = .w09

  func body(content: Content) -> some View {
    content
      .background(
        RoundedRectangle(cornerRadius: radius, style: .continuous)
          .fill(sb.ink(.w04))
      )
      .overlay(
        RoundedRectangle(cornerRadius: radius, style: .continuous)
          .stroke(sb.ink(strokeToken), lineWidth: 1)
      )
  }
}

extension View {
  func sbCard(radius: CGFloat = 14, stroke: SBInk = .w09) -> some View {
    modifier(SBGlassPanelModifier(radius: radius, strokeToken: stroke))
  }
}

// MARK: - Toggle (the design's pill knob)

struct SBToggleSwitch: View {
  @Environment(\.sbTheme) private var sb
  @Binding var isOn: Bool
  var width: CGFloat = 30
  var height: CGFloat = 17

  var body: some View {
    Button {
      withAnimation(SBMotion.toggle) { isOn.toggle() }
    } label: {
      ZStack(alignment: isOn ? .trailing : .leading) {
        RoundedRectangle(cornerRadius: height / 2, style: .continuous)
          .fill(isOn ? sb.ink : sb.ink(.w15))
          .frame(width: width, height: height)
        Circle()
          .fill(isOn ? sb.inkInverted : sb.ink(.w6))
          .frame(width: height - 3, height: height - 3)
          .padding(.horizontal, 1.5)
      }
    }
    .buttonStyle(.plain)
    .accessibilityAddTraits(isOn ? [.isSelected, .isButton] : .isButton)
  }
}

// MARK: - Hairline row

/// A single tappable row with a 1px hairline separator underneath — the design's
/// core list primitive (rows, not cards).
struct SBHairlineRow<Trailing: View>: View {
  @Environment(\.sbTheme) private var sb
  let title: String
  var subtitle: String? = nil
  var titleToken: SBInk = .w9
  var onTap: (() -> Void)? = nil
  @ViewBuilder var trailing: () -> Trailing

  var body: some View {
    VStack(spacing: 0) {
      HStack(spacing: 12) {
        VStack(alignment: .leading, spacing: 2) {
          Text(title)
            .geist(size: 15)
            .foregroundStyle(sb.ink(titleToken))
          if let subtitle {
            Text(subtitle)
              .geist(size: 12.5)
              .foregroundStyle(sb.ink(.w38))
          }
        }
        Spacer(minLength: 8)
        trailing()
      }
      .padding(.vertical, 12)
      .contentShape(Rectangle())
      .onTapGesture { onTap?() }

      Rectangle().fill(sb.ink(.w07)).frame(height: 1)
    }
  }
}

extension SBHairlineRow where Trailing == EmptyView {
  init(title: String, subtitle: String? = nil, titleToken: SBInk = .w9, onTap: (() -> Void)? = nil) {
    self.init(title: title, subtitle: subtitle, titleToken: titleToken, onTap: onTap) { EmptyView() }
  }
}
