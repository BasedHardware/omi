import AppKit
import OmiTheme
import SwiftUI

// The SB components are shared chrome: the shell, the chat surfaces, sign-in and onboarding are all
// built out of them. On glass they render in `Ink` rather than the `SBInk` white-alpha scale — that
// scale is layered on a *white* base in dark mode, so every one of these components drew white ink on
// a light-pinned panel and disappeared. The `SBInk` parameters stay in the API (callers outside this
// file pass them) but are collapsed onto the two rungs glass carries; see `SBInk.glassRung`.

// MARK: - The ladder

extension SBInk {
  /// The two rungs glass carries. `Ink.tertiary` is illegal on a translucent panel (it measures
  /// under AA there — see `Ink.tertiary`), so the design's thirty-two-step white-alpha scale
  /// collapses onto exactly two: anything the design set at 0.70 or above is something the reader
  /// acts on, and everything fainter is something the reader reads.
  var glassRung: Color {
    switch self {
    case .w9, .w88, .w85, .w8, .w75, .w7: return Ink.primary
    default: return Ink.secondary
    }
  }
}

// MARK: - Logo

/// The 8-dot Omi mark, tinted to the current ink. Spins ONLY while Omi is
/// actively working (listening / thinking) — never decoratively.
struct SBLogo: View {
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
        OmiBrandMarkFallback(size: size, color: tint ?? Ink.primary)
      }
    }
    .foregroundStyle(tint ?? Ink.primary)
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
      InkReduceMotion.perform(SBMotion.logoSpin) { angle = 360 }
    } else {
      InkReduceMotion.perform(.easeOut(duration: InkMotion.settle)) { angle = 0 }
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
  let text: String
  var trailing: String? = nil
  var onTrailingTap: (() -> Void)? = nil

  var body: some View {
    HStack(alignment: .firstTextBaseline, spacing: 8) {
      Text(text.uppercased())
        .geistMono(size: 12, weight: .medium, tracking: 12 * 0.08)
        .foregroundStyle(Ink.secondary)
      if let trailing {
        Text(trailing)
          .geistMono(size: 12, tracking: 0)
          .foregroundStyle(Ink.secondary)
          .onTapGesture { onTrailingTap?() }
          .contentShape(Rectangle())
      }
      Spacer(minLength: 0)
    }
  }
}

// MARK: - Buttons

/// The primary action: `Ink.primary` fill, `Ink.surface` label — the label ladder inverted, which is
/// high-contrast in both appearances by construction and owes no second colour pair.
struct SBInkButton: View {
  let title: String
  /// Retained for source compatibility. The button's metrics are the design system's
  /// (`InkButtonStyle`), so a caller cannot make one action pill a different size from another.
  var size: CGFloat = 14
  var horizontalPadding: CGFloat = 18
  var verticalPadding: CGFloat = 9
  var isDefaultAction = false
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Text(title)
    }
    // A full stadium capsule, never a rounded rectangle, and press feedback is
    // opacity rather than scale. Both come from the one button style.
    .buttonStyle(InkButtonStyle(kind: .primary))
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
  let title: String
  /// See `SBInkButton.size` — the metrics belong to `InkButtonStyle`.
  var size: CGFloat = 14
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Text(title)
    }
    .buttonStyle(InkButtonStyle(kind: .secondary))
  }
}

// MARK: - Glass panel modifier

extension View {
  /// A card on the panel. Delegates to the shared content chrome so a card here and a card on a
  /// content page cannot disagree; `stroke` is retained for source compatibility and ignored,
  /// because a card's outline is `Ink.separator` and nothing else.
  func sbCard(radius: CGFloat = PageGlass.cardRadius, stroke: SBInk = .w09) -> some View {
    _ = stroke
    return glassCard(cornerRadius: radius)
  }
}

// MARK: - Toggle (the design's pill knob)

struct SBToggleSwitch: View {
  @Binding var isOn: Bool
  var width: CGFloat = 30
  var height: CGFloat = 17

  var body: some View {
    Button {
      InkReduceMotion.perform(SBMotion.toggle) { isOn.toggle() }
    } label: {
      ZStack(alignment: isOn ? .trailing : .leading) {
        Capsule(style: .continuous)
          .fill(isOn ? Ink.primary : Ink.rowFillHover)
          .overlay(Capsule(style: .continuous).strokeBorder(isOn ? .clear : Ink.hairline, lineWidth: 1))
          .frame(width: width, height: height)
        Circle()
          .fill(isOn ? Ink.surface : Ink.primary)
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
            .inkStyle(InkType.rowCopy, color: titleToken.glassRung)
          if let subtitle {
            Text(subtitle)
              .inkStyle(InkType.statusLabel, color: Ink.secondary)
          }
        }
        Spacer(minLength: 8)
        trailing()
      }
      .padding(.vertical, 12)
      .contentShape(Rectangle())
      .onTapGesture { onTap?() }

      Rectangle().fill(Ink.separator).frame(height: 1)
    }
  }
}

extension SBHairlineRow where Trailing == EmptyView {
  init(title: String, subtitle: String? = nil, titleToken: SBInk = .w9, onTap: (() -> Void)? = nil) {
    self.init(title: title, subtitle: subtitle, titleToken: titleToken, onTap: onTap) { EmptyView() }
  }
}
