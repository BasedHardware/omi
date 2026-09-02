import Foundation

/// The onboarding demo note: what the model is told while the scenario's push-to-talk beat is
/// active, so "when does this arrive?" is answerable before any screen frame has been captured,
/// OCR'd, or embedded (capture starts at this beat). Both the typed-chat kernel context and the
/// voice system instruction read `active`. Mirrors the bundled order page exactly; update both
/// together.
///
/// The first-run guide uses the same slot for its one spoken step (`firstRunReminder`), so the
/// two never overlap: the talk beat clears its note before onboarding can end.
enum OnboardingDemoNote {
  @MainActor static var active: String?

  static func firstRunReminder(project: String) -> String {
    """
    First-run guidance in progress: the user is dictating something Omi should bring up the next \
    time they open "\(project)". Omi's first-run guide records that reminder itself. Acknowledge in \
    one short sentence what you will bring up and when; do not create a task, reminder, memory, or \
    calendar event, and do not ask a follow-up question.
    """
  }

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
