import 'dart:convert';
import 'dart:math';

import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:objectbox/objectbox.dart';

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

  String? recordingFilePath;

  final structured = ToOne<Structured>();

  @Backlink('memory')
  final pluginsResponse = ToMany<PluginResponse>();

  @Index()
  bool discarded;

  Memory(
    this.createdAt,
    this.transcript,
    this.discarded, {
    this.id = 0,
    this.recordingFilePath,
    this.startedAt,
    this.finishedAt,
  });

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
      for (String response in json['pluginsResponse']) {
        if (response.isEmpty) continue;
        memory.pluginsResponse.add(PluginResponse(response));
      }
    }

    if (json['transcriptSegments'] != null) {
      for (dynamic segment in json['transcriptSegments']) {
        if (segment.isEmpty) continue;
        memory.transcriptSegments.add(TranscriptSegment.fromJson(segment));
      }
    }

    return memory;
  }

  String getTranscript({int? maxCount}) {
    try {
      var transcript = this.transcript;
      if (maxCount != null) transcript = transcript.substring(0, min(maxCount, transcript.length));
      return utf8.decode(transcript.toString().codeUnits);
    } catch (e) {
      return transcript;
    }
  }

  toJson() {
    return {
      'id': id,
      'createdAt': createdAt.toIso8601String(),
      'transcript': transcript,
      'recordingFilePath': recordingFilePath,
      'structured': structured.target!.toJson(),
      'pluginsResponse': pluginsResponse.map<String>((response) => response.content).toList(),
      'discarded': discarded,
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
    if (json['actionItems'] != null) {
      for (String item in json['actionItems']) {
        if (item.isEmpty) continue;
        structured.actionItems.add(ActionItem(item));
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
}
