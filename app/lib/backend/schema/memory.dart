enum MemoryCategory { system, interesting, manual }

enum MemoryVisibility { private, public }

// Maps legacy category strings to new categories
MemoryCategory _parseMemoryCategory(String? category) {
  if (category == null) return MemoryCategory.system;
  if (category == 'manual') return MemoryCategory.manual;
  if (category == 'interesting') return MemoryCategory.interesting;
  if (category == 'system') return MemoryCategory.system;
  // Legacy categories map to system (facts about user)
  if (['core', 'hobbies', 'lifestyle', 'interests', 'work', 'skills', 'habits', 'other'].contains(category)) {
    return MemoryCategory.system;
  }
  // 'learnings' and 'auto' map to system as well
  return MemoryCategory.system;
}

class Memory {
  String id;
  String uid;
  String content;
  MemoryCategory category;
  DateTime createdAt;
  DateTime updatedAt;
  String? conversationId;
  bool reviewed;
  bool? userReview;
  bool manuallyAdded;
  bool edited;
  bool deleted;
  MemoryVisibility visibility;
  bool isLocked;

  Memory({
    required this.id,
    required this.uid,
    required this.content,
    required this.category,
    required this.createdAt,
    required this.updatedAt,
    this.conversationId,
    this.reviewed = false,
    this.userReview,
    this.manuallyAdded = false,
    this.edited = false,
    this.deleted = false,
    required this.visibility,
    this.isLocked = false,
  });

  factory Memory.fromJson(Map<String, dynamic> json) {
    return Memory(
      id: json['id'],
      uid: json['uid'],
      content: json['content'],
      category: _parseMemoryCategory(json['category']),
      createdAt: DateTime.parse(json['created_at']).toLocal(),
      updatedAt: DateTime.parse(json['updated_at']).toLocal(),
      conversationId: json['conversation_id'],
      reviewed: json['reviewed'] ?? false,
      userReview: json['user_review'],
      manuallyAdded: json['manually_added'] ?? false,
      edited: json['edited'] ?? false,
      deleted: json['deleted'] ?? false,
      visibility: json['visibility'] != null
          ? (MemoryVisibility.values.asNameMap()[json['visibility']] ?? MemoryVisibility.public)
          : MemoryVisibility.public,
      isLocked: json['is_locked'] ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'uid': uid,
      'content': content,
      'category': category.toString().split('.').last,
      'created_at': createdAt.toUtc().toIso8601String(),
      'updated_at': updatedAt.toUtc().toIso8601String(),
      'memory_id': conversationId,
      'conversation_id': conversationId,
      'reviewed': reviewed,
      'user_review': userReview,
      'manually_added': manuallyAdded,
      'edited': edited,
      'deleted': deleted,
      'visibility': visibility.name,
      'is_locked': isLocked,
    };
  }
}
