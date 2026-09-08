// Not a pure 1:1 wrapper: this class additionally holds the legacy local id,
// treats latitude/longitude as nullable (the wire type requires them), and
// throws from toGenerated() when either coordinate is absent.

import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;

class Geolocation {
  // TODO: location should be the place the memory starts

  int id = 0;

  double? latitude;
  double? longitude;
  double? altitude;
  double? accuracy;

  DateTime? time;
  String? captureSource;

  String? googlePlaceId;
  String? address;
  String? locationType;

  Geolocation({
    this.latitude,
    this.longitude,
    this.altitude,
    this.accuracy,
    this.time,
    this.captureSource,
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
      altitude: generated.altitude,
      accuracy: generated.accuracy,
      time: generated.capturedAt?.toUtc() ?? (json['time'] == null ? null : DateTime.parse(json['time']).toUtc()),
      captureSource: generated.captureSource,
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
      altitude: generated.altitude,
      accuracy: generated.accuracy,
      time: generated.capturedAt?.toUtc(),
      captureSource: generated.captureSource,
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
      altitude: altitude,
      accuracy: accuracy,
      capturedAt: time,
      captureSource: captureSource,
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
      'captured_at': time?.toUtc().toIso8601String(),
      'capture_source': captureSource,
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
