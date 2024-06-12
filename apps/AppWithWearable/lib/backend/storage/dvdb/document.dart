import 'dart:math';
import 'dart:typed_data';
import 'package:uuid/uuid.dart';

class Document {
  Document({String? id, required this.text, required this.embedding, Map<String, String>? metadata})
      : id = id ?? _generateUuid(),
        magnitude = _calculateMagnitude(embedding),
        metadata = metadata ?? <String, String>{};

  final String id;
  final String text;
  final Float64List embedding;
  final double magnitude;
  final Map<String, String> metadata;

  static String _generateUuid() {
    return const Uuid().v1();
  }

  static double _calculateMagnitude(Float64List embedding) {
    return sqrt(embedding.fold(0, (num sum, double element) => sum + element * element));
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'text': text,
      'embedding': embedding,
      'magnitude': magnitude,
      'metadata': metadata,
    };
  }

  factory Document.fromJson(Map<String, dynamic> json) {
    return Document(
        id: json['id'],
        text: json['text'],
        embedding: Float64List.fromList(json['embedding'].cast<double>()),
        metadata: Map<String, String>.from(json['metadata'])
    );
  }
}