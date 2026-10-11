import Foundation

/// The one action under the screen-demo step.
///
/// Skip used to appear only after the doors page was opened, so a person who did not want the demo,
/// or whose demo never armed, had no way forward but Skip Setup. Skip is now always offered until Omi
/// has answered; then Continue replaces it.
enum SBOnboardingScreenDemoFooter: Equatable {
  case skip
  case `continue`
}

extension SBOnboardingModel {
  var screenDemoFooter: SBOnboardingScreenDemoFooter {
    screenDemoDone ? .continue : .skip
  }
}
