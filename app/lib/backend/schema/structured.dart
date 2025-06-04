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
          (event['startsAt'] ?? event['start']) is int
              ? DateTime.fromMillisecondsSinceEpoch((event['startsAt'] ?? event['start']) * 1000).toLocal()
              : DateTime.parse(event['startsAt'] ?? event['start']).toLocal(),
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

  toJson() => {'appId': appId, 'content': content};

  factory AppResponse.fromJson(Map<String, dynamic> json) {
    return AppResponse(json['content'], appId: json['appId'] ?? json['app_id']);
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

class ConversationPhoto {
  int id = 0;

  String? photoId;  // Cloud storage photo ID
  String? base64;   // Legacy base64 data - optional for cloud photos
  String description;
  String? thumbnailUrl;  // Cloud storage thumbnail URL
  String? url;           // Cloud storage full-size URL
  String? createdAt;     // When photo was taken/added
  String? addedAt;       // When photo was added to conversation

  ConversationPhoto(this.description, {
    this.id = 0, 
    this.photoId, 
    this.base64, 
    this.thumbnailUrl, 
    this.url, 
    this.createdAt, 
    this.addedAt
  });

  factory ConversationPhoto.fromJson(Map<String, dynamic> json) {
    return ConversationPhoto(
      json['description'] ?? '',
      id: json['id'] is int ? json['id'] : 0,
      photoId: json['photo_id'] as String? ?? json['id'] as String?,
      base64: json['base64'] as String?,
      thumbnailUrl: json['thumbnail_url'] as String?,
      url: json['url'] as String?,
      createdAt: json['created_at'] as String?,
      addedAt: json['added_at'] as String?,
    );
  }

  toJson() {
    return {
      'id': id,
      'photo_id': photoId,
      'base64': base64,
      'description': description,
      'thumbnail_url': thumbnailUrl,
      'url': url,
      'created_at': createdAt,
      'added_at': addedAt,
    };
  }

  // Helper method to get createdAt as DateTime
  DateTime get createdAtDateTime {
    if (createdAt != null) {
      try {
        return DateTime.parse(createdAt!);
      } catch (e) {
        // Fallback to current time if parsing fails
        return DateTime.now();
      }
    }
    return DateTime.now();
  }

  // Helper method to get the best display URL (thumbnail first, then full URL)
  String? getDisplayUrl() {
    // Prefer thumbnail URL for display, fallback to full URL
    if (thumbnailUrl != null && thumbnailUrl!.isNotEmpty) {
      return thumbnailUrl;
    }
    if (url != null && url!.isNotEmpty) {
      return url;
    }
    return null;
  }

  // Helper method to get full-size URL - prefer full URL, fallback to thumbnail, then base64
  String? getFullUrl() {
    if (url != null && url!.isNotEmpty) {
      return url;
    }
    if (thumbnailUrl != null && thumbnailUrl!.isNotEmpty) {
      return thumbnailUrl;
    }
    if (base64 != null && base64!.isNotEmpty) {
      return 'data:image/jpeg;base64,$base64';
    }
    return null;
  }

  // Helper method to check if photo has any displayable content
  bool hasDisplayableContent() {
    return (thumbnailUrl != null && thumbnailUrl!.isNotEmpty) ||
           (url != null && url!.isNotEmpty) ||
           (base64 != null && base64!.isNotEmpty);
  }
}
