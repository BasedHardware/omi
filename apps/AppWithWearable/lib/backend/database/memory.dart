import 'dart:convert';
import 'dart:math';

import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:objectbox/objectbox.dart';

enum MemoryType { audio, image }

@Entity()
class Memory {
  @Id()
  int id = 0;

  @Index()
  @Property(type: PropertyType.date)
  DateTime createdAt;

  @Property(type: PropertyType.date)
  DateTime? startedAt;

  @Property(type: PropertyType.date)
  DateTime? finishedAt;

  String transcript;
  final transcriptSegments = ToMany<TranscriptSegment>();
  final photos = ToMany<MemoryPhoto>();

  String? recordingFilePath;

  final structured = ToOne<Structured>();

  @Backlink('memory')
  final pluginsResponse = ToMany<PluginResponse>();

  @Index()
  bool discarded;

  final geolocation = ToOne<Geolocation>();

  Memory(
    this.createdAt,
    this.transcript,
    this.discarded, {
    this.id = 0,
    this.recordingFilePath,
    this.startedAt,
    this.finishedAt,
  });

  MemoryType get type => transcript.isNotEmpty ? MemoryType.audio : MemoryType.image;

  static String memoriesToString(List<Memory> memories, {bool includeTranscript = false}) => memories
      .map((e) => '''
      ${e.createdAt.toIso8601String().split('.')[0]}
      Title: ${e.structured.target!.title}
      Summary: ${e.structured.target!.overview}
      ${e.structured.target!.actionItems.isNotEmpty ? 'Action Items:' : ''}
      ${e.structured.target!.actionItems.map((item) => '  - ${item.description}').join('\n')}
      Category: ${e.structured.target!.category}
      ${includeTranscript ? 'Transcript:\n${e.transcript}' : ''}
      '''
          .replaceAll('      ', '')
          .trim())
      .join('\n\n');

  static Memory fromJson(Map<String, dynamic> json) {
    var memory = Memory(
      DateTime.parse(json['createdAt']),
      json['transcript'],
      json['discarded'],
      recordingFilePath: json['recordingFilePath'],
      startedAt: json['startedAt'] != null ? DateTime.parse(json['startedAt']) : null,
      finishedAt: json['finishedAt'] != null ? DateTime.parse(json['finishedAt']) : null,
    );
    memory.structured.target = Structured.fromJson(json['structured']);
    if (json['pluginsResponse'] != null) {
      for (dynamic response in json['pluginsResponse']) {
        if (response.isEmpty) continue;
        if (response is String) {
          memory.pluginsResponse.add(PluginResponse(response));
        } else {
          memory.pluginsResponse.add(PluginResponse.fromJson(response));
        }
      }
    }

    if (json['transcriptSegments'] != null) {
      for (dynamic segment in json['transcriptSegments']) {
        if (segment.isEmpty) continue;
        memory.transcriptSegments.add(TranscriptSegment.fromJson(segment));
      }
    }

    if (json['photos'] != null) {
      for (dynamic photo in json['photos']) {
        if (photo.isEmpty) continue;
        memory.photos.add(MemoryPhoto.fromJson(photo));
      }
    }

    return memory;
  }

  String getTranscript({int? maxCount, bool generate = false}) {
    try {
      var transcript = generate && transcriptSegments.isNotEmpty
          ? TranscriptSegment.segmentsAsString(transcriptSegments, includeTimestamps: true)
          : this.transcript;
      var decoded = utf8.decode(transcript.codeUnits);
      if (maxCount != null) return decoded.substring(0, min(maxCount, decoded.length));
      return decoded;
    } catch (e) {
      return transcript;
    }
  }

  toJson() {
    return {
      'id': id,
      'createdAt': createdAt.toIso8601String(),
      'startedAt': startedAt?.toIso8601String(),
      'finishedAt': finishedAt?.toIso8601String(),
      'transcript': transcript,
      'recordingFilePath': recordingFilePath,
      'structured': structured.target!.toJson(),
      'pluginsResponse': pluginsResponse.map<Map<String, String?>>((response) => response.toJson()).toList(),
      'discarded': discarded,
      'transcriptSegments': transcriptSegments.map((segment) => segment.toJson()).toList(),
      'photos': photos.map((photo) => photo.toJson()).toList(),
    };
  }
}

