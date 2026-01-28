import 'package:equatable/equatable.dart';

class Task extends Equatable {
  final String id;
  final String title;
  final String? description;
  final bool completed;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? dueDate;
  final String? parentId;
  final int? depth;
  final int? order;
  final List<String>? subtaskIds;

  const Task({
    required this.id,
    required this.title,
    this.description,
    this.completed = false,
    this.createdAt,
    this.updatedAt,
    this.dueDate,
    this.parentId,
    this.depth,
    this.order,
    this.subtaskIds,
  });

  bool get hasSubtasks => subtaskIds?.isNotEmpty == true;

  Task copyWith({
    String? id,
    String? title,
    String? description,
    bool? completed,
    DateTime? createdAt,
    DateTime? updatedAt,
    DateTime? dueDate,
    String? parentId,
    int? depth,
    int? order,
    List<String>? subtaskIds,
  }) {
    return Task(
      id: id ?? this.id,
      title: title ?? this.title,
      description: description ?? this.description,
      completed: completed ?? this.completed,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      dueDate: dueDate ?? this.dueDate,
      parentId: parentId ?? this.parentId,
      depth: depth ?? this.depth,
      order: order ?? this.order,
      subtaskIds: subtaskIds ?? this.subtaskIds,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'description': description,
      'completed': completed,
      'createdAt': createdAt?.toIso8601String(),
      'updatedAt': updatedAt?.toIso8601String(),
      'dueDate': dueDate?.toIso8601String(),
      'parentId': parentId,
      'depth': depth,
      'order': order,
      'subtaskIds': subtaskIds,
    };
  }

  factory Task.fromJson(Map<String, dynamic> json) {
    return Task(
      id: json['id'],
      title: json['title'],
      description: json['description'],
      completed: json['completed'] ?? false,
      createdAt: json['createdAt'] != null 
        ? DateTime.parse(json['createdAt']) 
        : null,
      updatedAt: json['updatedAt'] != null 
        ? DateTime.parse(json['updatedAt']) 
        : null,
      dueDate: json['dueDate'] != null 
        ? DateTime.parse(json['dueDate']) 
        : null,
      parentId: json['parentId'],
      depth: json['depth'],
      order: json['order'],
      subtaskIds: json['subtaskIds']?.cast<String>(),
    );
  }

  @override
  List<Object?> get props => [
        id,
        title,
        description,
        completed,
        createdAt,
        updatedAt,
        dueDate,
        parentId,
        depth,
        order,
        subtaskIds,
      ];
}
