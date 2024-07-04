import 'dart:convert';
import 'dart:math';

import 'package:friend_private/backend/storage/plugin.dart';
import 'package:tuple/tuple.dart';

class MemoryCalendarEvent {
  String title;
  String? description;
  DateTime startsAt;
  int duration;

  MemoryCalendarEvent({
    required this.title,
    this.description,
    required this.startsAt,
    this.duration = 30,
  });

  factory MemoryCalendarEvent.fromJson(Map<String, dynamic> json) => MemoryCalendarEvent(
        title: json['title'] ?? '',
        startsAt: DateTime.parse(json['startsAt']),
        description: json['description'],
        duration: json['duration'] ?? 30,
      );

  static fromJsonList(List<dynamic> json) => json.map((e) => MemoryCalendarEvent.fromJson(e)).toList();

  Map<String, dynamic> toJson() => {
        'title': title,
        'startsAt': startsAt,
        'description': description,
        'duration': duration,
      };
}

class MemoryStructured {
  String title;
  String overview;
  List<String> actionItems;
  List<Tuple2<Plugin, String>> pluginsResponse;
  String emoji;
  String category;
  List<MemoryCalendarEvent> events;

  MemoryStructured({
    this.title = "",
    this.overview = "",
    required this.actionItems,
    required this.pluginsResponse,
    this.emoji = '',
    this.category = '',
    this.events = const [],
  });

  factory MemoryStructured.fromJson(Map<String, dynamic> json) => MemoryStructured(
        title: json['title'] ?? '',
        overview: json['overview'] ?? '',
        actionItems: List<String>.from(json['action_items'] ?? []),
        pluginsResponse: List<Tuple2<Plugin, String>>.from(json['pluginsResponse'] ?? []),
        category: json['category'] ?? '',
        emoji: json['emoji'] ?? '',
        events: MemoryCalendarEvent.fromJsonList(json['events'] ?? []),
      );

  Map<String, dynamic> toJson() => {
        'title': title,
        'overview': overview,
        'action_items': List<dynamic>.from(actionItems),
        'pluginsResponse': List<dynamic>.from(pluginsResponse),
        'emoji': emoji,
        'category': category,
      };

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
