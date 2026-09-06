import Foundation
import OmiTheme

/// Glass transparency automation actions: read and set the user's glass transparency without
/// cursor input. `set_glass_transparency` writes the same published value the Settings → General
/// slider binds to, so driving it exercises the production path every mounted panel follows.
extension DesktopAutomationActionRegistry {
  func registerGlassTransparencyActions() {
    register(
      name: "glass_transparency_snapshot",
      summary: "Return the glass transparency (0 solid … 1 bare material), its default, and the effective ground alpha"
    ) { _ in
      await MainActor.run { Self.glassTransparencySnapshot() }
    }

    register(
      name: "set_glass_transparency",
      summary: "Set the glass transparency through the slider's own published value (0…1, clamped)",
      params: ["value"]
    ) { params in
      guard let value = params["value"].flatMap(Double.init) else {
        throw DesktopAutomationActionError.invalidParams("value must be a number in 0...1")
      }
      return await MainActor.run {
        InkGlassTransparencySettings.shared.transparency = CGFloat(value)
        return Self.glassTransparencySnapshot()
      }
    }
  }

  @MainActor
  private static func glassTransparencySnapshot() -> [String: String] {
    let settings = InkGlassTransparencySettings.shared
    let reduced = InkReduceTransparency.isEnabled
    return [
      "transparency": String(format: "%.4f", Double(settings.transparency)),
      "default_transparency": String(format: "%.4f", Double(InkGlass.defaultTransparency)),
      "is_default": settings.isDefault ? "true" : "false",
      "reduce_transparency": reduced ? "true" : "false",
      "ground_alpha": String(
        format: "%.4f",
        Double(InkGlass.groundAlpha(reduceTransparency: reduced, transparency: settings.transparency))),
    ]
  }
}
