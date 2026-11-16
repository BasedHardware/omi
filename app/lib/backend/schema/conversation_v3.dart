/// Fields a v3 server adds to a conversation (recordings and conversations design).
///
/// All are optional on the wire: older servers and one-to-one conversations (calls,
/// desktop, imports) omit them, and [ConversationV3Fields.fromJson] then returns null.
library;

/// Where a conversation is in the pipeline; drives the Home tile.
enum ConversationTileState {
  /// The conversation is still going: breathing dot.
  live,

  /// It ended and its transcript is still arriving: spinner.
  transcribing,

  /// Its summary is being written: pen.
  writing,

  /// Finished: the subject's emoji.
  done;

  static ConversationTileState? parse(Object? value) => switch (value) {
        'live' => ConversationTileState.live,
        'transcribing' => ConversationTileState.transcribing,
        'writing' => ConversationTileState.writing,
        'done' => ConversationTileState.done,
        _ => null,
      };
}

/// One piece of a conversation's audio: a span of one recording's audio file.
class RecordingPiece {
  const RecordingPiece({required this.recordingId, required this.audioFileId, required this.start, required this.end});

  final String recordingId;
  final String audioFileId;

  /// Seconds on that audio file's clock.
  final double start;
  final double end;

  static RecordingPiece? fromJson(Object? json) {
    if (json is! Map) return null;
    final recordingId = json['recording_id'];
    final audioFileId = json['audio_file_id'];
    final start = json['start'];
    final end = json['end'];
    if (recordingId is! String || audioFileId is! String || start is! num || end is! num || end < start) return null;
    return RecordingPiece(
        recordingId: recordingId, audioFileId: audioFileId, start: start.toDouble(), end: end.toDouble());
  }

  Map<String, dynamic> toJson() =>
      {'recording_id': recordingId, 'audio_file_id': audioFileId, 'start': start, 'end': end};
}

class ConversationV3Fields {
  const ConversationV3Fields({
    this.kind,
    this.homeHidden = false,
    this.tileState,
    this.titleLocked = false,
    this.recordingPieces = const [],
    this.summaryCoversThrough,
  });

  /// `conversation`, `voice_work`, `media` or `background`.
  final String? kind;
  final bool homeHidden;
  final ConversationTileState? tileState;

  /// The title will not change; the app never rewrites it locally either.
  final bool titleLocked;
  final List<RecordingPiece> recordingPieces;

  /// Last speech the stored summary covers; null when no summary is stored.
  final DateTime? summaryCoversThrough;

  static const _keys = [
    'kind',
    'home_hidden',
    'tile_state',
    'title_locked',
    'recording_pieces',
    'summary_covers_through'
  ];

  /// Null when the JSON carries none of the v3 fields.
  static ConversationV3Fields? fromJson(Map<String, dynamic> json) {
    if (!_keys.any(json.containsKey)) return null;
    final pieces = json['recording_pieces'];
    final covers = json['summary_covers_through'];
    return ConversationV3Fields(
      kind: json['kind'] is String ? json['kind'] as String : null,
      homeHidden: json['home_hidden'] == true,
      tileState: ConversationTileState.parse(json['tile_state']),
      titleLocked: json['title_locked'] == true,
      recordingPieces:
          pieces is List ? pieces.map(RecordingPiece.fromJson).whereType<RecordingPiece>().toList() : const [],
      summaryCoversThrough: covers is String ? DateTime.tryParse(covers) : null,
    );
  }

  Map<String, dynamic> toJson() => {
        if (kind != null) 'kind': kind,
        'home_hidden': homeHidden,
        if (tileState != null) 'tile_state': tileState!.name,
        'title_locked': titleLocked,
        'recording_pieces': recordingPieces.map((p) => p.toJson()).toList(),
        if (summaryCoversThrough != null) 'summary_covers_through': summaryCoversThrough!.toUtc().toIso8601String(),
      };
}
