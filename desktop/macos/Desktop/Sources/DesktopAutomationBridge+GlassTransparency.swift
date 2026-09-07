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
      summary: "Set the glass transparency through the slider's own published value (0…1)",
      params: ["value"]
    ) { params in
      // The model would normalise anything, but a harness that asks for 7 or "nan" has a bug, and
      // a boundary that quietly writes 1 instead hides it. The message states the whole contract.
      guard let value = params["value"].flatMap(Double.init), value.isFinite,
        InkGlassTransparencySettings.range.contains(CGFloat(value))
      else {
        throw DesktopAutomationActionError.invalidParams("value must be a number in 0...1")
      }
      return await MainActor.run {
        InkGlassTransparencySettings.shared.transparency = CGFloat(value)
        return Self.glassTransparencySnapshot()
      }
    }

    register(
      name: "reset_glass_transparency",
      summary: "Return the glass transparency to the shipped default, as the card's Reset button does"
    ) { _ in
      await MainActor.run {
        InkGlassTransparencySettings.shared.resetToDefault()
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
