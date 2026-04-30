/// Result captured from a widget turn. Each step produces one of these and
/// hands it to [OnboardingChatProvider.reportWidgetCapture].
sealed class WidgetResult {
  const WidgetResult();
}

class TextResult extends WidgetResult {
  final String value;
  const TextResult(this.value);
}

class ChipResult extends WidgetResult {
  final String id;
  final String label;
  const ChipResult({required this.id, required this.label});
}

class PermissionResult extends WidgetResult {
  final bool granted;
  final bool skipped;
  const PermissionResult({required this.granted, required this.skipped});
}

class AcknowledgeResult extends WidgetResult {
  const AcknowledgeResult();
}

class SkipResult extends WidgetResult {
  const SkipResult();
}

class SpeechProfileResult extends WidgetResult {
  final bool captured;
  final int frameCount;
  const SpeechProfileResult({required this.captured, required this.frameCount});
}
