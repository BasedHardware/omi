import 'package:flutter/material.dart';

final List<Color> speakerColors = [
  Color(0xFF2D3748), // Dark gray-blue
  Color(0xFF1E3A5F), // Deep blue
  Color(0xFF2D4A3E), // Forest green
  Color(0xFF4A3728), // Brown
  Color(0xFF3D2E4A), // Purple
  Color(0xFF4A3A2D), // Tan
  Color(0xFF2E3D4A), // Steel blue
  Color(0xFF3A2D2D), // Maroon
];

final List<String> speakerImagePath = [
  'assets/images/speaker_1_icon.png',
  // 'assets/images/speaker_1_red.png',
  // 'assets/images/speaker_1_blue.png',
  // 'assets/images/speaker_1_green.png',
  // 'assets/images/speaker_1_yellow.png',
  // 'assets/images/speaker_1_purple.png',
  // 'assets/images/speaker_1_orange.png',
  // 'assets/images/speaker_1_pink.png',
  // 'assets/images/speaker_1_teal.png',
  // 'assets/images/speaker_1_cyan.png',
  // 'assets/images/speaker_1_amber.png',
];

class Person {
  final String id;
  final String name;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<String>? speechSamples;
  final int? colorIdx;

  Person({
    required this.id,
    required this.name,
    required this.createdAt,
    required this.updatedAt,
    this.speechSamples,
    this.colorIdx,
  });

  factory Person.fromJson(Map<String, dynamic> json) {
    return Person(
      id: json['id'],
      name: json['name'],
      createdAt: DateTime.parse(json['created_at']).toLocal(),
      updatedAt: DateTime.parse(json['updated_at']).toLocal(),
      speechSamples: json['speech_samples'] != null ? List<String>.from(json['speech_samples']) : [],
      colorIdx: json['color_idx'] ?? json['id'].hashCode % speakerColors.length,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'created_at': createdAt.toUtc().toIso8601String(),
      'updated_at': updatedAt.toUtc().toIso8601String(),
      'speech_samples': speechSamples ?? [],
      'color_idx': colorIdx,
    };
  }
}
