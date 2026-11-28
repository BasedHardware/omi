// What Home shows, as data. `buildHome` is a pure function of its inputs: no providers, no widgets,
// no clock reads. The page turns each `HomeRow` into one widget, so "what can appear on Home" is the
// list of row kinds below and nothing else.
//
// Rules (SCA-5226, David 2026-11-27):
//  - Home is v3 only. The live row is at most one row, first in Today, and Finishing… follows it.
//  - Within a day, rows are newest first by start time.
//  - Home holds what is capturing, in progress, done or locked. Anything that needs the reader (a
//    failed conversation, a recording waiting on this phone or one that could not be sent) is in
//    Activity instead, and the bell says so.
//  - Locked conversations and held audio share one row per day.
//  - Live, Finishing…, saved recordings and locked rows show only in the default (unfiltered) view.

import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/conversations/home_rows.dart' show HomeStep, homeStepOf, isFailedConversation;

/// How long an in-progress state may run before its row says it is taking longer than usual.
/// Server work has no client timeout; the row only stops claiming that all is well.
class HomeDeadlines {
  const HomeDeadlines._();

  /// A conversation transcribing or writing its summary.
  static const conversationStep = Duration(minutes: 15);

  /// A recording saved on this phone that the server accepted and is still processing.
  static const savedProcessing = Duration(minutes: 30);
}

/// The capture the live row stands for.
enum HomeLiveKind {
  /// A streaming capture (pendant or phone) the server already shows as a conversation.
  conversation,

  /// A streaming capture the server has no conversation for yet (or between two).
  capture,

  /// An Omi call.
  call,

  /// Transcribe Later: audio saved on the phone with no live transcript.
  transcribeLater,
}

@immutable
sealed class HomeRow {
  const HomeRow();

  /// Stable across rebuilds, for list keys.
  String get key;
}

/// The one live row: first in Today while anything is capturing.
final class HomeLiveRow extends HomeRow {
  const HomeLiveRow(this.kind, {this.conversation});

  final HomeLiveKind kind;

  /// The server's conversation in progress, for [HomeLiveKind.conversation].
  final ServerConversation? conversation;

  @override
  String get key => 'live';
}

/// The conversation the reader just ended, until the server's own row takes its place.
final class HomeFinishingRow extends HomeRow {
  const HomeFinishingRow(this.conversation);

  final ServerConversation conversation;

  @override
  String get key => 'finishing';
}

/// A server conversation in any state: ready, transcribing, writing, failed.
final class HomeConversationRow extends HomeRow {
  const HomeConversationRow(this.conversation, {required this.index});

  final ServerConversation conversation;

  /// Position in the server's list, for analytics.
  final int index;

  @override
  String get key => conversation.id;
}

/// A recording from this phone while it is being sent or the server is processing it. Waiting or
/// failed recordings are in Activity.
final class HomeSavedRow extends HomeRow {
  const HomeSavedRow(this.recording);

  final LocalRecording recording;

  @override
  String get key => 'saved_${recording.id}';
}

/// Everything over the plan's limit on one day: locked conversations and held audio together.
final class HomeLockedRow extends HomeRow {
  const HomeLockedRow({required this.day, this.conversations = const [], this.held = const [], this.more = 0});

  final DateTime day;
  final List<ServerConversation> conversations;
  final List<HeldAudioRecording> held;

  /// Held recordings the server counted but did not list.
  final int more;

  int get count => conversations.length + held.length + more;

  @override
  String get key => 'locked_${day.toIso8601String()}';
}

@immutable
class HomeDay {
  const HomeDay(this.date, this.rows);

  final DateTime date;
  final List<HomeRow> rows;
}

@immutable
class HomeModel {
  const HomeModel(this.days);

  final List<HomeDay> days;

  bool get isEmpty => days.isEmpty;

  /// Every row, in display order.
  Iterable<HomeRow> get rows => days.expand((d) => d.rows);
}

