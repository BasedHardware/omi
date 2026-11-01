import 'package:omi/utils/analytics/registry/events.g.dart';

/// One event per visible step exit. Repeated TabController animation notifications
/// do not duplicate an exit; a return via Back starts a new timed visit.
class MobileOnboardingStepTelemetry {
  MobileOnboardingStepTelemetry({required this.emit, required this.platform, int Function()? elapsedMs})
      : elapsedMs = elapsedMs ?? (Stopwatch()..start()).elapsedMillisecondsGetter;
  final void Function(RegisteredEvent) emit;
  final OnboardingStepCompletedPlatform Function() platform;
  final int Function() elapsedMs;
  int index = 0;
  int _enteredAt = 0;
  bool skipped = false;
  OnboardingStepCompletedExitReason exitReason = OnboardingStepCompletedExitReason.answered;
  bool _exited = false;
  static const steps = [
    OnboardingStepCompletedStep.auth,
    OnboardingStepCompletedStep.aiConsent,
    OnboardingStepCompletedStep.name,
    OnboardingStepCompletedStep.primaryLanguage,
    OnboardingStepCompletedStep.acquisitionSource,
    OnboardingStepCompletedStep.permissions,
    OnboardingStepCompletedStep.speechProfile,
    OnboardingStepCompletedStep.knowledgeGraph,
    OnboardingStepCompletedStep.setup,
    OnboardingStepCompletedStep.firstCapture,
  ];
  void seed(int restoredIndex) {
    index = restoredIndex;
    _enteredAt = elapsedMs();
    skipped = false;
    exitReason = OnboardingStepCompletedExitReason.answered;
    _exited = false;
  }

  void enter(int next) {
    if (next == index) return;
    exit();
    index = next;
    _enteredAt = elapsedMs();
    skipped = false;
    exitReason = OnboardingStepCompletedExitReason.answered;
    _exited = false;
  }

  void exit() {
    if (_exited) return;
    _exited = true;
    emit(OnboardingStepCompleted(
        step: steps[index],
        index: index,
        elapsedMs: (elapsedMs() - _enteredAt).clamp(0, 1 << 31),
        skipped: skipped,
        platform: platform(),
        exitReason: skipped ? OnboardingStepCompletedExitReason.skipped : exitReason));
  }
}

extension on Stopwatch {
  int elapsedMillisecondsGetter() => elapsedMilliseconds;
}
