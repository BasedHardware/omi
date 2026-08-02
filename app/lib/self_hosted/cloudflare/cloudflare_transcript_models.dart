import 'cloudflare_transcript_exception.dart';

class CloudflareTranscriptSession {
  const CloudflareTranscriptSession({
    required this.id,
    required this.status,
    this.createdAt,
    this.recordedAt,
    this.characterCount,
  });

  factory CloudflareTranscriptSession.fromJson(Map<String, dynamic> json) {
    return CloudflareTranscriptSession(
      id: json['id'] as String? ?? '',
      status: json['status'] as String? ?? 'unknown',
      createdAt: _parseDate(json['created_at']),
      recordedAt: _parseDate(json['recorded_at']),
      characterCount: _parseInt(json['transcript_char_count']) ?? _parseInt(json['character_count']),
    );
  }

  final String id;
  final String status;
  final DateTime? createdAt;
  final DateTime? recordedAt;
  final int? characterCount;

  DateTime? get displayTime => recordedAt ?? createdAt;
}

class CloudflareTranscriptChunk {
  const CloudflareTranscriptChunk({required this.sequence, required this.text});

  factory CloudflareTranscriptChunk.fromJson(Map<String, dynamic> json) {
    return CloudflareTranscriptChunk(
      sequence: _requiredJsonInt(json['sequence']),
      text: json['text'] as String? ?? '',
    );
  }

  final int sequence;
  final String text;
}

class CloudflareTranscriptDetail {
  const CloudflareTranscriptDetail({required this.session, required this.chunks});

  factory CloudflareTranscriptDetail.fromJson(Map<String, dynamic> json) {
    final rawChunks = json['chunks'];
    final chunks = rawChunks is List
        ? rawChunks
            .whereType<Map>()
            .map((item) => CloudflareTranscriptChunk.fromJson(Map<String, dynamic>.from(item)))
            .toList()
        : <CloudflareTranscriptChunk>[];
    chunks.sort((a, b) => a.sequence.compareTo(b.sequence));
    final rawSession = json['session'];
    return CloudflareTranscriptDetail(
      session: CloudflareTranscriptSession.fromJson(
        rawSession is Map ? Map<String, dynamic>.from(rawSession) : json,
      ),
      chunks: chunks,
    );
  }

  final CloudflareTranscriptSession session;
  final List<CloudflareTranscriptChunk> chunks;

  String get fullText => chunks.map((chunk) => chunk.text.trim()).where((text) => text.isNotEmpty).join('\n');
}

DateTime? _parseDate(Object? value) => value is String ? DateTime.tryParse(value)?.toLocal() : null;

int? _parseInt(Object? value) => value is int ? value : int.tryParse(value?.toString() ?? '');

int _requiredJsonInt(Object? value) {
  if (value is int) return value;
  throw const CloudflareTranscriptApiException.malformedTranscriptChunk();
}
