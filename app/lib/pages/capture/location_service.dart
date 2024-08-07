import 'dart:async';

import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:location/location.dart';

class LocationService {
  Location location = Location();

  Future<bool> enableService() async {
    bool serviceEnabled = await location.serviceEnabled();
    if (serviceEnabled) {
      return true;
    } else {
      return await location.requestService();
    }
  }

  Future<bool> displayPermissionsDialog() async {
    if (SharedPreferencesUtil().locationPermissionRequested) return false;
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
    return permissionGranted;
  }

  Future<PermissionStatus> permissionStatus() => location.hasPermission();

  Future hasPermission() async => (await location.hasPermission()) == PermissionStatus.granted;

  Future<Geolocation?> getGeolocationDetails() async {
    if (await hasPermission()) {
      LocationData locationData = await location.getLocation();
      return Geolocation(latitude: locationData.latitude, longitude: locationData.longitude);
    } else {
      return null;
    }
  }
}
