/// Fields a v3 server adds to a conversation (recordings and conversations design).
///
/// All are optional on the wire: older servers and one-to-one conversations (calls,
/// desktop, imports) omit them, and [ConversationV3Fields.fromJson] then returns null.
library;

import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
import 'package:omi/backend/schema/structured.dart';

/// Where a conversation is in the pipeline; drives the Home tile.
enum ConversationTileState {
  /// The conversation is still going: breathing dot.
  live,

  /// It ended and its transcript is still arriving: spinner.
  transcribing,

  /// Its summary is being written: pen.
  writing,

  /// Finished: the subject's emoji.
  done,

  /// Transcription or the summary failed for good: a warning mark, so a failed conversation never
  /// reads as finished.
  failed;

  static ConversationTileState? parse(Object? value) => switch (value) {
        'live' => ConversationTileState.live,
        'transcribing' => ConversationTileState.transcribing,
        'writing' => ConversationTileState.writing,
        'done' => ConversationTileState.done,
        'failed' => ConversationTileState.failed,
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

  factory RecordingPiece.fromGenerated(wire.GeneratedRecordingPiece piece) => RecordingPiece(
      recordingId: piece.recordingId, audioFileId: piece.audioFileId, start: piece.start, end: piece.end);

  /// Null for a malformed piece (or one that ends before it starts): one bad piece never fails the row.
  static RecordingPiece? fromJson(Object? json) {
    if (json is! Map) return null;
    final wire.GeneratedRecordingPiece piece;
    try {
      piece = wire.GeneratedRecordingPiece.fromJson(Map<String, dynamic>.from(json));
    } catch (_) {
      return null;
    }
    return piece.end < piece.start ? null : RecordingPiece.fromGenerated(piece);
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
    this.recordingIds = const [],
    this.summaryCoversThrough,
    this.liveSummary,
    this.recording = false,
    this.captureDeviceId,
  });

  /// `conversation`, `voice_work`, `media` or `background`.
  final String? kind;
  final bool homeHidden;
  final ConversationTileState? tileState;

  /// The title will not change; the app never rewrites it locally either.
  final bool titleLocked;
  final List<RecordingPiece> recordingPieces;

  /// Source IDs carried by the authenticated live-window read and hydrated detail.
  final List<String> recordingIds;

  /// Last speech the stored summary covers; null when no summary is stored.
  final DateTime? summaryCoversThrough;

  /// The owner-scoped live preview from detail. It does not enter the cached or final summary.
  final ({Structured structured, DateTime coversThrough})? liveSummary;

  /// A pendant capture's storage document. The server never lists one, but the capture socket still
  /// delivers them by recording id for released builds; a v3 Home never shows one as a row.
  final bool recording;

  /// Reliability experiment `end_button_by_device`: the app install (`{platform}_{hash}`) behind the
  /// open conversation's latest speech, on the live read only. Null when the server does not send it.
  final String? captureDeviceId;

  static const _keys = [
    'kind',
    'home_hidden',
    'tile_state',
    'title_locked',
    'recording_pieces',
    'v3_recording_ids',
    'summary_covers_through',
    'live_summary',
    'recording',
  ];

  /// Null when the JSON carries none of the v3 fields.
  static ConversationV3Fields? fromJson(Map<String, dynamic> json) {
    if (!_keys.any(json.containsKey)) return null;
    final pieces = json['recording_pieces'];
    final recordingIds = json['v3_recording_ids'];
    final covers = json['summary_covers_through'];
    final captureDevice = json['v3_capture_device_id'];
    return ConversationV3Fields(
      kind: json['kind'] is String ? json['kind'] as String : null,
      homeHidden: json['home_hidden'] == true,
      tileState: ConversationTileState.parse(json['tile_state']),
      titleLocked: json['title_locked'] == true,
      recordingPieces:
          pieces is List ? pieces.map(RecordingPiece.fromJson).whereType<RecordingPiece>().toList() : const [],
      recordingIds: recordingIds is List
          ? recordingIds.whereType<String>().where((id) => id.isNotEmpty && !id.contains('/')).toList(growable: false)
          : const [],
      summaryCoversThrough: covers is String ? DateTime.tryParse(covers) : null,
      liveSummary: _readLiveSummary(json['live_summary']),
      recording: json['recording'] == true,
      captureDeviceId: captureDevice is String && captureDevice.isNotEmpty ? captureDevice : null,
    );
  }

  static ({Structured structured, DateTime coversThrough})? _readLiveSummary(Object? value) {
    if (value is! Map<String, dynamic>) return null;
    final structured = value['structured'];
    final timestamp = value['summary_covers_through'];
    if (structured is! Map<String, dynamic> || timestamp is! String) return null;
    final through = DateTime.tryParse(timestamp);
    if (through == null) return null;
    try {
      return (structured: Structured.fromJson(structured), coversThrough: through);
    } catch (_) {
      return null;
    }
  }

  Map<String, dynamic> toJson() => {
        if (kind != null) 'kind': kind,
        'home_hidden': homeHidden,
        if (tileState != null) 'tile_state': tileState!.name,
        'title_locked': titleLocked,
        'recording_pieces': recordingPieces.map((p) => p.toJson()).toList(),
        if (recordingIds.isNotEmpty) 'v3_recording_ids': recordingIds,
        if (summaryCoversThrough != null) 'summary_covers_through': summaryCoversThrough!.toUtc().toIso8601String(),
        if (recording) 'recording': true,
        if (captureDeviceId != null) 'v3_capture_device_id': captureDeviceId,
      };
}
