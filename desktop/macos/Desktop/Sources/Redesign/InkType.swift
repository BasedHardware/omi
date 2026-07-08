import SwiftUI

/// Typography for the redesign, mapped from the mockup's type scale.
/// - Serif (New York) for display lines, stat numbers, and the `omi.` wordmark.
/// - Sans (SF Pro / system) for body text.
/// - Mono (SF Mono) for dates, counts, and code.
enum InkFont {
  static func serif(_ size: CGFloat, _ weight: Font.Weight = .medium) -> Font {
    .system(size: size, weight: weight, design: .serif)
  }
  static func sans(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
    .system(size: size, weight: weight)
  }
  static func mono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
    .system(size: size, weight: weight, design: .monospaced)
  }
}

extension View {
  /// Big serif hero line (empty states, onboarding headlines, share cards).
  func inkDisplay(_ size: CGFloat = 30) -> some View {
    self.font(InkFont.serif(size, .medium)).foregroundColor(Ink.ink).tracking(-0.4)
      .lineSpacing(1)
  }
  /// The `omi` wordmark.
  func inkWordmark(_ size: CGFloat = 20) -> some View {
    self.font(InkFont.serif(size, .medium)).foregroundColor(Ink.ink).tracking(-0.6)
  }
  func inkH1() -> some View {
    self.font(InkFont.sans(26, .semibold)).foregroundColor(Ink.ink).tracking(-0.5)
  }
  func inkH2() -> some View {
    self.font(InkFont.sans(19, .semibold)).foregroundColor(Ink.ink).tracking(-0.3)
  }
  func inkH3() -> some View {
    self.font(InkFont.sans(15, .semibold)).foregroundColor(Ink.ink)
  }
  func inkBody() -> some View {
    self.font(InkFont.sans(14)).foregroundColor(Ink.body)
  }
  func inkSmall() -> some View {
    self.font(InkFont.sans(13)).foregroundColor(Ink.muted)
  }
  func inkCaption() -> some View {
    self.font(InkFont.sans(12)).foregroundColor(Ink.faint)
  }
  /// Uppercase, tracked, faint label above a section.
  func inkEyebrow() -> some View {
    self.font(InkFont.sans(11, .semibold)).foregroundColor(Ink.faint)
      .tracking(1.4).textCase(.uppercase)
  }
  func inkMonoCaption() -> some View {
    self.font(InkFont.mono(12)).foregroundColor(Ink.faint)
  }
}

/// A serif "big number / tiny label" stat, e.g. `1,923 · Remembered`.
struct InkStat: View {
  let number: String
  let label: String
  var size: CGFloat = 40

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(number)
        .font(InkFont.serif(size, .medium))
        .foregroundColor(Ink.ink)
        .tracking(-0.4)
        .monospacedDigit()
      Text(label)
        .font(InkFont.sans(12))
        .foregroundColor(Ink.faint)
    }
  }
}
