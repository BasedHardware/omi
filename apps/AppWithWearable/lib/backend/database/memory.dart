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

  Memory(this.createdAt, this.transcript, this.discarded, {this.id = 0});
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
        str += '- $item\n';
      }
    }
    return str;
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
