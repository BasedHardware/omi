import 'dart:convert';
import 'dart:math';

class Structured {
  int id = 0;

  String title;
  String overview;
  String emoji;
  String category;

  List<ActionItem> actionItems = [];

  List<Event> events = [];

  Structured(this.title, this.overview, {this.id = 0, this.emoji = '', this.category = 'other'});

  getEmoji() {
    try {
      if (emoji.isNotEmpty) return utf8.decode(emoji.toString().codeUnits);
      return ['🧠', '😎', '🧑‍💻', '🚀'][Random().nextInt(4)];
    } catch (e) {
      // return ['🧠', '😎', '🧑‍💻', '🚀'][Random().nextInt(4)];
      return emoji; // should return random?
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
      for (dynamic item in aItems) {
        if (item.runtimeType == String) {
          if (item.isEmpty) continue;
          structured.actionItems.add(ActionItem(item));
        } else {
          structured.actionItems.add(ActionItem.fromJson(item));
        }
      }
    }

    if (json['events'] != null) {
      for (dynamic event in json['events']) {
        if (event.isEmpty) continue;
        structured.events.add(Event(
          event['title'],
          DateTime.parse(event['startsAt'] ?? event['start']).toLocal(),
          event['duration'],
          description: event['description'] ?? '',
          created: event['created'] ?? false,
        ));
      }
    }
    return structured;
  }

  @override
  String toString() {
    var str = '';
    str += '${getEmoji()} $title\n\n$overview\n\n'; // ($category)
    if (actionItems.isNotEmpty) {
      str += 'Action Items:\n';
      for (var item in actionItems) {
        str += '- ${item.description}\n';
      }
    }
    if (events.isNotEmpty) {
      str += 'Events:\n';
      for (var event in events) {
        str += '- ${event.title} (${event.startsAt.toLocal()} for ${event.duration} minutes)\n';
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

class ActionItem {
  int id = 0;

  String description;
  bool completed = false;
  bool deleted = false;

  ActionItem(this.description, {this.id = 0, this.completed = false, this.deleted = false});

  static fromJson(Map<String, dynamic> json) {
    return ActionItem(json['description'], completed: json['completed'] ?? false, deleted: json['deleted'] ?? false);
  }

  toJson() => {'description': description, 'completed': completed, 'deleted': deleted};
}

class AppResponse {
  int id = 0;

  String? appId;
  String content;

  AppResponse(this.content, {this.id = 0, this.appId});

  toJson() => {'pluginId': appId, 'content': content};

  factory AppResponse.fromJson(Map<String, dynamic> json) {
    return AppResponse(json['content'], appId: json['pluginId'] ?? json['plugin_id']);
  }
}

class Event {
  int id = 0;

  String title;
  DateTime startsAt;
  int duration;

  String description;
  bool created = false;

  Event(this.title, this.startsAt, this.duration, {this.description = '', this.created = false, this.id = 0});

  toJson() {
    return {
      'title': title,
      'startsAt': startsAt.toUtc().toIso8601String(),
      'duration': duration,
      'description': description,
      'created': created,
    };
  }
}

class MemoryPhoto {
  int id = 0;

  String base64;
  String description;

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
