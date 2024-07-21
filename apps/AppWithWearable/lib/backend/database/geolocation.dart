import 'package:objectbox/objectbox.dart';

@Entity()
class Geolocation {
  // TODO: location should be the place the memory starts
  @Id()
  int id = 0;

  double? latitude;
  double? longitude;
  double? altitude;
  double? accuracy;

  @Property(type: PropertyType.date)
  DateTime? time;

  String? googlePlaceId;
  String? address;
  String? locationType;

  // TODO: eventually locations could map to multiple memories
  // @Backlink('memory')
  // final memories = ToMany<Memory>();

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
      time: DateTime.parse(json['time']),
      googlePlaceId: json['googlePlaceId'],
      address: json['address'],
      locationType: json['locationType'],
    );
    geolocation.id = json['id'];
    return geolocation;
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'latitude': latitude,
      'longitude': longitude,
      'altitude': altitude,
      'accuracy': accuracy,
      'time': time!.toIso8601String(),
      'googlePlaceId': googlePlaceId,
      'address': address,
      'locationType': locationType,
    };
  }
}
