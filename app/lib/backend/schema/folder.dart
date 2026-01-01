import 'package:flutter/material.dart';

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
    return Folder(
      id: json['id'] ?? '',
      name: json['name'] ?? '',
      description: json['description'],
      color: json['color'] ?? '#6B7280',
      icon: json['icon'] ?? '📁',
      createdAt: json['created_at'] != null ? DateTime.parse(json['created_at']) : DateTime.now(),
      updatedAt: json['updated_at'] != null ? DateTime.parse(json['updated_at']) : DateTime.now(),
      order: json['order'] ?? 0,
      isDefault: json['is_default'] ?? false,
      isSystem: json['is_system'] ?? false,
      categoryMapping: json['category_mapping'],
      conversationCount: json['conversation_count'] ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'description': description,
      'color': color,
      'icon': icon,
      'created_at': createdAt.toIso8601String(),
      'updated_at': updatedAt.toIso8601String(),
      'order': order,
      'is_default': isDefault,
      'is_system': isSystem,
      'category_mapping': categoryMapping,
      'conversation_count': conversationCount,
    };
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
