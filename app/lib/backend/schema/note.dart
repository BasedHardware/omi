enum NoteType { voice, text }

enum NoteVisibility { private_, shared }

class Note {
  String id;
  String uid;
  String? title;
  String content;
  NoteType type;
  DateTime createdAt;
  DateTime updatedAt;
  bool discarded;
  bool deleted;
  bool edited;
  NoteVisibility visibility;
  bool isLocked;
  double? duration; // in seconds, for voice notes
  String? transcription; // for voice notes

  Note({
    required this.id,
    required this.uid,
    this.title,
    required this.content,
    required this.type,
    required this.createdAt,
    required this.updatedAt,
    this.discarded = false,
    this.deleted = false,
    this.edited = false,
    this.visibility = NoteVisibility.private_,
    this.isLocked = false,
    this.duration,
    this.transcription,
  });

  factory Note.fromJson(Map<String, dynamic> json) {
    return Note(
      id: json['id'] ?? '',
      uid: json['uid'] ?? '',
      title: json['title'],
      content: json['content'] ?? '',
      type: json['type'] != null
          ? (NoteType.values.asNameMap()[json['type']] ?? NoteType.text)
          : NoteType.text,
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at']).toLocal()
          : DateTime.now(),
      updatedAt: json['updated_at'] != null
          ? DateTime.parse(json['updated_at']).toLocal()
          : DateTime.now(),
      discarded: json['discarded'] ?? false,
      deleted: json['deleted'] ?? false,
      edited: json['edited'] ?? false,
      visibility: json['visibility'] != null
          ? (NoteVisibility.values.asNameMap()[json['visibility']] ?? NoteVisibility.private_)
          : NoteVisibility.private_,
      isLocked: json['is_locked'] ?? false,
      duration: json['duration'] != null ? (json['duration'] as num).toDouble() : null,
      transcription: json['transcription'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'uid': uid,
      'title': title,
      'content': content,
      'type': type.toString().split('.').last,
      'created_at': createdAt.toUtc().toIso8601String(),
      'updated_at': updatedAt.toUtc().toIso8601String(),
      'discarded': discarded,
      'deleted': deleted,
      'edited': edited,
      'visibility': visibility.name,
      'is_locked': isLocked,
      'duration': duration,
      'transcription': transcription,
    };
  }

  Note copyWith({
    String? id,
    String? uid,
    String? title,
    String? content,
    NoteType? type,
    DateTime? createdAt,
    DateTime? updatedAt,
    bool? discarded,
    bool? deleted,
    bool? edited,
    NoteVisibility? visibility,
    bool? isLocked,
    double? duration,
    String? transcription,
  }) {
    return Note(
      id: id ?? this.id,
      uid: uid ?? this.uid,
      title: title ?? this.title,
      content: content ?? this.content,
      type: type ?? this.type,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      discarded: discarded ?? this.discarded,
      deleted: deleted ?? this.deleted,
      edited: edited ?? this.edited,
      visibility: visibility ?? this.visibility,
      isLocked: isLocked ?? this.isLocked,
      duration: duration ?? this.duration,
      transcription: transcription ?? this.transcription,
    );
  }

  String get displayTitle {
    if (title != null && title!.isNotEmpty) return title!;
    if (type == NoteType.voice) {
      return 'Voice Note';
    }
    return content.length > 50 ? '${content.substring(0, 50)}...' : content;
  }

  String get formattedDuration {
    if (duration == null) return '';
    final minutes = (duration! / 60).floor();
    final seconds = (duration! % 60).floor();
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
  }
}
