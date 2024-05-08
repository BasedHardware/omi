import 'dart:core';

class SearchResult {
  SearchResult({required this.id, required this.text, required this.score});

  final String id;
  final String text;
  final double score;

  // Optional: If you need to serialize/deserialize to/from JSON
  factory SearchResult.fromJson(Map<String, dynamic> json) {
    return SearchResult(
      id: json['id'],
      text: json['text'],
      score: json['score'].toDouble(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'text': text,
      'score': score,
    };
  }
}