@Entity()
class Structured {
  @Id()
  int id = 0;

  String title;
  String overview;
  String emoji;
  String category;

  @Backlink('structured')
  final actionItems = ToMany<ActionItem>();

  @Backlink('structured')
  final events = ToMany<Event>();

  Structured(this.title, this.overview, {this.id = 0, this.emoji = '', this.category = 'other'});

  getEmoji() {
    try {
      if (emoji.isNotEmpty) return utf8.decode(emoji.toString().codeUnits);
      return ['🧠', '😎', '🧑‍💻', '🚀'][Random().nextInt(4)];
    } catch (e) {
      return ['🧠', '😎', '🧑‍💻', '🎂'][Random().nextInt(4)];
    }
  }

  static Structured fromJson(Map<String, dynamic> json) {
    var structured = Structured(
      json['title'],
      json['overview'],
      emoji: json['emoji'],
      category: json['category'],
    );
    var aItems = json['actionItems'] ?? json['action_items'];
    if (aItems != null) {
      for (String item in aItems) {
        if (item.isEmpty) continue;
        structured.actionItems.add(ActionItem(item));
      }
    }

    if (json['events'] != null) {
      for (dynamic event in json['events']) {
        if (event.isEmpty) continue;
        structured.events.add(Event(
          event['title'],
          DateTime.parse(event['startsAt']),
          event['duration'],
          description: event['description'] ?? '',
          created: false,
        ));
      }
    }
    return structured;
  }

  @override
  String toString() {
    var str = '';
    str += '${getEmoji()} $title ($category)\n\nSummary: $overview\n\n';
    if (actionItems.isNotEmpty) {
      str += 'Action Items:\n';
      for (var item in actionItems) {
        str += '- ${item.description}\n';
      }
    }
    return str.trim();
  }

  toJson() {
    return {
      'title': title,
      'overview': overview,
      'emoji': emoji,
      'category': category,
      'actionItems': actionItems.map((item) => item.description).toList(),
      'events': events.map((event) => event.toJson()).toList(),
    };
  }
}

@Entity()
class ActionItem {
  @Id()
  int id = 0;

  String description;
  bool completed = false;
  final structured = ToOne<Structured>();

  ActionItem(this.description, {this.id = 0, this.completed = false});
}

@Entity()
class PluginResponse {
  @Id()
  int id = 0;

  String? pluginId;
  String content;

  final memory = ToOne<Memory>();

  PluginResponse(this.content, {this.id = 0, this.pluginId});

  toJson() {
    return {
      'pluginId': pluginId,
      'content': content,
    };
  }

  factory PluginResponse.fromJson(Map<String, dynamic> json) {
    return PluginResponse(json['content'], pluginId: json['pluginId']);
  }
}

@Entity()
class Event {
  @Id()
  int id = 0;

  String title;
  DateTime startsAt;
  int duration;

  String description;
  bool created = false;

  final structured = ToOne<Structured>();

  Event(this.title, this.startsAt, this.duration, {this.description = '', this.created = false, this.id = 0});

  toJson() {
    return {
      'title': title,
      'startsAt': startsAt.toIso8601String(),
      'duration': duration,
      'description': description,
      'created': created,
    };
  }
}

@Entity()
class MemoryPhoto {
  @Id()
  int id = 0;

  String base64;
  String description;
  final memory = ToOne<Memory>();

  MemoryPhoto(this.base64, this.description, {this.id = 0});

  factory MemoryPhoto.fromJson(Map<String, dynamic> json) {
    return MemoryPhoto(json['base64'], json['description']);
  }

  toJson() {
    return {
      'base64': base64,
      'description': description,
    };
  }
}
