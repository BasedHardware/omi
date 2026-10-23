import 'package:omi/backend/schema/gen/episodes_wire.g.dart' as wire;

/// One stretch of speech inside an episode's conversation, with Omi's short heading for it.
class EpisodeMoment {
  const EpisodeMoment({
    required this.id,
    required this.conversationId,
    required this.startedAt,
    required this.endedAt,
    this.startOffset = 0,
    this.endOffset = 0,
    this.heading = '',
  });

  final String id;
  final String conversationId;
  final DateTime startedAt;
  final DateTime endedAt;

  /// Seconds into [conversationId]'s transcript.
  final double startOffset;
  final double endOffset;
  final String heading;

  Duration get duration {
    final span = endedAt.difference(startedAt);
    return span.isNegative ? Duration.zero : span;
  }

  factory EpisodeMoment.fromGenerated(wire.GeneratedEpisodeMoment m) => EpisodeMoment(
        id: m.id,
        conversationId: m.conversationId,
        startedAt: m.startedAt.toLocal(),
        endedAt: m.endedAt.toLocal(),
        startOffset: m.startOffset,
        endOffset: m.endOffset,
        heading: m.heading,
      );
}

enum EpisodeItemStatus { provisional, kept, dropped, dismissed }

/// A task or reminder Omi heard while the episode was live. Provisional: it is not in Tasks until
/// the conversation's own processing saves it ([EpisodeItemStatus.kept]).
class EpisodeItem {
  const EpisodeItem({
    required this.id,
    required this.text,
    required this.createdAt,
    this.isReminder = false,
    this.status = EpisodeItemStatus.provisional,
    this.explicit = false,
    this.dueAt,
    this.conversationId,
    this.segmentOffset,
    this.actionItemId,
  });

  final String id;
  final String text;
  final DateTime createdAt;
  final bool isReminder;
  final EpisodeItemStatus status;
  final bool explicit;
  final DateTime? dueAt;
  final String? conversationId;
  final double? segmentOffset;
  final String? actionItemId;

  bool get visible => status == EpisodeItemStatus.provisional || status == EpisodeItemStatus.kept;

  EpisodeItem withStatus(EpisodeItemStatus next) => EpisodeItem(
        id: id,
        text: text,
        createdAt: createdAt,
        isReminder: isReminder,
        status: next,
        explicit: explicit,
        dueAt: dueAt,
        conversationId: conversationId,
        segmentOffset: segmentOffset,
        actionItemId: actionItemId,
      );

  factory EpisodeItem.fromGenerated(wire.GeneratedEpisodeProvisionalItem i) => EpisodeItem(
        id: i.id,
        text: i.text,
        createdAt: i.createdAt.toLocal(),
        isReminder: i.kind == 'reminder',
        status: EpisodeItemStatus.values.firstWhere((s) => s.name == i.status, orElse: () => EpisodeItemStatus.dropped),
        explicit: i.explicit,
        dueAt: i.dueAt?.toLocal(),
        conversationId: i.conversationId,
        segmentOffset: i.segmentOffset,
        actionItemId: i.actionItemId,
      );
}

/// An occasion of the day (a meeting, a dinner, a work session) over the conversations that make
/// it up. The server's overlay: no conversation is changed by it.
class Episode {
  const Episode({
    required this.id,
    required this.live,
    required this.startedAt,
    required this.lastActivityAt,
    this.closedAt,
    this.closeReason,
    this.title = '',
    this.bullets = const [],
    this.people = const [],
    this.items = const [],
    this.moments = const [],
    this.conversationIds = const [],
    this.sources = const [],
    this.stateUpdatedAt,
  });

  final String id;
  final bool live;
  final DateTime startedAt;
  final DateTime lastActivityAt;
  final DateTime? closedAt;
  final String? closeReason;
  final String title;
  final List<String> bullets;
  final List<String> people;
  final List<EpisodeItem> items;
  final List<EpisodeMoment> moments;
  final List<String> conversationIds;
  final List<String> sources;
  final DateTime? stateUpdatedAt;

  List<EpisodeItem> get visibleItems => [
        for (final item in items)
          if (item.visible) item
      ];

  Episode copyWith({List<EpisodeItem>? items, bool? live}) => Episode(
        id: id,
        live: live ?? this.live,
        startedAt: startedAt,
        lastActivityAt: lastActivityAt,
        closedAt: closedAt,
        closeReason: closeReason,
        title: title,
        bullets: bullets,
        people: people,
        items: items ?? this.items,
        moments: moments,
        conversationIds: conversationIds,
        sources: sources,
        stateUpdatedAt: stateUpdatedAt,
      );

  factory Episode.fromGenerated(wire.GeneratedEpisode e) => Episode(
        id: e.id,
        live: e.status == 'live',
        startedAt: e.startedAt.toLocal(),
        lastActivityAt: e.lastActivityAt.toLocal(),
        closedAt: e.closedAt?.toLocal(),
        closeReason: e.closeReason,
        title: e.title,
        bullets: e.bullets ?? const [],
        people: e.people ?? const [],
        items: [for (final item in e.provisionalItems ?? const []) EpisodeItem.fromGenerated(item)],
        moments: [for (final moment in e.moments ?? const []) EpisodeMoment.fromGenerated(moment)],
        conversationIds: e.conversationIds ?? const [],
        sources: e.sources ?? const [],
        stateUpdatedAt: e.stateUpdatedAt?.toLocal(),
      );
}

/// A read of the episodes API: whether this server serves episodes at all, and the episode.
class EpisodeRead {
  const EpisodeRead({required this.enabled, this.episode});

  /// The server capability. False (or a 404 from an older server) keeps today's UI.
  final bool enabled;
  final Episode? episode;

  static const disabled = EpisodeRead(enabled: false);
}
