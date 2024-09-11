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
    var geolocation = Geolocation(
      latitude: json['latitude'],
      longitude: json['longitude'],
      altitude: json['altitude'],
      accuracy: json['accuracy'],
      // not in server
      time: json['time'] == null ? null : DateTime.parse(json['time']),
      // google_place_id server
      googlePlaceId: json['googlePlaceId'] ?? json['google_place_id'],
      address: json['address'],
      // location_type server
      locationType: json['locationType'] ?? json['location_type'],
    );
    return geolocation;
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'latitude': latitude,
      'longitude': longitude,
      'altitude': altitude,
      'accuracy': accuracy,
      'time': time?.toUtc().toIso8601String(),
      'googlePlaceId': googlePlaceId,
      'google_place_id': googlePlaceId, // server
      'address': address,
      'locationType': locationType,
      'location_type': locationType, // server
    };
  }
}
