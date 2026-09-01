import Foundation

/// The onboarding demo note: what the model is told while the scenario's push-to-talk beat is
/// active, so "when does this arrive?" is answerable before any screen frame has been captured,
/// OCR'd, or embedded (capture starts at this beat). Both the typed-chat kernel context and the
/// voice system instruction read `active`. Mirrors the bundled order page exactly; update both
/// together.
enum OnboardingDemoNote {
  @MainActor static var active: String?

  static func orderPage(_ context: OnboardingScenarioPageContext) -> String {
    """
    Onboarding demo in progress: the user is looking at a demo order-confirmation page Omi opened \
    in their browser (Norrland Goods, order #A2419, an Aurora desk lamp in brass, $148.00). \
    It arrives \(context.deliveryDateText), the return window closes \(context.returnDateText), \
    it ships from Portland, OR, and the sale ends \(context.saleEndDateText). \
    If the user asks when it arrives, when returns close, or anything else about this order, answer \
    directly and briefly from this note. Never say you cannot see the page or that no order was \
    mentioned.
    """
  }
}
