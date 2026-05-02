import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:hive/hive.dart';

import 'package:nooto_v2/companion/companion_signals.dart';
import 'package:nooto_v2/home/cards/morning_brief_card.dart';
import 'package:nooto_v2/home/cards/today_card.dart';
import 'package:nooto_v2/home/cards/welcome_card.dart';
import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/home_storage.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/services/chat_service.dart';

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
    required ChatService chatService,
  })  : _signals = signals,
        _actionItems = actionItems,
        _chatService = chatService {
    _actionItems.addListener(_onActionItemsChanged);
    _init();
  }

  final CompanionSignals _signals;
  final ActionItemsProvider _actionItems;
  final ChatService _chatService;
  final List<CompanionCard> _cards = [];
  bool _ready = false;
  bool _briefInFlight = false;
  bool _disposed = false;

  void _onActionItemsChanged() {
    _runGenerators();
    _persist();
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _actionItems.removeListener(_onActionItemsChanged);
    super.dispose();
  }

  List<CompanionCard> get cards => List.unmodifiable(_cards);
  bool get ready => _ready;

  Box<Map> get _cardsBox => Hive.box<Map>(HomeBoxes.cards);
  Box<Map> get _actionsBox => Hive.box<Map>(HomeBoxes.actions);
  Box<Map> get _briefBox => Hive.box<Map>(HomeBoxes.brief);

  Future<void> _init() async {
    try {
      _hydrateFromHive();
      _runGenerators();
      _persist();
      // Trigger the first action-items fetch from here so the widget tree
      // doesn't have to. Defer to next frame — the constructor runs during
      // the consumer's build, and ActionItemsProvider.fetchAll fires its
      // own notifyListeners synchronously, which would throw "setState
      // called during build" if we kicked off here.
      SchedulerBinding.instance.addPostFrameCallback((_) {
        unawaited(_actionItems.kickOffIfNeeded());
      });
      unawaited(_kickOffMorningBrief());
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
    final today = _todayLocalKey();
    for (final raw in _cardsBox.values.toList()) {
      try {
        final json = Map<String, dynamic>.from(raw);
        final card = _fromJson(json);
        if (card == null) continue;
        if (card.generatedAt.add(card.ttl).isBefore(now)) {
          _cardsBox.delete(card.id);
          continue;
        }
        // Brief cards carry a dateKey. We only ever want today's; yesterday's
        // brief stays cached in _briefBox under its own date but must not
        // leak into the visible stream past local midnight.
        if (card is MorningBriefCard && card.dateKey != today) {
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
    _replaceOrEmit(_cachedBriefCard());
    _replaceOrEmit(todayCardFor(_actionItems));
  }

  /// Synchronous read of today's brief from Hive. Network fetch lives in
  /// [_kickOffMorningBrief]; this just surfaces an already-cached entry so
  /// generator passes don't flicker the brief in/out.
  MorningBriefCard? _cachedBriefCard() {
    final raw = _briefBox.get(_todayLocalKey());
    if (raw == null) return null;
    try {
      return MorningBriefCard.fromJson(Map<String, dynamic>.from(raw));
    } catch (_) {
      return null;
    }
  }

  /// Cache contract: one network call per device per day. The cache hit at
  /// the top short-circuits every subsequent call same-day; the miss path
  /// writes to Hive immediately on success so even a fast second mount
  /// (e.g. screen rebuild during the in-flight fetch) sees the entry.
  /// Errors are NOT cached — including the backend's `agentic.py` fallback
  /// string, which we detect and discard so a failed fetch doesn't poison
  /// the next 24h of opens.
  Future<void> _kickOffMorningBrief() async {
    final dateKey = _todayLocalKey();
    if (_briefBox.get(dateKey) != null) return;
    if (_briefInFlight) return;
    _briefInFlight = true;
    try {
      final body = await _chatService.fetchBrief(prompt: _briefPrompt);
      if (_disposed) return;
      final trimmed = body.trim();
      if (trimmed.isEmpty) return;
      if (_looksLikeBackendError(trimmed)) {
        debugPrint('[CompanionStream] brief returned backend fallback, '
            'not caching: $trimmed');
        return;
      }
      final card = MorningBriefCard(
        dateKey: dateKey,
        greeting: _greetingFor(_signals.preferredName),
        body: trimmed,
        generatedAt: DateTime.now(),
      );
      await _briefBox.put(dateKey, card.toJson());
      if (_disposed) return;
      _replaceOrEmit(card);
      _persist();
      notifyListeners();
    } catch (e) {
      debugPrint('[CompanionStream] brief fetch failed: $e');
    } finally {
      _briefInFlight = false;
    }
  }

  /// Backend's agentic chat path returns this exact string on any LLM
  /// exception (see `backend/utils/retrieval/agentic.py:427`). It looks like
  /// a successful response from our wire-protocol POV, so we sniff it here.
  bool _looksLikeBackendError(String body) {
    final lower = body.toLowerCase();
    return lower.contains('encountered an error') &&
        lower.contains('try again');
  }

  static const String _briefPrompt =
      "Brief me in at most 60 words: the one most important thing from "
      "yesterday I should pick up today, and the single most important new "
      "focus. First-person chief-of-staff voice — direct, no greeting, no "
      "headers, no bullets, no preamble. If yesterday was empty, say so in "
      "one short sentence and name today's top priority.";

  String _greetingFor(String? name) {
    final hour = DateTime.now().hour;
    final salutation = hour < 11
        ? 'Good morning'
        : hour < 17
            ? 'Good afternoon'
            : hour < 22
                ? 'Good evening'
                : 'Hi';
    final n = (name ?? '').trim();
    return n.isEmpty ? '$salutation.' : '$salutation, $n.';
  }

  String _todayLocalKey() {
    final now = DateTime.now();
    final y = now.year.toString().padLeft(4, '0');
    final m = now.month.toString().padLeft(2, '0');
    final d = now.day.toString().padLeft(2, '0');
    return '$y-$m-$d';
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
      return MorningBriefCard.fromJson(json);
    case CardKind.commitmentCapture:
    case CardKind.focusBlock:
    case CardKind.relationshipNudge:
      // Day 30+ kinds — generators not yet implemented.
      return null;
  }
}
