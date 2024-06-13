import 'dart:convert';
import 'dart:math';

import 'package:objectbox/objectbox.dart';

@Entity()
class Memory {
  @Id()
  int id = 0;

  @Index()
  @Property(type: PropertyType.date)
  DateTime createdAt;

  String transcript;
  String? recordingFilePath;
  final structured = ToOne<Structured>();

  @Backlink('memory')
  final pluginsResponse = ToMany<PluginResponse>();

  @Index()
  bool discarded;

  Memory(this.createdAt, this.transcript, this.discarded, {this.id = 0, this.recordingFilePath});

  static String memoriesToString(List<Memory> memories) => memories
      .map((e) => '''
      ${e.createdAt.toIso8601String().split('.')[0]}
      Title: ${e.structured.target!.title}
      Summary: ${e.structured.target!.overview}
      ${e.structured.target!.actionItems.isNotEmpty ? 'Action Items:' : ''}
      ${e.structured.target!.actionItems.map((item) => '  - ${item.description}').join('\n')}
      ${e.pluginsResponse.isNotEmpty ? 'Plugins Response:' : ''}
      ${e.pluginsResponse.map((response) => '  - ${response.content}').join('\n')}
      Category: ${e.structured.target!.category}
      '''
          .replaceAll('      ', '')
          .trim())
      .join('\n\n');

  String getTranscript({int? maxCount}) {
    try {
      var transcript = this.transcript;
      if (maxCount != null) {
        transcript = transcript.substring(0, min(maxCount, transcript.length));
      }
      return utf8.decode(transcript.toString().codeUnits);
    } catch (e) {
      return transcript;
    }
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

  Structured(this.title, this.overview, {this.emoji = '', this.category = 'other'});

  getEmoji() {
    try {
      return utf8.decode(emoji.toString().codeUnits);
    } catch (e) {
      return ['🧠', '😎', '🧑‍💻', '🎂'][Random().nextInt(4)];
    }
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

  String content;
  final memory = ToOne<Memory>();

  PluginResponse(this.content);
}
