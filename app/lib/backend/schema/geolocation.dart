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

  wire.GeneratedGeolocation toGenerated() {
    return wire.GeneratedGeolocation(
      latitude: latitude ?? 0.0,
      longitude: longitude ?? 0.0,
      googlePlaceId: googlePlaceId,
      address: address,
      locationType: locationType,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      ...toGenerated().toJson(),
      'id': id,
      'altitude': altitude,
      'accuracy': accuracy,
      'time': time?.toUtc().toIso8601String(),
      'google_place_id': googlePlaceId, // server
      'location_type': locationType, // server
    };
  }
}
