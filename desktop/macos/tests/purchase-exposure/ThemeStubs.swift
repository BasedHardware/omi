import SwiftUI

// Styling-only shims let the real billing coordinator compile without building the app.
enum OmiSpacing {
  static let md: CGFloat = 8
  static let xl: CGFloat = 20
  static let lg: CGFloat = 16
  static let sm: CGFloat = 4
  static let xxl: CGFloat = 24
}
enum OmiType {
  static let heading: CGFloat = 16
  static let title: CGFloat = 24
}
enum Ink {
  static let primary = Color.primary
  static let rowFill = Color.clear
  static let surface = Color.clear
  static let secondary = Color.secondary
}
struct GlassSeparator: View { var body: some View { Divider() } }
struct OmiButtonStyle: ButtonStyle {
  enum Kind { case primary }
  enum Size { case compact }
  init(_ kind: Kind, size: Size) {}
  func makeBody(configuration: Configuration) -> some View { configuration.label }
}
extension View {
  func scaledFont(size: CGFloat, weight: Font.Weight) -> some View { font(.system(size: size, weight: weight)) }
}
final class AnalyticsManager {
  static let shared = AnalyticsManager()
  func purchaseEvent(_ event: PurchaseEvent, _ properties: [String: String]) {}
  func paywallOpened(source: String, currentPlan: String) {}
}

struct ShellModalScrim: View {
  let onTap: () -> Void
  var body: some View { Color.clear }
}
struct DismissButton: View {
  let action: () -> Void
  var body: some View { Button("Dismiss", action: action) }
}
struct InkButton: View {
  enum Kind { case primary, secondary }
  let title: String
  let action: () -> Void
  init(_ title: String, kind: Kind = .primary, action: @escaping () -> Void) {
    self.title = title
    self.action = action
  }
  var body: some View { Button(title, action: action) }
}
enum PopupInkStyle { case stepHeadline, prose }
extension View {
  func inkStyle(_ style: PopupInkStyle, color: Color) -> some View { foregroundColor(color) }
  func inkGlassPanel() -> some View { self }
}
enum OmiMotion { static func gated(_ animation: Animation) -> Animation { animation } }
final class FloatingBarUsageLimiter {
  static let shared = FloatingBarUsageLimiter()
  struct Quota { let allowed: Bool }
  var serverQuota: Quota? = nil
}
extension String { static let floatingBarCachedPlan = "test.plan" }
