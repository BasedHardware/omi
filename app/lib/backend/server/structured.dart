import 'package:enum_to_string/enum_to_string.dart';

enum CategoryEnum {
  personal,
  education,
  health,
  finance,
  legal,
  philosophy,
  spiritual,
  science,
  entrepreneurship,
  parenting,
  romantic,
  travel,
  inspiration,
  technology,
  business,
  social,
  work,
  other
}

class ActionItem {
  final String description;
  bool completed;

  ActionItem({
    required this.description,
    this.completed = false,
  });

  factory ActionItem.fromJson(Map<String, dynamic> json) {
    return ActionItem(
      description: json['description'],
      completed: json['completed'] ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'description': description,
      'completed': completed,
    };
  }
}

class Event {
  final String title;
  final String description;
  final DateTime start;
  final int duration;
  final bool created;

  Event({
    required this.title,
    this.description = '',
    required this.start,
    this.duration = 30,
    this.created = false,
  });

  factory Event.fromJson(Map<String, dynamic> json) {
    return Event(
      title: json['title'],
      description: json['description'] ?? '',
      start: DateTime.parse(json['start']),
      duration: json['duration'] ?? 30,
      created: json['created'] ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'title': title,
      'description': description,
      'start': start.toIso8601String(),
      'duration': duration,
      'created': created,
    };
  }
}

class Structured {
  final String title;
  final String overview;
  final String? emoji;
  final CategoryEnum category;
  final List<ActionItem> actionItems;
  final List<Event> events;

  Structured({
    this.title = '',
    this.overview = '',
    this.emoji = '🧠',
    this.category = CategoryEnum.other,
    this.actionItems = const [],
    this.events = const [],
  });

  factory Structured.fromJson(Map<String, dynamic> json) {
    return Structured(
      title: json['title'] ?? '',
      overview: json['overview'] ?? '',
      emoji: json['emoji'],
      category: EnumToString.fromString(CategoryEnum.values, json['category']) ?? CategoryEnum.other,
      actionItems: (json['action_items'] as List<dynamic>?)?.map((item) => ActionItem.fromJson(item)).toList() ?? [],
      events: (json['events'] as List<dynamic>?)?.map((event) => Event.fromJson(event)).toList() ?? [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'title': title,
      'overview': overview,
      'emoji': emoji,
      'category': EnumToString.convertToString(category),
      'action_items': actionItems.map((item) => item.toJson()).toList(),
      'events': events.map((event) => event.toJson()).toList(),
    };
  }

}
