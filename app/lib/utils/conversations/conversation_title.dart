import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';

/// The server's deterministic title budget (`TITLE_MAX_CHARS` in
/// `backend/utils/conversations/deterministic_minimum.py`), so a client fallback reads like the
/// title the server writes today.
const int conversationFallbackTitleMaxChars = 60;

/// Last-resort title for a legacy kept row the server left untitled: the first non-blank
/// transcript segment, whitespace-collapsed and cut at a word boundary. Null when the payload
/// carries no transcript text. The server titles every row it keeps, so this only covers rows
/// written before that rule.
String? transcriptFallbackTitle(ServerConversation conversation) {
  for (final segment in conversation.transcriptSegments) {
    final text = segment.text.split(RegExp(r'\s+')).where((word) => word.isNotEmpty).join(' ');
    if (text.isEmpty) continue;
    if (text.length <= conversationFallbackTitleMaxChars) return text;
    final head = text.substring(0, conversationFallbackTitleMaxChars);
    final boundary = head.lastIndexOf(' ');
    return '${boundary > 0 ? head.substring(0, boundary) : head}…';
  }
  return null;
}

/// The display title of a kept (not discarded) conversation: its title, else transcript text,
/// else "Untitled Conversation" — and that last case reports [ConversationUntitledRendered] so
/// the fallback can be verified to reach zero. [title] overrides the raw structured title when a
/// surface already normalized it.
String conversationDisplayTitle(
  ServerConversation conversation,
  AppLocalizations l10n, {
  required ConversationUntitledRenderedSurface surface,
  String? title,
}) {
  final trimmed = (title ?? conversation.structured.title).trim();
  if (trimmed.isNotEmpty) return trimmed;
  final fallback = transcriptFallbackTitle(conversation);
  if (fallback != null) return fallback;
  UntitledConversationTelemetry.report(conversation, surface);
  return l10n.untitledConversation;
}

/// Reports each bare "Untitled Conversation" render at most once per conversation, surface and
/// app session. Only bounded properties leave the device: surface, an age bucket and whether a
/// retry was offered — never the id, title or transcript.
class UntitledConversationTelemetry {
  UntitledConversationTelemetry._();

  static const int _maxRemembered = 512;
  static final Set<String> _reported = <String>{};

  /// Test seam: replaces the typed-event sink.
  @visibleForTesting
  static void Function(ConversationUntitledRendered event)? sinkOverride;

  @visibleForTesting
  static void resetForTest() {
    _reported.clear();
    sinkOverride = null;
  }

  static void report(ServerConversation conversation, ConversationUntitledRenderedSurface surface, {DateTime? now}) {
    final key = '${surface.wireName}:${conversation.id}';
    if (!_reported.add(key)) return;
    if (_reported.length > _maxRemembered) _reported.remove(_reported.first);
    final event = ConversationUntitledRendered(
      surface: surface,
      ageBucket: ageBucketFor(conversation.createdAt, now ?? DateTime.now()),
      summaryRetryable: conversation.summaryRetryable,
    );
    final sink = sinkOverride;
    if (sink != null) {
      sink(event);
      return;
    }
    const TypedEvents().emit(event);
  }

  static ConversationUntitledRenderedAgeBucket ageBucketFor(DateTime createdAt, DateTime now) {
    final age = now.difference(createdAt);
    if (age < const Duration(hours: 1)) return ConversationUntitledRenderedAgeBucket.under1h;
    if (age < const Duration(days: 1)) return ConversationUntitledRenderedAgeBucket.under1d;
    if (age < const Duration(days: 7)) return ConversationUntitledRenderedAgeBucket.under7d;
    if (age < const Duration(days: 30)) return ConversationUntitledRenderedAgeBucket.under30d;
    return ConversationUntitledRenderedAgeBucket.over30d;
  }
}
