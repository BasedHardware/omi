import Foundation

/// Where the progress band stands: `current` of `total` steps this run will show.
struct SBOnboardingProgress: Equatable {
  let current: Int
  let total: Int
}

/// Back and the progress dots both read the steps a person actually sees, not `Step.allCases`.
///
/// `advance` skips permission steps that are already granted (`firstUnaskedStep`), so a raw-value
/// walk would put Back on a step the person never saw and draw a dot for every skipped step. The
/// model keeps `shownStepHistory` (every step shown before the current one, oldest first), Back pops
/// it, and the band counts it plus the steps still ahead that will not be skipped.
extension SBOnboardingModel {
  /// True when `advance` would jump over this step because its permission is already granted.
  /// Mirrors `firstUnaskedStep`: a pre-granted Files step still shows once to run the scan.
  func wouldSkip(_ candidate: Step) -> Bool {
    guard let key = permissionKey(for: candidate), isGranted(key) else { return false }
    if candidate == .files, !localFileProfileState.isTerminal { return false }
    return true
  }

  /// The steps before `target` that a run reaching it would have shown. Seeds the history when
  /// onboarding resumes mid-way, and stands in for it when nothing was recorded.
  func predictedShownSteps(before target: Step) -> [Step] {
    Step.allCases.filter { $0.rawValue < target.rawValue && !wouldSkip($0) }
  }

  /// The step Back returns to: the last one shown, never one that was skipped.
  var previousShownStep: Step? {
    shownStepHistory.last ?? predictedShownSteps(before: step).last
  }

  /// `current` is the number of steps already shown, so it moves by exactly one per answer and
  /// never jumps over a skipped permission. `total` adds the steps still ahead that will be shown.
  var progress: SBOnboardingProgress {
    let current = shownStepHistory.count
    let ahead = Step.allCases.filter { $0.rawValue > step.rawValue && !wouldSkip($0) }.count
    return SBOnboardingProgress(current: current, total: current + 1 + ahead)
  }

  /// Record that `step` was shown and the run is moving on to `target`.
  func recordShownStep(movingTo target: Step) {
    guard target != step else { return }
    shownStepHistory.append(step)
  }

  /// Pop the history and return the step Back lands on.
  func popShownStep() -> Step? {
    shownStepHistory.popLast() ?? predictedShownSteps(before: step).last
  }
}
