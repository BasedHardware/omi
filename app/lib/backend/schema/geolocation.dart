// Phase 4.1 SKIPPED — not a pure 1:1 wrapper, so not typedef'd here.
// GeneratedGeolocation (gen/conversation_wire.g.dart) only carries latitude, longitude,
// googlePlaceId, address, locationType. This class additionally holds
// id/altitude/accuracy/time, treats latitude/longitude as nullable (the generated type
// requires them), and throws a StateError from toGenerated() when lat/lon are absent.
// Typedefing would drop the extra fields and change nullability + the throw contract.

import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;

class Geolocation {
  // TODO: location should be the place the memory starts

  int id = 0;

  double? latitude;
  double? longitude;
  double? altitude;
  double? accuracy;

  DateTime? time;

  String? googlePlaceId;
  String? address;
  String? locationType;

  Geolocation({
    this.latitude,
    this.longitude,
    this.altitude,
    this.accuracy,
    this.time,
    this.googlePlaceId,
    this.address,
    this.locationType,
    this.id = 0,
  });

  static Geolocation fromJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedGeolocation.fromJson(json);
    var geolocation = Geolocation(
      latitude: generated.latitude,
      longitude: generated.longitude,
      altitude: json['altitude'],
      accuracy: json['accuracy'],
      // not in server
      time: json['time'] == null ? null : DateTime.parse(json['time']),
      // google_place_id server
      googlePlaceId: generated.googlePlaceId,
      address: generated.address,
      // location_type server
      locationType: generated.locationType,
    );
    return geolocation;
  }

  factory Geolocation.fromGenerated(wire.GeneratedGeolocation generated) {
    return Geolocation(
      latitude: generated.latitude,
      longitude: generated.longitude,
      googlePlaceId: generated.googlePlaceId,
      address: generated.address,
      locationType: generated.locationType,
    );
  }

  wire.GeneratedGeolocation toGenerated() {
    final lat = latitude;
    final lon = longitude;
    if (lat == null || lon == null) {
      throw StateError('Cannot serialize geolocation without latitude and longitude');
    }
    return wire.GeneratedGeolocation(
      latitude: lat,
      longitude: lon,
      googlePlaceId: googlePlaceId,
      address: address,
      locationType: locationType,
    );
  }

  Map<String, dynamic> toJson() {
    final lat = latitude;
    final lon = longitude;
    final result = <String, dynamic>{
      'id': id,
      'altitude': altitude,
      'accuracy': accuracy,
      'time': time?.toUtc().toIso8601String(),
      'google_place_id': googlePlaceId,
      'location_type': locationType,
      'address': address,
    };
    if (lat != null && lon != null) {
      result.addAll(toGenerated().toJson());
    } else {
      if (lat != null) result['latitude'] = lat;
      if (lon != null) result['longitude'] = lon;
    }
    return result;
  }
}
