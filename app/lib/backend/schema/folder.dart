// Phase 4.1 SKIPPED — has copyWith + computed accessors, so not typedef'd here.
// Folder exposes copyWith(), a computed colorValue getter, and a custom toString();
// per the refactor rules, files with copyWith need manual care and are excluded.

import 'package:flutter/material.dart';

import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as wire;

class Folder {
  final String id;
  final String name;
  final String? description;
  final String color;
  final String icon;
  final DateTime createdAt;
  final DateTime updatedAt;
  final int order;
  final bool isDefault;
  final bool isSystem;
  final String? categoryMapping;
  final int conversationCount;

  Folder({
    required this.id,
    required this.name,
    this.description,
    required this.color,
    required this.icon,
    required this.createdAt,
    required this.updatedAt,
    required this.order,
    required this.isDefault,
    required this.isSystem,
    this.categoryMapping,
    required this.conversationCount,
  });

  factory Folder.fromJson(Map<String, dynamic> json) {
    return Folder.fromGenerated(wire.GeneratedFolder.fromJson(json));
  }

  factory Folder.fromGenerated(wire.GeneratedFolder generated) {
    return Folder(
      id: generated.id,
      name: generated.name,
      description: generated.description,
      color: generated.color,
      icon: generated.icon,
      createdAt: generated.createdAt,
      updatedAt: generated.updatedAt,
      order: generated.order,
      isDefault: generated.isDefault,
      isSystem: generated.isSystem,
      categoryMapping: generated.categoryMapping,
      conversationCount: generated.conversationCount,
    );
  }

  wire.GeneratedFolder toGenerated() {
    return wire.GeneratedFolder(
      id: id,
      name: name,
      description: description,
      color: color,
      icon: icon,
      createdAt: createdAt,
      updatedAt: updatedAt,
      order: order,
      isDefault: isDefault,
      isSystem: isSystem,
      categoryMapping: categoryMapping,
      conversationCount: conversationCount,
    );
  }

  Map<String, dynamic> toJson() {
    return toGenerated().toJson();
  }

  Color get colorValue {
    try {
      final hex = color.replaceFirst('#', '');
      return Color(int.parse('FF$hex', radix: 16));
    } catch (e) {
      return const Color(0xFF6B7280);
    }
  }

  @override
  String toString() => 'Folder(id: $id, name: $name, count: $conversationCount)';

  Folder copyWith({
    String? id,
    String? name,
    String? description,
    String? color,
    String? icon,
    DateTime? createdAt,
    DateTime? updatedAt,
    int? order,
    bool? isDefault,
    bool? isSystem,
    String? categoryMapping,
    int? conversationCount,
  }) {
    return Folder(
      id: id ?? this.id,
      name: name ?? this.name,
      description: description ?? this.description,
      color: color ?? this.color,
      icon: icon ?? this.icon,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      order: order ?? this.order,
      isDefault: isDefault ?? this.isDefault,
      isSystem: isSystem ?? this.isSystem,
      categoryMapping: categoryMapping ?? this.categoryMapping,
      conversationCount: conversationCount ?? this.conversationCount,
    );
  }
}
