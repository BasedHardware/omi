import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/format/omi_date_format.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';

/// The server's deterministic title budget in code points (`TITLE_MAX_CHARS` in
/// `backend/utils/conversations/deterministic_minimum.py`).
const int conversationFallbackTitleMaxChars = 60;

const _sentenceTerminators = {'.', '!', '?'};

/// Last-resort title for a legacy kept row the server left untitled. A port of the server's
/// `deterministic_minimum_title` transcript branch, pinned by
/// `contracts/parity/deterministic_title.json`: the non-blank segment texts joined with spaces,
/// whitespace collapsed, cut after the first `.`/`!`/`?`, then cut to 60 code points on a word
/// boundary (a hard cut for one unbroken token), with no ellipsis. Null when the payload carries no
/// transcript text; the server's time label depends on the user's zone and stays server-side.
String? transcriptFallbackTitle(ServerConversation conversation) {
  final joined = conversation.transcriptSegments.map((s) => s.text.trim()).where((t) => t.isNotEmpty).join(' ');
  final collapsed = joined.split(RegExp(r'\s+')).where((word) => word.isNotEmpty).join(' ');
  if (collapsed.isEmpty) return null;
  final runes = collapsed.runes.toList();
  var end = runes.length;
  for (var i = 0; i < runes.length; i++) {
    if (_sentenceTerminators.contains(String.fromCharCode(runes[i]))) {
      end = i + 1;
      break;
    }
  }
  final sentence = runes.sublist(0, end);
  if (sentence.length <= conversationFallbackTitleMaxChars) return String.fromCharCodes(sentence);
  final head = sentence.sublist(0, conversationFallbackTitleMaxChars);
  final boundary = head.lastIndexOf(' '.codeUnitAt(0));
  if (boundary <= 0) return String.fromCharCodes(head);
  return String.fromCharCodes(head.sublist(0, boundary)).trimRight();
}

/// The display title of a kept (not discarded) conversation: its title, else transcript text,
/// else a localized recording date/time. The last case reports [ConversationUntitledRendered]
/// so missing server titles remain observable. [title] overrides the raw structured title
/// when a surface already normalized it.
String conversationDisplayTitle(
  ServerConversation conversation,
  AppLocalizations l10n, {
  required ConversationUntitledRenderedSurface surface,
  String? title,
  OmiDateFormat? dates,
}) {
  final trimmed = (title ?? conversation.structured.title).trim();
  if (trimmed.isNotEmpty) return trimmed;
  final fallback = transcriptFallbackTitle(conversation);
  if (fallback != null) return fallback;
  UntitledConversationTelemetry.report(conversation, surface);
  return recordingFallbackTitle(conversation, l10n, dates: dates);
}

/// A presentation-only label; never save this placeholder as a user title.
String recordingFallbackTitle(ServerConversation conversation, AppLocalizations l10n, {OmiDateFormat? dates}) {
  final formatter = dates ?? OmiDateFormat(locale: Locale(l10n.localeName), use24HourFormat: false, l10n: l10n);
  return formatter.dateTime((conversation.startedAt ?? conversation.createdAt).toLocal());
}

/// Reports each missing-title/no-transcript fallback at most once per conversation, surface and
/// app session. Only bounded properties leave the device: surface, an age bucket and whether a
/// retry was offered — never the id, title or transcript.
class UntitledConversationTelemetry {
  UntitledConversationTelemetry._();

  /// Session budget: once this many distinct rows have reported, the session stops reporting.
  /// Nothing is evicted, so a revisited row can never report twice.
  @visibleForTesting
  static const int maxReportsPerSession = 512;
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
    if (_reported.length >= maxReportsPerSession) return;
    if (!_reported.add('${surface.wireName}:${conversation.id}')) return;
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
