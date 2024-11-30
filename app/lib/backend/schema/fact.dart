enum FactCategory { hobbies, lifestyle, interests, habits, work, skills, other }

class Fact {
  String id;
  String uid;
  String content;
  FactCategory category;
  DateTime createdAt;
  DateTime updatedAt;
  String? conversationId;
  String? conversationCategory;
  bool reviewed;
  bool? userReview;
  bool manuallyAdded;
  bool edited;
  bool deleted;

  Fact({
    required this.id,
    required this.uid,
    required this.content,
    required this.category,
    required this.createdAt,
    required this.updatedAt,
    this.conversationId,
    this.conversationCategory,
    this.reviewed = false,
    this.userReview,
    this.manuallyAdded = false,
    this.edited = false,
    this.deleted = false,
  });

  factory Fact.fromJson(Map<String, dynamic> json) {
    return Fact(
      id: json['id'],
      uid: json['uid'],
      content: json['content'],
      category: FactCategory.values.firstWhere((e) => e.toString() == 'FactCategory.${json['category']}'),
      createdAt: DateTime.parse(json['created_at']).toLocal(),
      updatedAt: DateTime.parse(json['updated_at']).toLocal(),
      conversationId: json['memory_id'],
      conversationCategory: json['memory_category'],
      reviewed: json['reviewed'],
      userReview: json['user_review'],
      manuallyAdded: json['manually_added'],
      edited: json['edited'],
      deleted: json['deleted'],
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
      'memory_category': conversationCategory.toString().split('.').last,
      'reviewed': reviewed,
      'user_review': userReview,
      'manually_added': manuallyAdded,
      'edited': edited,
      'deleted': deleted,
    };
  }
}
