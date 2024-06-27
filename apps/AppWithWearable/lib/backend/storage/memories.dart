import 'dart:convert';
import 'dart:math';

import 'package:friend_private/backend/storage/plugin.dart';
import 'package:tuple/tuple.dart';

class MemoryStructured {
  String title;
  String overview;
  List<String> actionItems;
  List<Tuple2<Plugin, String>> pluginsResponse;
  String emoji;
  String category;

  MemoryStructured({
    this.title = "",
    this.overview = "",
    required this.actionItems,
    required this.pluginsResponse,
    this.emoji = '',
    this.category = '',
  });

  factory MemoryStructured.fromJson(Map<String, dynamic> json) => MemoryStructured(
      title: json['title'] ?? '',
      overview: json['overview'] ?? '',
      actionItems: List<String>.from(json['action_items'] ?? []),
      pluginsResponse: List<Tuple2<Plugin, String>>.from(json['pluginsResponse'] ?? []),
      category: json['category'] ?? '',
      emoji: json['emoji'] ?? '');

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
