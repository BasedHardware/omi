import 'package:flutter/widgets.dart';

/// A card in the Companion Stream.
///
/// `abstract base` (not `sealed`) so subclasses can live in their own files
/// under `lib/home/cards/` per the architectural test, while preventing
/// outside-library implementations.
///
/// New card types satisfy the architectural test (design doc §"Recommended
/// Approach") by:
///   1. Adding a `CardKind` enum value.
///   2. Adding a subclass in `lib/home/cards/`.
///   3. Registering a `fromJson` factory in the provider's `_fromJson` switch.
///   4. Registering a generator in `CompanionStreamProvider._runGenerators`.
/// No edits to `home_screen.dart`. No edits to this file beyond the enum.
abstract base class CompanionCard {
  /// Stable identifier used for dedup and action-recording. Generators must
  /// produce the same id for the same logical card across sessions.
  String get id;

  CardKind get kind;

  /// Higher = floats up in the stream.
  int get priority;

  DateTime get generatedAt;

  /// When this card becomes stale and is hidden by TTL enforcement.
  Duration get ttl;

  /// For local persistence in `home.cards.v1`. The `kind` field MUST be
  /// included so `companionCardFromJson` can dispatch on it.
  Map<String, dynamic> toJson();

  Widget render(BuildContext context);

  /// Called when the user taps an action affordance on the card. Provider
  /// records the action in `home.actions.v1` and re-evaluates the stream.
  void onAction(BuildContext context, CardAction action);
}

enum CardKind {
  welcome,
  brief,
  actionItem,
  // Day 30+ kinds, declared here so the enum stays exhaustive even before
  // the generators ship. Subclasses land alongside the generator.
  commitmentCapture,
  focusBlock,
  relationshipNudge,
}

extension CardKindCodec on CardKind {
  String get code => name;

  static CardKind fromCode(String code) {
    return CardKind.values.firstWhere(
      (k) => k.name == code,
      orElse: () => throw ArgumentError('unknown CardKind: $code'),
    );
  }
}

enum CardAction {
  accept,
  snooze,
  dismiss,
  tapThrough,
  open,
}

extension CardActionCodec on CardAction {
  String get code => name;
}
