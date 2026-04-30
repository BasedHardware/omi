/// A single turn in the onboarding chat. Mirrors the union type at
/// `desktop-v2/src/components/onboarding/chatFlow/types.ts`.
sealed class CompanionTurn {
  final String id;
  const CompanionTurn({required this.id});
}

class AssistantTextTurn extends CompanionTurn {
  final String text;
  final bool streaming;
  const AssistantTextTurn({required super.id, required this.text, this.streaming = false});
}

class UserTextTurn extends CompanionTurn {
  final String text;
  const UserTextTurn({required super.id, required this.text});
}

class WidgetTurn extends CompanionTurn {
  final String stepId;
  bool captured;
  String? capturedSummary;
  WidgetTurn({
    required super.id,
    required this.stepId,
    this.captured = false,
    this.capturedSummary,
  });
}
