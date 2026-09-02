//
//  DesktopAutomationFirstUsePopupActions.swift — drive the first-use popup without the cursor.
//
//  Each action posts the notification the popup itself observes, which runs the exact handler the
//  on-screen control runs: a bridge action is a second caller of production code, never a second
//  implementation of it. Registered from `DesktopAutomationActionRegistry.registerBuiltins()`.
//

import Foundation

extension DesktopAutomationActionRegistry {

  func registerFirstUsePopupActions() {
    register(
      name: "first_use_popup_show",
      summary: "Re-arm and raise the first-use popup onboarding shows (legacy shell only; non-prod)",
      examples: ["./scripts/omi-ctl action first_use_popup_show"]
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "first_use_popup_show is disabled on production bundles"]
      }
      // The same persisted arming onboarding's handoff performs, so the popup is raised from the
      // state a real first launch has rather than a bare notification.
      PostOnboardingPromptSuggestions.save([HomeSuggestionComposer.universalFirstQuestion])
      NotificationCenter.default.post(name: .showTryAskingPopup, object: nil)
      return ["armed": PostOnboardingPromptSuggestions.shouldArmPopup() ? "true" : "false"]
    }

    register(
      name: "first_use_popup_select",
      summary: "Select a case in the first-use popup (same handler as clicking its chip)",
      params: ["use_case"],
      examples: ["./scripts/omi-ctl action first_use_popup_select use_case=design"]
    ) { params in
      let id = (params["use_case"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard let useCase = FirstUseCase.named(id) else {
        return ["error": "unknown use_case '\(id)'; one of \(FirstUseCase.all.map(\.id).joined(separator: ", "))"]
      }
      NotificationCenter.default.post(
        name: .firstUsePopupSelect, object: nil, userInfo: ["id": useCase.id])
      return ["selected": useCase.id, "site": useCase.siteName, "question": useCase.question]
    }

    register(
      name: "first_use_popup_try",
      summary: "Press \"Try it now\" in the first-use popup (opens the site)",
      examples: ["./scripts/omi-ctl action first_use_popup_try"]
    ) { _ in
      NotificationCenter.default.post(name: .firstUsePopupTry, object: nil)
      return nil
    }
  }
}
