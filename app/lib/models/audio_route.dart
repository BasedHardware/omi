enum AudioRouteType {
  iPhone,
  speaker,
  airPods,
  bluetoothHeadset,
  headphones,
  carPlay,
  unknown,
}

class AudioRoute {
  final String id;
  final String name;
  final AudioRouteType type;

  AudioRoute({required this.id, required this.name, required this.type});

  factory AudioRoute.fromMap(Map<String, dynamic> map) {
    return AudioRoute(
      id: map['id'] as String? ?? '',
      name: map['name'] as String? ?? '',
      type: _parseType(map['type'] as String? ?? ''),
    );
  }

  static AudioRouteType _parseType(String type) {
    switch (type) {
      case 'iPhone':
        return AudioRouteType.iPhone;
      case 'speaker':
        return AudioRouteType.speaker;
      case 'airPods':
        return AudioRouteType.airPods;
      case 'bluetoothHeadset':
        return AudioRouteType.bluetoothHeadset;
      case 'headphones':
        return AudioRouteType.headphones;
      case 'carPlay':
        return AudioRouteType.carPlay;
      default:
        return AudioRouteType.unknown;
    }
  }

  @override
  String toString() => 'AudioRoute($id: $name, $type)';
}