/// What [buildHome] reads. Callers resolve providers into these plain values.
@immutable
class HomeInputs {
  const HomeInputs({
    required this.now,
    required this.listed,
    this.defaultView = true,
    this.live,
    this.streaming = false,
    this.callActive = false,
    this.transcribeLater = false,
    this.listeningSuppressed = false,
    this.finishing,
    this.saved = const [],
    this.held = const [],
    this.heldMore = 0,
    this.hiddenIds = const {},
  });

  final DateTime now;

  /// The server's conversations, already narrowed by any search or filter, grouped or not.
  final Iterable<ServerConversation> listed;

  /// No search, folder, starred, date filter or selection: Home's own view.
  final bool defaultView;

  /// The server's conversation in progress (already excluding one the reader removed).
  final ServerConversation? live;
  final bool streaming;
  final bool callActive;
  final bool transcribeLater;

  /// Right after End, until speech or a new conversation brings the live row back.
  final bool listeningSuppressed;
  final ServerConversation? finishing;

  final List<LocalRecording> saved;
  final List<HeldAudioRecording> held;
  final int heldMore;

  /// Conversations being deleted (Undo pending) or otherwise hidden.
  final Set<String> hiddenIds;
}

DateTime homeDay(DateTime t) {
  final local = t.toLocal();
  return DateTime(local.year, local.month, local.day);
}

DateTime _startOf(ServerConversation c) => c.startedAt ?? c.createdAt;

/// Whether the server lists [c] on Home. A failed one is in Activity, with its Try Again.
bool listedOnHome(ServerConversation c) =>
    c.v3?.homeHidden != true && c.v3?.recording != true && !isFailedConversation(c);

/// Whether a recording on this phone is on Home: only while it is being sent or processed. One
/// waiting to be sent, or one that could not be, is in Activity.
bool savedOnHome(LocalRecording r) => r.isBusy;

/// Whether the server's conversation in progress can stand for the live row. A failed one (v3- or
/// legacy-shaped, [isFailedConversation]) cannot.
bool usableLiveConversation(ServerConversation? c) =>
    c != null && !c.discarded && !c.deleted && c.v3?.homeHidden != true && !isFailedConversation(c);

/// The live row's capture, or null when nothing is capturing (or End just hid it).
HomeLiveKind? homeLiveKind({
  required ServerConversation? live,
  required bool streaming,
  required bool callActive,
  required bool transcribeLater,
  required bool listeningSuppressed,
}) {
  if (usableLiveConversation(live)) return HomeLiveKind.conversation;
  if (callActive) return HomeLiveKind.call;
  if (transcribeLater) return HomeLiveKind.transcribeLater;
  if (streaming && !listeningSuppressed) return HomeLiveKind.capture;
  return null;
}

/// Where a conversation is in the pipeline, for its tile and status line. The v3 tile state wins;
/// a row without one (a server holdout or rollback serves legacy-shaped rows) falls back to the
/// server's Home step, so its progress still shows.
ConversationTileState? homeTileState(ServerConversation c) {
  final tile = c.v3?.tileState;
  if (tile != null) return tile;
  if (c.status == ConversationStatus.in_progress) return null;
  return switch (homeStepOf(c)) {
    HomeStep.transcribing => ConversationTileState.transcribing,
    HomeStep.writingNotes => ConversationTileState.writing,
    HomeStep.failed => ConversationTileState.failed,
    null => null,
  };
}

/// Whether a conversation step has run past [HomeDeadlines.conversationStep].
bool conversationStepOverdue(ServerConversation c, DateTime now) {
  final state = homeTileState(c);
  if (state != ConversationTileState.transcribing && state != ConversationTileState.writing) return false;
  final since = c.finishedAt ?? c.createdAt;
  return now.difference(since) > HomeDeadlines.conversationStep;
}

/// Whether a saved recording the server accepted has been processing past its deadline.
bool savedProcessingOverdue(LocalRecording r, DateTime now) =>
    r.state == LocalRecordingState.processing &&
    r.uploadedAt != null &&
    now.difference(r.uploadedAt!) > HomeDeadlines.savedProcessing;

