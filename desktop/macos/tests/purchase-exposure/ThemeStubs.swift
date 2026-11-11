import SwiftUI

// Styling-only shims let the real billing coordinator compile without building the app.
enum OmiSpacing {
  static let md: CGFloat = 8
  static let xl: CGFloat = 20
  static let lg: CGFloat = 16
}
enum OmiType { static let heading: CGFloat = 16 }
enum Ink {
  static let primary = Color.primary
  static let rowFill = Color.clear
  static let surface = Color.clear
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
}
