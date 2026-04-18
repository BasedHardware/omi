import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';


class GenUIMessage {
  final String type;
  final String component;
  final String message;
  final List<String>? actions;
  final GenUILocation? location;
  final String? title;
  final String? description;
  final String? distance;

  GenUIMessage({
    required this.type,
    required this.component,
    required this.message,
    this.actions,
    this.location,
    this.title,
    this.description,
    this.distance,
  });

  factory GenUIMessage.fromJson(Map<String, dynamic> json) {
    return GenUIMessage(
      type: json['type'] ?? '',
      component: json['component'] ?? '',
      message: json['message'] ?? '',
      actions: json['actions'] != null 
          ? List<String>.from(json['actions']) 
          : null,
      location: json['location'] != null 
          ? GenUILocation.fromJson(json['location']) 
          : null,
      title: json['title'],
      description: json['description'],
      distance: json['distance'],
    );
  }

  /// Strip markdown code fences (```json ... ``` or ``` ... ```) if present.
  static String _stripFences(String text) {
    final trimmed = text.trim();
    final fencePattern = RegExp(r'^```(?:json)?\s*\n?(.*?)\n?\s*```$', dotAll: true);
    final match = fencePattern.firstMatch(trimmed);
    if (match != null) {
      return match.group(1)?.trim() ?? trimmed;
    }
    return trimmed;
  }

  static bool isGenUIMessage(String text) {
    try {
      final trimmed = _stripFences(text);
      if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) {
        return false;
      }
      final json = jsonDecode(trimmed);
      return json is Map && json['type'] == 'genui';
    } catch (_) {
      return false;
    }
  }

  static GenUIMessage? tryParse(String text) {
    try {
      final stripped = _stripFences(text);
      if (!isGenUIMessage(stripped)) return null;
      final json = jsonDecode(stripped.trim());
      return GenUIMessage.fromJson(json);
    } catch (_) {
      return null;
    }
  }
}

class GenUILocation {
  final double lat;
  final double lng;
  final String? label;

  GenUILocation({
    required this.lat,
    required this.lng,
    this.label,
  });

  factory GenUILocation.fromJson(Map<String, dynamic> json) {
    return GenUILocation(
      lat: (json['lat'] ?? 0).toDouble(),
      lng: (json['lng'] ?? 0).toDouble(),
      label: json['label'],
    );
  }
}

class LocationSharePrompt extends StatelessWidget {
  final String message;
  final List<String> actions;
  final Function(String) onAction;

  const LocationSharePrompt({
    super.key,
    required this.message,
    required this.actions,
    required this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.location_on, color: Colors.blue, size: 24),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  message,
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: actions.map((action) {
              final isYes = action.toLowerCase() == 'yes';
              return Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: ElevatedButton(
                    onPressed: () => onAction(action),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: isYes ? Colors.blue : const Color(0xFF2C2C2E),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: Text(
                      action == 'yes' ? 'Yes' : (action == 'no' ? 'No' : action),
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

class MapCard extends StatelessWidget {
  final String? message;
  final GenUILocation location;

  const MapCard({
    super.key,
    this.message,
    required this.location,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
            child: SizedBox(
              height: 150,
              child: FlutterMap(
                options: MapOptions(
                  initialCenter: LatLng(location.lat, location.lng),
                  initialZoom: 15,
                  interactionOptions: const InteractionOptions(
                    flags: InteractiveFlag.none,
                  ),
                ),
                children: [
                  TileLayer(
                    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                    userAgentPackageName: 'com.friend.ios',
                  ),
                  MarkerLayer(
                    markers: [
                      Marker(
                        point: LatLng(location.lat, location.lng),
                        width: 40,
                        height: 40,
                        child: const Icon(
                          Icons.location_pin,
                          color: Colors.red,
                          size: 40,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          if (message != null || location.label != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (location.label != null)
                    Row(
                      children: [
                        const Icon(Icons.place, color: Colors.blue, size: 18),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            location.label!,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ),
                  if (message != null) ...[
                    if (location.label != null) const SizedBox(height: 8),
                    Text(
                      message!,
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class ResultCard extends StatelessWidget {
  final String title;
  final String? description;
  final String? distance;
  final GenUILocation? location;
  final Function(String)? onAction;
  final List<String>? actions;

  const ResultCard({
    super.key,
    required this.title,
    this.description,
    this.distance,
    this.location,
    this.onAction,
    this.actions,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (title.isNotEmpty)
            Text(
              title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
          if (description != null) ...[
            if (title.isNotEmpty) const SizedBox(height: 8),
            Text(
              description!,
              style: TextStyle(
                color: Colors.grey.shade400,
                fontSize: 14,
              ),
            ),
          ],
          if (distance != null) ...[
            const SizedBox(height: 8),
            Row(
              children: [
                const Icon(Icons.directions_walk, color: Colors.blue, size: 16),
                const SizedBox(width: 4),
                Text(
                  distance!,
                  style: const TextStyle(color: Colors.blue, fontSize: 14),
                ),
              ],
            ),
          ],
          if (location != null) ...[
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: SizedBox(
                height: 100,
                child: FlutterMap(
                  options: MapOptions(
                    initialCenter: LatLng(location!.lat, location!.lng),
                    initialZoom: 15,
                    interactionOptions: const InteractionOptions(
                      flags: InteractiveFlag.none,
                    ),
                  ),
                  children: [
                    TileLayer(
                      urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                      userAgentPackageName: 'com.friend.ios',
                    ),
                    MarkerLayer(
                      markers: [
                        Marker(
                          point: LatLng(location!.lat, location!.lng),
                          width: 30,
                          height: 30,
                          child: const Icon(
                            Icons.location_pin,
                            color: Colors.red,
                            size: 30,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
          if (actions != null && actions!.isNotEmpty) ...[
            const SizedBox(height: 12),
            Row(
              children: actions!.map((action) {
                final isPrimary = action.toLowerCase() == 'yes' || action.toLowerCase() == 'confirm';
                return Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: ElevatedButton(
                      onPressed: () => onAction?.call(action),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: isPrimary ? Colors.blue : const Color(0xFF2C2C2E),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 10),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      child: Text(
                        action == 'yes' ? 'Yes' : (action == 'no' ? 'No' : action),
                        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
          ],
        ],
      ),
    );
  }
}

class ConfirmPrompt extends StatelessWidget {
  final String message;
  final List<String> actions;
  final Function(String) onAction;

  const ConfirmPrompt({
    super.key,
    required this.message,
    required this.actions,
    required this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.help_outline, color: Colors.orange, size: 24),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  message,
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: actions.map((action) {
              final isPrimary = action.toLowerCase() == 'yes' || action.toLowerCase() == 'confirm';
              return Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: ElevatedButton(
                    onPressed: () => onAction(action),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: isPrimary ? Colors.blue : const Color(0xFF2C2C2E),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: Text(
                      action == 'yes' ? 'Yes' : (action == 'no' ? 'No' : action),
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}