HomeModel buildHome(HomeInputs i) {
  final today = homeDay(i.now);
  // (start, row) per day, sorted at the end.
  final byDay = <DateTime, List<(DateTime, HomeRow)>>{};
  void add(DateTime day, DateTime at, HomeRow row) => (byDay[day] ??= []).add((at, row));

  final liveId = i.defaultView && usableLiveConversation(i.live) ? i.live!.id : null;
  final lockedByDay = <DateTime, List<ServerConversation>>{};
  var index = 0;
  final seen = <String>{};
  for (final c in i.listed) {
    final at = index++;
    if (!seen.add(c.id) || c.id == liveId || i.hiddenIds.contains(c.id) || !listedOnHome(c)) continue;
    final day = homeDay(_startOf(c));
    if (i.defaultView && c.isLocked) {
      (lockedByDay[day] ??= []).add(c);
      continue;
    }
    add(day, _startOf(c), HomeConversationRow(c, index: at));
  }

  if (i.defaultView) {
    for (final r in i.saved.where(savedOnHome)) {
      add(homeDay(r.startedAt), r.startedAt, HomeSavedRow(r));
    }
    final heldByDay = <DateTime, List<HeldAudioRecording>>{};
    for (final h in i.held) {
      final started = DateTime.fromMillisecondsSinceEpoch(h.startedAt * 1000);
      (heldByDay[homeDay(started)] ??= []).add(h);
    }
    // Held recordings the server counted but did not list belong with the newest day that holds
    // any, or the newest locked day, or Today when nothing else is locked.
    final lockedDays = {...lockedByDay.keys, ...heldByDay.keys}.toList()..sort((a, b) => b.compareTo(a));
    final heldDays = heldByDay.keys.toList()..sort((a, b) => b.compareTo(a));
    final moreDay = i.heldMore <= 0
        ? null
        : heldDays.isNotEmpty
            ? heldDays.first
            : lockedDays.isNotEmpty
                ? lockedDays.first
                : today;
    for (final day in {...lockedDays, if (moreDay != null) moreDay}) {
      final conversations = lockedByDay[day] ?? const <ServerConversation>[];
      final held = heldByDay[day] ?? const <HeldAudioRecording>[];
      final starts = [
        for (final c in conversations) _startOf(c),
        for (final h in held) DateTime.fromMillisecondsSinceEpoch(h.startedAt * 1000),
      ];
      // A row holding only unlisted recordings sits at the top of its day.
      final newest = starts.isEmpty ? i.now : starts.reduce((a, b) => a.isAfter(b) ? a : b);
      add(day, newest,
          HomeLockedRow(day: day, conversations: conversations, held: held, more: day == moreDay ? i.heldMore : 0));
    }
  }

  final days = <HomeDay>[];
  final dates = byDay.keys.toList()..sort((a, b) => b.compareTo(a));
  for (final date in dates) {
    final entries = byDay[date]!..sort((a, b) => b.$1.compareTo(a.$1));
    days.add(HomeDay(date, [for (final e in entries) e.$2]));
  }

  if (i.defaultView) {
    final kind = homeLiveKind(
      live: i.live,
      streaming: i.streaming,
      callActive: i.callActive,
      transcribeLater: i.transcribeLater,
      listeningSuppressed: i.listeningSuppressed,
    );
    final top = <HomeRow>[
      if (kind != null) HomeLiveRow(kind, conversation: kind == HomeLiveKind.conversation ? i.live : null),
      if (i.finishing case final f?) HomeFinishingRow(f),
    ];
    if (top.isNotEmpty) {
      // The live row leads Today, even when the conversation started before midnight.
      if (days.isNotEmpty && days.first.date == today) {
        days[0] = HomeDay(today, [...top, ...days.first.rows]);
      } else {
        days.insert(0, HomeDay(today, top));
      }
    }
  }
  return HomeModel(days);
}
