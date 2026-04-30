import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';

import 'package:nooto_v2/companion/companion_signals.dart';
import 'package:nooto_v2/home/cards/today_card.dart';
import 'package:nooto_v2/home/cards/welcome_card.dart';
import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/home_storage.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';

/// Screen-scoped provider that owns the Home card stream.
///
/// Lifecycle: instantiated in `HomeScreen.build` via `ChangeNotifierProvider`,
/// disposed when the screen unmounts. Hive boxes are the durable source of
/// truth — provider just reads them on init and writes back on action.
///
/// Generators are registered in [_runGenerators]. Each new card type adds one
/// entry there + one fromJson registration in [_fromJson]; nothing else here
/// changes when the card vocabulary grows.
class CompanionStreamProvider extends ChangeNotifier {
  CompanionStreamProvider({
    required CompanionSignals signals,
    required ActionItemsProvider actionItems,
  })  : _signals = signals,
        _actionItems = actionItems {
    _actionItems.addListener(_onActionItemsChanged);
    _init();
  }

  final CompanionSignals _signals;
  final ActionItemsProvider _actionItems;
  final List<CompanionCard> _cards = [];
  bool _ready = false;

  void _onActionItemsChanged() {
    _runGenerators();
    _persist();
    notifyListeners();
  }

  @override
  void dispose() {
    _actionItems.removeListener(_onActionItemsChanged);
    super.dispose();
  }

  List<CompanionCard> get cards => List.unmodifiable(_cards);
  bool get ready => _ready;

  Box<Map> get _cardsBox => Hive.box<Map>(HomeBoxes.cards);
  Box<Map> get _actionsBox => Hive.box<Map>(HomeBoxes.actions);

  Future<void> _init() async {
    try {
      _hydrateFromHive();
      _runGenerators();
      _persist();
      // Trigger the first action-items fetch from here so the widget tree
      // doesn't have to. Fire-and-forget; the listener re-runs generators
      // when results arrive.
      unawaited(_actionItems.kickOffIfNeeded());
    } catch (e, st) {
      debugPrint('[CompanionStream] init failed: $e\n$st');
      // Fail-soft: empty stream, no crash. User sees only the welcome
      // card on next generator pass (which still runs on `refresh`).
    } finally {
      _ready = true;
      notifyListeners();
    }
  }

  void _hydrateFromHive() {
    _cards.clear();
    final now = DateTime.now();
    for (final raw in _cardsBox.values) {
      try {
        final json = Map<String, dynamic>.from(raw);
        final card = _fromJson(json);
        if (card == null) continue;
        if (card.generatedAt.add(card.ttl).isBefore(now)) {
          _cardsBox.delete(card.id);
          continue;
        }
        _cards.add(card);
      } catch (e) {
        debugPrint('[CompanionStream] skipped bad card: $e');
      }
    }
    _cards.sort((a, b) => b.priority.compareTo(a.priority));
  }

  /// Runs every registered generator and emits new cards into the stream.
  /// Idempotent — skips emit if a card with the same id already exists or is
  /// dismissed in `home.actions.v1`.
  void _runGenerators() {
    _maybeEmit(welcomeCardFor(_signals));
    _replaceOrEmit(todayCardFor(_actionItems));
  }

  /// Today card is regenerated each pass with fresh content, so unlike most
  /// cards we want the latest copy in the stream — drop any prior instance
  /// before emitting the new one. Dismiss/snooze suppression still applies.
  void _replaceOrEmit(CompanionCard? card) {
    if (card == null) return;
    if (_isDismissed(card.id)) return;
    if (_isSnoozed(card.id)) return;
    _cards.removeWhere((c) => c.id == card.id);
    _cards.add(card);
    _cards.sort((a, b) => b.priority.compareTo(a.priority));
  }

  void _maybeEmit(CompanionCard? card) {
    if (card == null) return;
    if (_cards.any((c) => c.id == card.id)) return;
    if (_isDismissed(card.id)) return;
    if (_isAccepted(card.id)) return;
    if (_isSnoozed(card.id)) return;
    _cards.add(card);
    _cards.sort((a, b) => b.priority.compareTo(a.priority));
  }

  bool _isDismissed(String cardId) {
    final raw = _actionsBox.get(_actionKey(cardId, CardAction.dismiss));
    return raw != null;
  }

  bool _isAccepted(String cardId) {
    final raw = _actionsBox.get(_actionKey(cardId, CardAction.accept));
    return raw != null;
  }

  bool _isSnoozed(String cardId) {
    final raw = _actionsBox.get(_actionKey(cardId, CardAction.snooze));
    if (raw == null) return false;
    final until = raw['until'] as int?;
    if (until == null) return false;
    return DateTime.now().millisecondsSinceEpoch < until;
  }

  /// Refreshes the stream — re-runs generators against current state. Called
  /// on Home foreground or when an action mutates state in a way that should
  /// trigger re-evaluation.
  Future<void> refresh() async {
    _hydrateFromHive();
    _runGenerators();
    _persist();
    notifyListeners();
  }

  /// Records an action and removes the card from the active stream. Dismissed
  /// cards stay suppressed via `_isDismissed`; snoozed cards re-emerge once
  /// `now > until`.
  Future<void> recordAction(
    CompanionCard card,
    CardAction action, {
    DateTime? snoozeUntil,
  }) async {
    await _actionsBox.put(
      _actionKey(card.id, action),
      {
        'id': card.id,
        'action': action.code,
        'ts': DateTime.now().millisecondsSinceEpoch,
        if (snoozeUntil != null) 'until': snoozeUntil.millisecondsSinceEpoch,
      },
    );
    final removesFromStream = action == CardAction.accept ||
        action == CardAction.dismiss ||
        action == CardAction.snooze;
    if (removesFromStream) {
      _cards.removeWhere((c) => c.id == card.id);
      await _cardsBox.delete(card.id);
      notifyListeners();
    }
  }

  void _persist() {
    for (final card in _cards) {
      _cardsBox.put(card.id, card.toJson());
    }
  }

  String _actionKey(String cardId, CardAction action) =>
      '$cardId::${action.code}';
}

/// Card-type registry: dispatches deserialization on the `kind` field. Adding
/// a new card type requires one line here.
CompanionCard? _fromJson(Map<String, dynamic> json) {
  final kindCode = json['kind'] as String?;
  if (kindCode == null) return null;
  final kind = CardKindCodec.fromCode(kindCode);
  switch (kind) {
    case CardKind.welcome:
      return WelcomeCard.fromJson(json);
    case CardKind.actionItem:
      return TodayCard.fromJson(json);
    case CardKind.brief:
    case CardKind.commitmentCapture:
    case CardKind.focusBlock:
    case CardKind.relationshipNudge:
      // Day 30+ kinds — generators not yet implemented.
      return null;
  }
}
