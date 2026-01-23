import 'dart:convert';

import 'package:collection/collection.dart';

enum GenUiNodeType {
  column,
  row,
  text,
  button,
  mapCard,
}

class GenUiAction {
  final String type;
  final Map<String, dynamic> payload;

  const GenUiAction({required this.type, required this.payload});

  factory GenUiAction.fromJson(Object? json) {
    if (json is String) {
      return GenUiAction(type: json, payload: const {});
    }

    if (json is Map<String, dynamic>) {
      final type = json['type']?.toString() ?? 'unknown';
      final payload = Map<String, dynamic>.from(json);
      payload.remove('type');
      return GenUiAction(type: type, payload: payload);
    }

    return const GenUiAction(type: 'unknown', payload: {});
  }
}

class GenUiMapCard {
  final String? title;
  final String? subtitle;
  final double? latitude;
  final double? longitude;
  final String? url;
  final String? actionLabel;

  const GenUiMapCard({
    this.title,
    this.subtitle,
    this.latitude,
    this.longitude,
    this.url,
    this.actionLabel,
  });

  factory GenUiMapCard.fromJson(Map<String, dynamic> json) {
    return GenUiMapCard(
      title: json['title']?.toString(),
      subtitle: json['subtitle']?.toString(),
      latitude: (json['latitude'] ?? json['lat']) is num ? (json['latitude'] ?? json['lat']).toDouble() : null,
      longitude: (json['longitude'] ?? json['lng']) is num ? (json['longitude'] ?? json['lng']).toDouble() : null,
      url: json['url']?.toString(),
      actionLabel: json['action_label']?.toString(),
    );
  }

  bool get hasCoordinates => latitude != null && longitude != null;
}

class GenUiNode {
  final GenUiNodeType type;
  final String? text;
  final GenUiAction? action;
  final List<GenUiNode> children;
  final GenUiMapCard? mapCard;

  const GenUiNode({
    required this.type,
    this.text,
    this.action,
    this.children = const [],
    this.mapCard,
  });

  static GenUiNode? fromJson(Map<String, dynamic> json) {
    final typeValue = json['type']?.toString();
    final type = _typeFromString(typeValue);
    if (type == null) {
      return null;
    }

    final childrenJson = json['children'];
    final children = childrenJson is List
        ? childrenJson
            .map((child) => child is Map<String, dynamic> ? GenUiNode.fromJson(child) : null)
            .whereNotNull()
            .toList()
        : <GenUiNode>[];

    switch (type) {
      case GenUiNodeType.column:
      case GenUiNodeType.row:
        return GenUiNode(type: type, children: children);
      case GenUiNodeType.text:
        return GenUiNode(
          type: type,
          text: json['text']?.toString() ?? json['value']?.toString(),
        );
      case GenUiNodeType.button:
        return GenUiNode(
          type: type,
          text: json['label']?.toString() ?? json['text']?.toString(),
          action: GenUiAction.fromJson(json['action']),
        );
      case GenUiNodeType.mapCard:
        return GenUiNode(
          type: type,
          mapCard: GenUiMapCard.fromJson(json),
          action: json['action'] != null ? GenUiAction.fromJson(json['action']) : null,
        );
    }
  }

  static GenUiNodeType? _typeFromString(String? value) {
    switch (value) {
      case 'column':
      case 'container':
        return GenUiNodeType.column;
      case 'row':
        return GenUiNodeType.row;
      case 'text':
        return GenUiNodeType.text;
      case 'button':
        return GenUiNodeType.button;
      case 'map':
      case 'map_card':
      case 'mapCard':
        return GenUiNodeType.mapCard;
    }
    return null;
  }
}

class GenUiPayload {
  final GenUiNode root;

  const GenUiPayload({required this.root});

  static GenUiPayload? tryParse(Object? value) {
    if (value == null) return null;

    if (value is String) {
      try {
        final decoded = jsonDecode(value);
        return tryParse(decoded);
      } catch (_) {
        return null;
      }
    }

    if (value is List) {
      final children = value
          .map((entry) => entry is Map<String, dynamic> ? GenUiNode.fromJson(entry) : null)
          .whereNotNull()
          .toList();
      if (children.isEmpty) return null;
      return GenUiPayload(root: GenUiNode(type: GenUiNodeType.column, children: children));
    }

    if (value is Map<String, dynamic>) {
      final rootValue = value['root'] ?? value;
      if (rootValue is Map<String, dynamic>) {
        final rootNode = GenUiNode.fromJson(rootValue);
        if (rootNode != null) {
          return GenUiPayload(root: rootNode);
        }
      }
    }

    return null;
  }
}
