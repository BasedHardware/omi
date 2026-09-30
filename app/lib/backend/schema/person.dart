// Phase 4.1 SKIPPED — has custom behavior, so not typedef'd here.
// Person.fromGenerated derives colorIdx from id.hashCode, throws FormatException on
// missing created_at/updated_at, defaults speechSamplesVersion to 3, and toJson injects
// color_idx. None of that survives a plain typedef; this file needs manual care.

import 'package:flutter/material.dart';

import 'package:collection/collection.dart';

import 'package:omi/backend/schema/gen/people_wire.g.dart' as wire;

final List<Color> speakerColors = [
  const Color(0xFF2D3748), // Dark gray-blue
  const Color(0xFF1E3A5F), // Deep blue
  const Color(0xFF2D4A3E), // Forest green
  const Color(0xFF4A3728), // Brown
  const Color(0xFF3D2E4A), // Purple
  const Color(0xFF4A3A2D), // Tan
  const Color(0xFF2E3D4A), // Steel blue
  const Color(0xFF3A2D2D), // Maroon
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
  final String voiceReadiness;

  /// Stats over the newest conversations; null until the list is loaded with `includeStats`.
  final int? conversationCount;
  final DateTime? lastHeardAt;
  final double? talkSeconds;

  /// Conversations where every label for this person was automatic (stats only).
  final int? autoConversationCount;

  /// Kept out of bulk clean-up and expected in conversations.
  final bool pinned;
  final DateTime? pinnedAt;

  /// `confirmed`, `likely` or `unverified`, derived by the server from what the user did.
  final String confidence;
  final List<wire.GeneratedPersonConfidenceReason> confidenceReasons;

  /// Hand labels still needed to reach Confirmed; null when Confirmed or only a voice sample is missing.
  final int? labelsToConfirm;
  final DateTime? lastLabeledAt;

  Person({
    required this.id,
    required this.name,
    required this.createdAt,
    required this.updatedAt,
    this.speechSamples,
    this.speechSampleTranscripts,
    this.speechSamplesVersion = 1,
    this.colorIdx,
    this.voiceReadiness = 'unknown',
    this.conversationCount,
    this.lastHeardAt,
    this.talkSeconds,
    this.autoConversationCount,
    this.pinned = false,
    this.pinnedAt,
    this.confidence = 'unverified',
    this.confidenceReasons = const [],
    this.labelsToConfirm,
    this.lastLabeledAt,
  });

  Person copyWith({
    String? name,
    DateTime? updatedAt,
    List<String>? speechSamples,
    bool? pinned,
    DateTime? Function()? pinnedAt,
  }) {
    return Person(
      id: id,
      name: name ?? this.name,
      createdAt: createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      speechSamples: speechSamples ?? this.speechSamples,
      speechSampleTranscripts: speechSampleTranscripts,
      speechSamplesVersion: speechSamplesVersion,
      colorIdx: colorIdx,
      voiceReadiness: voiceReadiness,
      conversationCount: conversationCount,
      lastHeardAt: lastHeardAt,
      talkSeconds: talkSeconds,
      autoConversationCount: autoConversationCount,
      pinned: pinned ?? this.pinned,
      pinnedAt: pinnedAt != null ? pinnedAt() : this.pinnedAt,
      confidence: confidence,
      confidenceReasons: confidenceReasons,
      labelsToConfirm: labelsToConfirm,
      lastLabeledAt: lastLabeledAt,
    );
  }

  /// How many of a confidence reason, or 0 when absent.
  int reasonCount(String code) => confidenceReasons.firstWhereOrNull((r) => r.code == code)?.count ?? 0;

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
      voiceReadiness: generated.voiceReadiness,
      conversationCount: generated.conversationCount,
      lastHeardAt: generated.lastHeardAt,
      talkSeconds: generated.talkSeconds,
      autoConversationCount: generated.autoConversationCount,
      pinned: generated.pinned,
      pinnedAt: generated.pinnedAt,
      confidence: generated.confidence,
      confidenceReasons: generated.confidenceReasons,
      labelsToConfirm: generated.labelsToConfirm,
      lastLabeledAt: generated.lastLabeledAt,
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
      voiceReadiness: voiceReadiness,
      conversationCount: conversationCount,
      lastHeardAt: lastHeardAt,
      talkSeconds: talkSeconds,
      autoConversationCount: autoConversationCount,
      pinned: pinned,
      pinnedAt: pinnedAt,
      confidence: confidence,
      confidenceReasons: confidenceReasons,
      labelsToConfirm: labelsToConfirm,
      lastLabeledAt: lastLabeledAt,
    );
  }

  Map<String, dynamic> toJson() {
    return {...toGenerated().toJson(), 'color_idx': colorIdx};
  }
}
