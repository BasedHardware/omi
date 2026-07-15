// Phase 4.1 SKIPPED — has custom behavior, so not typedef'd here.
// Person.fromGenerated derives colorIdx from id.hashCode, throws FormatException on
// missing created_at/updated_at, defaults speechSamplesVersion to 3, and toJson injects
// color_idx. None of that survives a plain typedef; this file needs manual care.

import 'package:flutter/material.dart';
import 'package:omi/backend/schema/gen/people_wire.g.dart' as wire;

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
  final List<String>? speechSampleTranscripts;
  final int speechSamplesVersion;
  final int? colorIdx;

  Person({
    required this.id,
    required this.name,
    required this.createdAt,
    required this.updatedAt,
    this.speechSamples,
    this.speechSampleTranscripts,
    this.speechSamplesVersion = 1,
    this.colorIdx,
  });

  factory Person.fromJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedPerson.fromJson(json);
    return Person.fromGenerated(generated, colorIdx: json['color_idx'] as int?);
  }

  factory Person.fromGenerated(wire.GeneratedPerson generated, {int? colorIdx}) {
    final createdAt = generated.createdAt;
    final updatedAt = generated.updatedAt;
    if (createdAt == null) {
      throw const FormatException('Missing required field: created_at');
    }
    if (updatedAt == null) {
      throw const FormatException('Missing required field: updated_at');
    }
    return Person(
      id: generated.id,
      name: generated.name,
      createdAt: createdAt,
      updatedAt: updatedAt,
      speechSamples: generated.speechSamples,
      speechSampleTranscripts: generated.speechSampleTranscripts,
      speechSamplesVersion: generated.speechSamplesVersion,
      colorIdx: colorIdx ?? generated.id.hashCode % speakerColors.length,
    );
  }

  wire.GeneratedPerson toGenerated() {
    return wire.GeneratedPerson(
      id: id,
      name: name,
      createdAt: createdAt,
      updatedAt: updatedAt,
      speechSamples: speechSamples ?? const [],
      speechSampleTranscripts: speechSampleTranscripts,
      speechSamplesVersion: speechSamplesVersion,
    );
  }

  Map<String, dynamic> toJson() {
    return {...toGenerated().toJson(), 'color_idx': colorIdx};
  }
}
