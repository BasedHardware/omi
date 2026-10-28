import 'dart:convert';

import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
// Phase 4.1 — Structured, ActionItem, AppResponse, and Event are kept as deliberate
// adapters, not typedefs:
//  - Structured: client-only `id`, getEmoji() behavior (utf8 decode + random pick),
//    fromJson that accepts String action items, and cache JSON that retains each
//    valid action item's original stored row coordinate even when bad rows were skipped.
//  - ActionItem: client-only `id`/`deleted` fields absent from GeneratedActionItem.
//  - AppResponse: client-only `id` and toJson key 'appId' (generated emits 'app_id').
//  - Event: client-only `id`, field name `startsAt` (generated `start`), and fromJson
//    epoch-int -> DateTime conversion.

// Section has no client-only fields or behavior, so it stays a typedef over the wire type.
typedef Section = wire.GeneratedSection;

class Structured {
  /// The neutral emoji for a row where nothing chose one (server
  /// `models.conversation_emoji.NEUTRAL_EMOJI`). 🧠 is the server's
  /// "extraction omitted the field" sentinel and must not be the
  /// missing/empty fallback here.
  static const String neutralEmoji = '💬';

  int id = 0;

  String title;
  String overview;
  String emoji;
  String category;

  List<Section> sections = [];

  List<ActionItem> actionItems = [];

  List<Event> events = [];

  /// 'highlight' or 'background' from the notes pass (Episodes M3); null on legacy notes.
  String? salience;

  Structured(this.title, this.overview, {this.id = 0, this.emoji = '', this.category = 'other', this.salience});

  bool get isBackground => salience == 'background';

  getEmoji() {
    try {
      if (emoji.isNotEmpty) return utf8.decode(emoji.toString().codeUnits);
      return neutralEmoji;
    } catch (e) {
      return emoji; // should return random?
    }
  }

  static Structured fromJson(Map<String, dynamic> json) {
    final emojiSource = json['emoji'];
    var structured = Structured(
      json['title'] ?? '',
      json['overview'] ?? '',
      emoji: emojiSource is String && emojiSource.trim().isNotEmpty ? emojiSource : neutralEmoji,
      category: json['category'] ?? 'other',
      salience: json['salience'] is String ? json['salience'] as String : null,
    );
    final sections = json['sections'];
    if (sections is List) {
      for (final section in sections) {
        final Map<String, dynamic>? sectionJson = section is Map<String, dynamic>
            ? section
            : section is Map
                ? Map<String, dynamic>.from(section)
                : null;
        if (sectionJson == null) continue;
        // Section.fromJson throws a FormatException on a missing or mistyped
        // `heading` / `body_markdown`. Skip the bad entry the way the
        // actionItems and events loops below do: one malformed section used to
        // throw out of here and take the whole conversation decode with it.
        try {
          structured.sections.add(Section.fromJson(sectionJson));
        } on FormatException {
          continue;
        }
      }
    }

    final aItems = json['actionItems'] ?? json['action_items'];
    if (aItems is List) {
      for (final entry in aItems.indexed) {
        final item = entry.$2;
        if (item is String) {
          if (item.isEmpty) continue;
          structured.actionItems.add(ActionItem(item, sourceIndex: entry.$1));
        } else if (item is Map) {
          final itemJson = item is Map<String, dynamic> ? item : Map<String, dynamic>.from(item);
          try {
            structured.actionItems.add(ActionItem.fromJson(itemJson,
                sourceIndex: entry.$1, retainCachedSourceIndex: json['actionItems'] is List));
          } on FormatException {
            continue;
          } on TypeError {
            continue;
          }
        }
      }
    }

    final events = json['events'];
    if (events is List) {
      for (final event in events) {
        if (event is Map && event.isEmpty) continue;
        if (event is Map) {
          final eventJson = event is Map<String, dynamic> ? event : Map<String, dynamic>.from(event);
          try {
            structured.events.add(Event.fromJson(eventJson));
          } on FormatException {
            continue;
          } on TypeError {
            continue;
          }
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
      salience: generated.salience,
    );
    structured.sections = generated.sections?.toList() ?? [];
    structured.actionItems = generated.actionItems?.indexed
            .map((entry) => ActionItem.fromGenerated(entry.$2, sourceIndex: entry.$1))
            .toList() ??
        [];
    structured.events = generated.events?.map(Event.fromGenerated).toList() ?? [];
    return structured;
  }

  @override
  String toString() {
    var str = '';
    str += '${getEmoji()} $title\n\n$overview\n\n'; // ($category)
    for (var section in sections) {
      str += '${section.heading}\n${section.bodyMarkdown}\n\n';
    }
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
      'sections': sections.map((section) => section.toJson()).toList(),
      // This is the client cache adapter, not a task-write payload. Keep coordinates
      // alongside the compacted rows, plus completed/deleted state, for safe recovery
      // after reopening. Legacy description-string caches remain readable above.
      'actionItems': actionItems
          .map((item) => {
                ...item.toJson(),
                if (item.sourceIndex != null) '_cache_source_index': item.sourceIndex,
              })
          .toList(),
      'events': events.map((event) => event.toJson()).toList(),
      if (salience != null) 'salience': salience,
    };
  }

  wire.GeneratedStructured toGenerated() {
    return wire.GeneratedStructured(
      title: title,
      overview: overview,
      emoji: emoji,
      category: category,
      sections: sections.toList(),
      actionItems: actionItems.map((item) => item.toGenerated()).toList(),
      events: events.map((event) => event.toGenerated()).toList(),
      salience: salience,
    );
  }
}

class ActionItem {
  int id = 0;

  /// Index in the original stored summary array, independent of filtered UI rows.
  /// Client cache metadata only; never included in generated wire/task-write payloads.
  final int? sourceIndex;

  String description;
  bool completed = false;
  bool deleted = false;

  ActionItem(this.description, {this.id = 0, this.completed = false, this.deleted = false, this.sourceIndex});

  factory ActionItem.fromGenerated(wire.GeneratedActionItem generated, {int? sourceIndex}) {
    return ActionItem(generated.description, completed: generated.completed, sourceIndex: sourceIndex);
  }

  static ActionItem fromJson(Map<String, dynamic> json, {int? sourceIndex, bool retainCachedSourceIndex = false}) {
    if (retainCachedSourceIndex && json.containsKey('_cache_source_index')) {
      final cached = json['_cache_source_index'];
      if (cached is! int || cached < 0) throw const FormatException('Invalid cached summary coordinate');
      sourceIndex = cached;
    }
    final generated = wire.GeneratedActionItem.fromJson(json);
    return ActionItem(
      generated.description,
      completed: generated.completed,
      deleted: json['deleted'] ?? false,
      sourceIndex: sourceIndex,
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
