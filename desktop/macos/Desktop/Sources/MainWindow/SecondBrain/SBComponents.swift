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

  private static let image = OmiBrandMarkAsset.templateImage()

  var body: some View {
    Group {
      if let nsImage = Self.image {
        Image(nsImage: nsImage)
          .resizable()
          .renderingMode(.template)
          .scaledToFit()
      } else {
        // A missing bitmap must never turn Omi into a generic progress ring.
        // Keep the same eight-dot brand silhouette at every shared SBLogo call
        // site while the signed bundle's resource lookup is unavailable.
        OmiBrandMarkFallback(size: size, color: tint ?? sb.ink)
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

/// Resolves the packaged Omi mark without depending on a single bundle's
/// registration order. Named, signed app bundles load the SwiftPM resource
/// bundle beneath `Contents/Resources`, while tests and preview hosts can make
/// it available through one of the already-loaded bundles instead.
enum OmiBrandMarkAsset {
  private static let resourceBundleName = "Omi Computer_Omi Computer.bundle"

  static func templateImage(named resourceName: String = "herologo") -> NSImage? {
    templateImage(
      named: resourceName,
      in: Bundle.allBundles + Bundle.allFrameworks + [Bundle.main],
      resourceBundleRoots: knownResourceBundleRoots()
    )
  }

  static func templateImage(
    named resourceName: String = "herologo",
    in bundles: [Bundle],
    resourceBundleRoots: [URL]
  ) -> NSImage? {
    for bundle in bundles {
      guard let url = bundle.url(forResource: resourceName, withExtension: "png"),
        let image = NSImage(contentsOf: url)
      else { continue }
      image.isTemplate = true
      return image
    }

    for root in resourceBundleRoots {
      let url = root.appendingPathComponent("\(resourceName).png")
      guard let image = NSImage(contentsOf: url) else { continue }
      image.isTemplate = true
      return image
    }

    return nil
  }

  private static func knownResourceBundleRoots() -> [URL] {
    let mainBundleURL = Bundle.main.bundleURL
    return [
      // Signed app: Omi.app/Contents/Resources/<SwiftPM resources>.bundle
      mainBundleURL
        .appendingPathComponent("Contents/Resources")
        .appendingPathComponent(resourceBundleName),
      // Development app host: Omi.app/<SwiftPM resources>.bundle
      mainBundleURL.appendingPathComponent(resourceBundleName),
      // SwiftPM test host: .build/.../debug/<SwiftPM resources>.bundle
      mainBundleURL.deletingLastPathComponent().appendingPathComponent(resourceBundleName),
    ]
  }
}

/// Vector-equivalent recovery mark for the rare case where an external host
/// has not made the packaged PNG available yet. It intentionally mirrors the
/// eight-dot Omi logo rather than drawing a generic circle.
private struct OmiBrandMarkFallback: View {
  let size: CGFloat
  let color: Color

  var body: some View {
    ZStack {
      ForEach(0..<8, id: \.self) { index in
        Circle()
          .fill(color)
          .frame(width: size * 0.23, height: size * 0.23)
          .offset(y: -size * 0.31)
          .rotationEffect(.degrees(Double(index) * 45))
      }
    }
    .frame(width: size, height: size)
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
  var isDefaultAction = false
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
    .modifier(SBDefaultActionKeyboardShortcut(enabled: isDefaultAction))
  }
}

private struct SBDefaultActionKeyboardShortcut: ViewModifier {
  let enabled: Bool

  @ViewBuilder
  func body(content: Content) -> some View {
    if enabled {
      content.keyboardShortcut(.defaultAction)
    } else {
      content
    }
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
