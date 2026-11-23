// Parses generation-pinned Listen receipts and the source coordinates of durable audio frames.
// The authenticated socket supplies the owner and recording context when journaling a receipt.
import 'dart:convert';

import 'message_event.dart';

class CustodyFrame {
  const CustodyFrame._({
    required this.captureRoot,
    required this.channel,
    required this.clockEpoch,
    required this.ordinal,
    required this.sha256,
  });

  final String captureRoot;
  final String channel;
  final int clockEpoch;
  final int ordinal;
  final String sha256;
}

/// Receipt issued by Listen after committing the original and its frame manifest.
class AudioCustodyEvent extends MessageEvent {
  AudioCustodyEvent._(this._wire, this.owner, this.frames, this.recordingSessionId, this.conversationId)
      : super(eventType: 'audio_custody');

  static final _sha256 = RegExp(r'^[0-9a-f]{64}$');
  static final _generation = RegExp(r'^[1-9][0-9]*$');
  static final _archiveRoot = RegExp(r'^[0-9a-f]{32}$');
  static final _sourceRoot = RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$');
  static const _maxFrames = 4096; // Listen's capture pack limit.

  // The persisted wire doubles as an input to the orphan-file census. An
  // unrecognized field may introduce a local file reference in a newer schema.
  static const _eventFields = {'type', 'recording_session_id', 'capture_root', 'channel', 'frames', 'receipt'};
  static const _frameFields = {
    'sequence',
    'byte_offset',
    'bytes',
    'start',
    'samples',
    'gap_before',
    'sha256',
    'source'
  };
  static const _sourceFields = {'capture_root', 'clock_epoch', 'source_frame'};
  static const _receiptFields = {
    'bucket',
    'path',
    'generation',
    'sha256',
    'manifest_path',
    'manifest_generation',
    'manifest_sha256',
    'pcm_sha256',
    'conversation_id',
    'start',
    'samples',
    'sample_rate',
  };

  final String _wire;
  final String owner;
  final List<CustodyFrame> frames;
  final String? recordingSessionId;
  final String? conversationId;

  // Keep the receipt and its original frame rows intact when journaling for restart.
  Map<String, dynamic> toJson() => jsonDecode(_wire) as Map<String, dynamic>;

  static AudioCustodyEvent? parse(Map<String, dynamic> json) {
    final archiveRoot = json['capture_root'];
    final session = json['recording_session_id'];
    final receipt = json['receipt'];
    final rows = json['frames'];
    // Listen uses index 0 for mono and also for the first channel of a
    // multichannel socket. The caller must additionally know the socket is mono.
    if (!json.keys.every(_eventFields.contains) ||
        json['type'] != 'audio_custody' ||
        json['channel'] != '0' ||
        archiveRoot is! String ||
        !_archiveRoot.hasMatch(archiveRoot) ||
        (session != null && (session is! String || session.trim().isEmpty)) ||
        receipt is! Map<String, dynamic> ||
        !_validReceipt(receipt, archiveRoot) ||
        rows is! List ||
        rows.isEmpty ||
        rows.length > _maxFrames) {
      return null;
    }

    final frames = <CustodyFrame>[];
    var previousSequence = -1;
    for (final row in rows) {
      if (row is! Map<String, dynamic> || !row.keys.every(_frameFields.contains)) return null;
      final sequence = row['sequence'], hash = row['sha256'];
      if (sequence is! int ||
          sequence <= previousSequence ||
          !_matches(_sha256, hash) ||
          !_nonnegativeInt(row['byte_offset']) ||
          !_positiveInt(row['bytes']) ||
          !_finiteNumber(row['start']) ||
          !_nonnegativeInt(row['samples']) ||
          row['gap_before'] is! bool) {
        return null;
      }
      previousSequence = sequence;
      final source = row['source'];
      if (source == null) continue;
      if (source is! Map<String, dynamic> || !source.keys.every(_sourceFields.contains)) return null;
      final root = source['capture_root'], epoch = source['clock_epoch'], ordinal = source['source_frame'];
      if (root is! String ||
          !_sourceRoot.hasMatch(root) ||
          epoch is! int ||
          epoch < 0 ||
          ordinal is! int ||
          ordinal < 0 ||
          ordinal + 1 <= ordinal) {
        return null;
      }
      frames.add(CustodyFrame._(captureRoot: root, channel: 'mono', clockEpoch: epoch, ordinal: ordinal, sha256: hash));
    }
    if (frames.isEmpty) return null;
    try {
      return AudioCustodyEvent._(
        jsonEncode(json),
        (receipt['path'] as String).split('/')[1],
        List.unmodifiable(frames),
        session as String?,
        receipt['conversation_id'] as String?,
      );
    } on JsonUnsupportedObjectError {
      return null;
    }
  }

  static bool _validReceipt(Map<String, dynamic> receipt, String archiveRoot) {
    final bucket = receipt['bucket'], original = receipt['path'], manifest = receipt['manifest_path'];
    final originalSha = receipt['sha256'], manifestSha = receipt['manifest_sha256'];
    final conversation = receipt['conversation_id'], pcmSha = receipt['pcm_sha256'];
    if (!receipt.keys.every(_receiptFields.contains) ||
        !_pathPart(bucket) ||
        original is! String ||
        manifest is! String ||
        !_matches(_generation, receipt['generation']) ||
        !_matches(_generation, receipt['manifest_generation']) ||
        !_matches(_sha256, originalSha) ||
        !_matches(_sha256, manifestSha) ||
        (pcmSha != null && !_matches(_sha256, pcmSha)) ||
        (conversation != null && !_pathPart(conversation)) ||
        !_finiteNumber(receipt['start']) ||
        !_nonnegativeInt(receipt['samples']) ||
        !_positiveInt(receipt['sample_rate'])) {
      return false;
    }

    final originalParts = original.split('/');
    final manifestParts = manifest.split('/');
    if (originalParts.length != 8 ||
        manifestParts.length != 8 ||
        originalParts[0] != 'raw-live' ||
        manifestParts[0] != 'audio-outbox' ||
        !_pathPart(originalParts[1]) ||
        originalParts[2] != (conversation ?? 'unlinked') ||
        originalParts[4] != '0' ||
        originalParts[5] != archiveRoot) {
      return false;
    }
    for (var i = 1; i < 7; i++) {
      if (originalParts[i] != manifestParts[i] || !_pathPart(originalParts[i])) return false;
    }
    final suffix = original.endsWith('.enc') ? '.bin.enc' : '.bin';
    // Framed manifests use the media digest in their path. Older unframed
    // manifests use their own digest. Both pin the manifest SHA independently.
    return originalParts.last == '$originalSha$suffix' &&
        (manifestParts.last == '$manifestSha$suffix' || manifestParts.last == '$originalSha$suffix');
  }

  static bool _pathPart(dynamic value) =>
      value is String && value.trim().isNotEmpty && value != '.' && value != '..' && !value.contains('/');
  static bool _matches(RegExp pattern, dynamic value) => value is String && pattern.hasMatch(value);
  static bool _nonnegativeInt(dynamic value) => value is int && value >= 0;
  static bool _positiveInt(dynamic value) => value is int && value > 0;
  static bool _finiteNumber(dynamic value) => value is num && value.isFinite;
}
