import 'dart:convert';

enum GenUiCardType { locationRequest, locationResult, info }

enum GenUiActionType { shareLocation, openMap, openUrl }

double? _parseCoordinate(dynamic value) {
  if (value is num) {
    return value.toDouble();
  }
  if (value is String) {
    return double.tryParse(value);
  }
  return null;
}

class GenUiAction {
  final String label;
  final GenUiActionType type;
  final String? url;

  const GenUiAction({required this.label, required this.type, this.url});

  factory GenUiAction.fromJson(Map<String, dynamic> json) {
    final rawType = (json['type'] ?? '').toString();
    final type = switch (rawType) {
      'share_location' => GenUiActionType.shareLocation,
      'open_map' => GenUiActionType.openMap,
      'open_url' => GenUiActionType.openUrl,
      _ => GenUiActionType.openUrl,
    };

    return GenUiAction(label: (json['label'] ?? 'Open').toString(), type: type, url: json['url']?.toString());
  }
}

class GenUiMessageCard {
  final GenUiCardType type;
  final String title;
  final String? description;
  final double? latitude;
  final double? longitude;
  final List<GenUiAction> actions;

  const GenUiMessageCard({
    required this.type,
    required this.title,
    this.description,
    this.latitude,
    this.longitude,
    this.actions = const [],
  });

  factory GenUiMessageCard.fromJson(Map<String, dynamic> json) {
    final rawType = (json['type'] ?? '').toString();
    final type = switch (rawType) {
      'location_request' => GenUiCardType.locationRequest,
      'location_result' => GenUiCardType.locationResult,
      _ => GenUiCardType.info,
    };

    final location = json['location'] is Map ? Map<String, dynamic>.from(json['location'] as Map) : null;
    final latitude = _parseCoordinate(json['latitude'] ?? json['lat'] ?? location?['latitude'] ?? location?['lat']);
    final longitude =
        _parseCoordinate(json['longitude'] ?? json['lng'] ?? json['lon'] ?? location?['longitude'] ?? location?['lng']);

    final actions = ((json['actions'] ?? const <dynamic>[]) as List<dynamic>)
        .whereType<Map>()
        .map((action) => GenUiAction.fromJson(Map<String, dynamic>.from(action)))
        .toList();

    if (actions.isEmpty) {
      switch (type) {
        case GenUiCardType.locationRequest:
          actions.add(const GenUiAction(label: 'Share location', type: GenUiActionType.shareLocation));
          break;
        case GenUiCardType.locationResult:
          if (latitude != null && longitude != null) {
            actions.add(const GenUiAction(label: 'Open map', type: GenUiActionType.openMap));
          }
          break;
        case GenUiCardType.info:
          break;
      }
    }

    return GenUiMessageCard(
      type: type,
      title: (json['title'] ??
              switch (type) {
                GenUiCardType.locationRequest => 'Share your location',
                GenUiCardType.locationResult => 'Location',
                GenUiCardType.info => 'Details',
              })
          .toString(),
      description: json['description']?.toString(),
      latitude: latitude,
      longitude: longitude,
      actions: actions,
    );
  }
}

class ParsedGenUiMessage {
  final String markdownText;
  final GenUiMessageCard? card;

  const ParsedGenUiMessage({required this.markdownText, this.card});
}

ParsedGenUiMessage parseGenUiMessage(String rawMessage) {
  final trimmed = rawMessage.trim();
  final fence = RegExp(r'```genui\s*([\s\S]*?)```', caseSensitive: false);
  final match = fence.firstMatch(trimmed);

  if (match == null) {
    return ParsedGenUiMessage(markdownText: rawMessage);
  }

  final jsonPayload = match.group(1)?.trim();
  if (jsonPayload == null || jsonPayload.isEmpty) {
    return ParsedGenUiMessage(markdownText: rawMessage);
  }

  try {
    final decoded = jsonDecode(jsonPayload);
    if (decoded is! Map) {
      return ParsedGenUiMessage(markdownText: rawMessage);
    }

    final remainingText = trimmed.replaceFirst(match.group(0)!, '').trim();
    return ParsedGenUiMessage(markdownText: remainingText, card: GenUiMessageCard.fromJson(Map<String, dynamic>.from(decoded)));
  } catch (_) {
    return ParsedGenUiMessage(markdownText: rawMessage);
  }
}
