class PluginReview {
  String uid;
  DateTime ratedAt;
  double score;
  String review;

  PluginReview({
    required this.uid,
    required this.ratedAt,
    required this.score,
    required this.review,
  });

  factory PluginReview.fromJson(Map<String, dynamic> json) {
    return PluginReview(
      uid: json['uid'],
      ratedAt: DateTime.parse(json['rated_at']),
      score: json['score'],
      review: json['review'],
    );
  }

  toJson() {
    return {
      'uid': uid,
      'rated_at': ratedAt.toIso8601String(),
      'score': score,
      'review': review,
    };
  }

  static List<PluginReview> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => PluginReview.fromJson(e)).toList();
  }
}

class Plugin {
  String id;
  String name;
  String author;
  String description;
  String prompt;
  bool isEnabled = false;
  String image;

  List<PluginReview> reviews;
  PluginReview? userReview;
  double? ratingAvg;
  int ratingCount;

  Plugin({
    required this.id,
    required this.name,
    required this.author,
    required this.description,
    required this.prompt,
    required this.image,
    this.reviews = const [],
    this.userReview,
    this.ratingAvg,
    required this.ratingCount,
  });

  factory Plugin.fromJson(Map<String, dynamic> json) {
    return Plugin(
      id: json['id'],
      name: json['name'],
      author: json['author'],
      description: json['description'],
      prompt: json['prompt'],
      image: json['image'],
      reviews: PluginReview.fromJsonList(json['reviews'] ?? []),
      userReview: json['user_review'] != null ? PluginReview.fromJson(json['user_review']) : null,
      ratingAvg: json['rating_avg'],
      ratingCount: json['rating_count'] ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'author': author,
      'description': description,
      'prompt': prompt,
      'image': image,
      'reviews': reviews.map((e) => e.toJson()).toList(),
      'rating_avg': ratingAvg,
      'user_review': userReview?.toJson(),
      'rating_count': ratingCount,
    };
  }

  static List<Plugin> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => Plugin.fromJson(e)).toList();
  }
}
