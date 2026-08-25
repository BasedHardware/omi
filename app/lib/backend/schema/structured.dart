import 'dart:convert';
import 'dart:math';

import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
// Phase 4.1 — Structured, ActionItem, AppResponse, and Event are kept as deliberate
// adapters, not typedefs:
//  - Structured: client-only `id`, getEmoji() behavior (utf8 decode + random pick),
//    fromJson that accepts String action items, and toJson that serializes actionItems
//    as description strings (generated emits objects).
//  - ActionItem: client-only `id`/`deleted` fields absent from GeneratedActionItem.
//  - AppResponse: client-only `id` and toJson key 'appId' (generated emits 'app_id').
//  - Event: client-only `id`, field name `startsAt` (generated `start`), and fromJson
//    epoch-int -> DateTime conversion.

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
      json['title'] ?? '',
      json['overview'] ?? '',
      emoji: json['emoji'] ?? '🧠',
      category: json['category'] ?? 'other',
    );
    final aItems = json['actionItems'] ?? json['action_items'];
    if (aItems is List) {
      for (final item in aItems) {
        if (item is String) {
          if (item.isEmpty) continue;
          structured.actionItems.add(ActionItem(item));
        } else if (item is Map<String, dynamic>) {
          structured.actionItems.add(ActionItem.fromJson(item));
        } else if (item is Map) {
          structured.actionItems.add(ActionItem.fromJson(Map<String, dynamic>.from(item)));
        }
      }
    }

    final events = json['events'];
    if (events is List) {
      for (final event in events) {
        if (event is Map && event.isEmpty) continue;
        if (event is Map<String, dynamic>) {
          structured.events.add(Event.fromJson(event));
        } else if (event is Map) {
          structured.events.add(Event.fromJson(Map<String, dynamic>.from(event)));
        }
      }
    }
    return structured;
  }

  factory Structured.fromGenerated(wire.GeneratedStructured generated) {
    var structured = Structured(
      generated.title,
      generated.overview,
      emoji: generated.emoji,
      category: generated.category,
    );
    structured.actionItems = generated.actionItems?.map(ActionItem.fromGenerated).toList() ?? [];
    structured.events = generated.events?.map(Event.fromGenerated).toList() ?? [];
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

  wire.GeneratedStructured toGenerated() {
    return wire.GeneratedStructured(
      title: title,
      overview: overview,
      emoji: emoji,
      category: category,
      actionItems: actionItems.map((item) => item.toGenerated()).toList(),
      events: events.map((event) => event.toGenerated()).toList(),
    );
  }
}

class ActionItem {
  int id = 0;

  String description;
  bool completed = false;
  bool deleted = false;

  ActionItem(this.description, {this.id = 0, this.completed = false, this.deleted = false});

  factory ActionItem.fromGenerated(wire.GeneratedActionItem generated) {
    return ActionItem(generated.description, completed: generated.completed);
  }

  static fromJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedActionItem.fromJson(json);
    return ActionItem(
      generated.description,
      completed: generated.completed,
      deleted: json['deleted'] ?? false,
    );
  }

  wire.GeneratedActionItem toGenerated() {
    return wire.GeneratedActionItem(description: description, completed: completed);
  }

  toJson() => {...toGenerated().toJson(), 'deleted': deleted};
}

class AppResponse {
  int id = 0;

  String? appId;
  String content;

  AppResponse(this.content, {this.id = 0, this.appId});

  factory AppResponse.fromGenerated(wire.GeneratedAppResult generated) {
    return AppResponse(generated.content, appId: generated.appId);
  }

  wire.GeneratedAppResult toGenerated() {
    return wire.GeneratedAppResult(appId: appId, content: content);
  }

  toJson() => {'appId': appId, 'content': content};

  factory AppResponse.fromJson(Map<String, dynamic> json) {
    return AppResponse.fromGenerated(wire.GeneratedAppResult.fromJson(json));
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

  factory Event.fromGenerated(wire.GeneratedEvent generated) {
    return Event(
      generated.title,
      generated.start,
      generated.duration,
      description: generated.description,
      created: generated.created,
    );
  }

  factory Event.fromJson(Map<String, dynamic> json) {
    final rawStart = json['startsAt'] ?? json['start'];
    if (rawStart is int) {
      return Event(
        json['title'] ?? '',
        DateTime.fromMillisecondsSinceEpoch(rawStart * 1000).toLocal(),
        json['duration'] ?? 30,
        description: json['description'] ?? '',
        created: json['created'] ?? false,
      );
    }
    return Event.fromGenerated(wire.GeneratedEvent.fromJson(json));
  }

  wire.GeneratedEvent toGenerated() {
    return wire.GeneratedEvent(
      title: title,
      start: startsAt,
      duration: duration,
      description: description,
      created: created,
    );
  }

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
