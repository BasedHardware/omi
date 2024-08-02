import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/env.dart';
import 'package:http/http.dart' as http;
import 'package:location/location.dart';

// Function to calculate the distance between two coordinates using the Haversine formula
double calculateDistance(double lat1, double lon1, double lat2, double lon2) {
  // Radius of the Earth in meters
  const double earthRadius = 6371000;
  // Convert latitude and longitude from degrees to radians
  double dLat = (lat2 - lat1) * pi / 180;
  double dLon = (lon2 - lon1) * pi / 180;
  // Haversine formula for calculating distance
  double a =
      sin(dLat / 2) * sin(dLat / 2) + cos(lat1 * pi / 180) * cos(lat2 * pi / 180) * sin(dLon / 2) * sin(dLon / 2);
  double c = 2 * atan2(sqrt(a), sqrt(1 - a));
  // Distance in meters using the Earth's radius
  double distance = earthRadius * c;
  // Return the calculated distance
  return distance;
}

// Function to check if a coordinate is within a certain range (in meters) of another coordinate
bool isWithinRange(double lat1, double lon1, double lat2, double lon2, double rangeInMeters) {
  double distance = calculateDistance(lat1, lon1, lat2, lon2);
  return distance <= rangeInMeters;
}

class LocationService {
  Location location = Location();
  StreamSubscription<LocationData>? _locationSubscription;
  List<LocationData> locationDataList = [];

  Future<void> startLocationService() async {
    if (await hasPermission()) {
      _locationSubscription = location.onLocationChanged.listen((LocationData locationData) {
        // if the current location is 20 meters away from the last location, add it to the list
        if (locationDataList.isEmpty ||
            isWithinRange(locationDataList.last.latitude!, locationDataList.last.longitude!, locationData.latitude!,
                locationData.longitude!, 20)) {
          locationDataList.add(locationData);
          print("Location data added: ${locationData.latitude}, ${locationData.longitude}");
        }
      });
    }
  }

  void stopLocationService() {
    _locationSubscription?.cancel();
  }

  Future<bool> enableService() async {
    location.enableBackgroundMode(enable: true);
    bool serviceEnabled = await location.serviceEnabled();
    if (!serviceEnabled) {
      serviceEnabled = await location.requestService();
      if (!serviceEnabled) {
        return false;
      } else {
        return true;
      }
    } else {
      return true;
    }
  }

  Future<bool> displayPermissionsDialog() async {
    // if (SharedPreferencesUtil().locationPermissionRequested) return false;
    SharedPreferencesUtil().locationPermissionRequested = true;
    var status = await permissionStatus();
    return await isServiceEnabled() == false ||
        (status != PermissionStatus.granted && status != PermissionStatus.deniedForever);
  }

  Future<bool> isServiceEnabled() => location.serviceEnabled();

  Future<PermissionStatus> requestPermission() async {
    PermissionStatus permissionGranted = await location.hasPermission();
    if (permissionGranted == PermissionStatus.denied) {
      permissionGranted = await location.requestPermission();
    }
    await startLocationService();
    return permissionGranted;
  }

  Future<PermissionStatus> permissionStatus() => location.hasPermission();

  Future hasPermission() async => (await location.hasPermission()) == PermissionStatus.granted;

  Future<Geolocation?> getGeolocationDetails() async {
    if (await hasPermission()) {
      LocationData locationData = await location.getLocation();
      // TODO: move http requests to other.dart

      try {
        var res = await http.get(
          Uri.parse(
            "https://maps.googleapis.com/maps/api/geocode/json?latlng"
            "=${locationData.latitude},${locationData.longitude}&key=${Env.googleMapsApiKey}",
          ),
        );

        var data = json.decode(res.body);
        Geolocation geolocation = Geolocation(
          latitude: locationData.latitude,
          longitude: locationData.longitude,
          address: data['results'][0]['formatted_address'],
          locationType: data['results'][0]['types'][0],
          googlePlaceId: data['results'][0]['place_id'],
        );
        return geolocation;
      } catch (e) {
        return Geolocation(latitude: locationData.latitude, longitude: locationData.longitude);
      }
    } else {
      return null;
    }
  }
}
